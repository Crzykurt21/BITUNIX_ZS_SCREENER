from flask import Flask, jsonify, render_template, request
import requests, threading, time, math
from concurrent.futures import ThreadPoolExecutor, as_completed

app = Flask(__name__)
BASE = 'https://fapi.bitunix.com'
SESSION = requests.Session()
SESSION.headers.update({'User-Agent': 'Bitunix-PreZS-Screener/1.0', 'Accept': 'application/json'})
TIMEFRAMES = {'1m':'1m','3m':'3m','15m':'15m','1H':'1h','4H':'4h','1D':'1d','1W':'1w'}
JOB_LOCK = threading.Lock()
JOB = {'running': False, 'progress': 0, 'total': 0, 'scanned': 0, 'timeframe': '1H', 'consolidation': {'mode':'fixed','length':10,'min':10,'max':20}, 'results': [], 'counts': {'ZS':0,'Pre-ZS':0,'iZS':0,'Pre-iZS':0}, 'error': None, 'started_at': None, 'finished_at': None}


def get_json(path, params=None):
    url = BASE + path
    last_error = None
    for attempt in range(3):
        try:
            r = SESSION.get(url, params=params, timeout=15)
            r.raise_for_status()
            payload = r.json()
            if isinstance(payload, dict) and payload.get('code') not in (None, 0, '0'):
                raise RuntimeError(payload.get('msg') or f"Bitunix API error {payload.get('code')}")
            return payload.get('data', payload) if isinstance(payload, dict) else payload
        except Exception as e:
            last_error = e
            time.sleep(0.4 * (attempt + 1))
    raise RuntimeError(str(last_error))


def get_symbols():
    data = get_json('/api/v1/futures/market/trading_pairs')
    if isinstance(data, dict):
        data = data.get('list') or data.get('data') or []
    symbols = []
    for row in data or []:
        if not isinstance(row, dict):
            continue
        symbol = str(row.get('symbol') or row.get('symbolName') or '').upper()
        quote = str(row.get('quote') or '').upper()
        status = str(row.get('symbolStatus') or 'OPEN').upper()
        if symbol.endswith('USDT') and (not quote or quote == 'USDT') and status == 'OPEN':
            symbols.append(symbol)
    return sorted(set(symbols))


def fetch_candles(symbol, interval):
    data = get_json('/api/v1/futures/market/kline', {'symbol': symbol, 'interval': interval, 'limit': 200, 'type': 'LAST_PRICE'})
    if isinstance(data, dict):
        data = data.get('list') or data.get('data') or []
    rows = []
    for k in data or []:
        try:
            rows.append({'time': int(k.get('time', k.get('ts', 0))), 'close': float(k['close'])})
        except (ValueError, TypeError, KeyError):
            continue
    rows.sort(key=lambda x: x['time'])
    # Official Bitunix futures kline documentation says the still-forming candle is not returned.
    # Keep the final returned candle as the most recently closed candle.
    return rows


def sma(values, period):
    out = [None] * len(values)
    for i in range(period - 1, len(values)):
        window = values[i-period+1:i+1]
        out[i] = sum(window) / period
    return out


def ema(values, period):
    out = [None] * len(values)
    if len(values) < period:
        return out
    # Seed with the simple average, then apply the standard EMA recurrence.
    out[period-1] = sum(values[:period]) / period
    alpha = 2.0 / (period + 1)
    for i in range(period, len(values)):
        out[i] = alpha * values[i] + (1-alpha) * out[i-1]
    return out


def rsi_wilder(values, period=14):
    out = [None] * len(values)
    if len(values) <= period:
        return out
    gains, losses = [], []
    for i in range(1, len(values)):
        delta = values[i] - values[i-1]
        gains.append(max(delta, 0.0)); losses.append(max(-delta, 0.0))
    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period
    def calc(g, l):
        if l == 0:
            return 100.0 if g > 0 else 50.0
        return 100.0 - (100.0 / (1.0 + g/l))
    out[period] = calc(avg_gain, avg_loss)
    for i in range(period + 1, len(values)):
        avg_gain = ((period-1)*avg_gain + gains[i-1]) / period
        avg_loss = ((period-1)*avg_loss + losses[i-1]) / period
        out[i] = calc(avg_gain, avg_loss)
    return out


def classify(symbol, candles, lengths=(10,)):
    # Need SMA100 warmup plus 50 prior candles and the longest consolidation window.
    lengths = sorted(set(int(x) for x in lengths if 1 <= int(x) <= 50))
    if not lengths:
        return []
    max_len = max(lengths)
    if len(candles) < 100 + 50 + max_len:
        return []
    closes = [x['close'] for x in candles]
    e19, s23, s100, r14 = ema(closes, 19), sma(closes, 23), sma(closes, 100), rsi_wilder(closes, 14)
    n = len(closes)
    last = n - 1
    if any(arr[last] is None for arr in (e19, s23, s100, r14)):
        return []

    # Each selected length is evaluated independently. In range mode, a symbol
    # qualifies if any complete window in the inclusive range matches.
    signals = []
    matched = set()
    for length in lengths:
        setup_start = n - length
        prior_start = setup_start - 50
        if prior_start < 99:
            continue
        setup = list(range(setup_start, n))
        prior = list(range(prior_start, setup_start))
        prior_below = all(closes[i] < s100[i] for i in prior)
        prior_above = all(closes[i] > s100[i] for i in prior)
        pre = setup
        breakout_base = setup[:-1]

        if ('Pre-ZS' not in matched and prior_below and
            all(closes[i] > e19[i] and closes[i] > s23[i] and closes[i] < s100[i] for i in pre) and
            r14[last] >= 50):
            signals.append({'symbol': symbol, 'signal': 'Pre-ZS', 'side': 'long', 'consolidation': length})
            matched.add('Pre-ZS')
        if ('ZS' not in matched and prior_below and
            all(closes[i] > e19[i] and closes[i] > s23[i] and closes[i] < s100[i] for i in breakout_base) and
            closes[last] > e19[last] and closes[last] > s23[last] and closes[last] > s100[last] and
            r14[last] >= 50):
            signals.append({'symbol': symbol, 'signal': 'ZS', 'side': 'long', 'consolidation': length})
            matched.add('ZS')
        if ('Pre-iZS' not in matched and prior_above and
            all(closes[i] < e19[i] and closes[i] < s23[i] and closes[i] > s100[i] for i in pre) and
            r14[last] <= 50):
            signals.append({'symbol': symbol, 'signal': 'Pre-iZS', 'side': 'short', 'consolidation': length})
            matched.add('Pre-iZS')
        if ('iZS' not in matched and prior_above and
            all(closes[i] < e19[i] and closes[i] < s23[i] and closes[i] > s100[i] for i in breakout_base) and
            closes[last] < e19[last] and closes[last] < s23[last] and closes[last] < s100[last] and
            r14[last] <= 50):
            signals.append({'symbol': symbol, 'signal': 'iZS', 'side': 'short', 'consolidation': length})
            matched.add('iZS')
        if len(matched) == 4:
            break
    return signals


def run_scan(timeframe, lengths, consolidation):
    try:
        symbols = get_symbols()
        with JOB_LOCK:
            JOB['total'] = len(symbols); JOB['progress'] = 0; JOB['scanned'] = 0
        if not symbols:
            raise RuntimeError('Bitunix returned no open USDT perpetual pairs. Please try again later.')
        found = []
        # Keep concurrency modest to respect the public API rate limit.
        with ThreadPoolExecutor(max_workers=5) as pool:
            futures = {pool.submit(fetch_candles, symbol, TIMEFRAMES[timeframe]): symbol for symbol in symbols}
            for fut in as_completed(futures):
                symbol = futures[fut]
                try:
                    candles = fut.result()
                    found.extend(classify(symbol, candles, lengths))
                except Exception:
                    # A single unavailable pair should not stop the whole scan.
                    pass
                with JOB_LOCK:
                    JOB['scanned'] += 1
                    JOB['progress'] = int(JOB['scanned'] * 100 / max(JOB['total'], 1))
                    JOB['results'] = sorted(found, key=lambda x: (['ZS','Pre-ZS','iZS','Pre-iZS'].index(x['signal']), x['symbol']))
                    JOB['counts'] = {s: sum(1 for x in found if x['signal'] == s) for s in ['ZS','Pre-ZS','iZS','Pre-iZS']}
        with JOB_LOCK:
            JOB['running'] = False; JOB['progress'] = 100; JOB['finished_at'] = time.time()
    except Exception as e:
        with JOB_LOCK:
            JOB['running'] = False; JOB['error'] = str(e); JOB['finished_at'] = time.time()


@app.get('/')
def index():
    return render_template('index.html')

@app.get('/api/health')
def health():
    return jsonify({'ok': True, 'timeframes': list(TIMEFRAMES.keys()), 'consolidation_modes': ['fixed', 'range']})

@app.post('/api/scan/start')
def start_scan():
    data = request.get_json(silent=True) or {}
    timeframe = data.get('timeframe', '1H')
    if timeframe not in TIMEFRAMES:
        return jsonify({'error': 'Unsupported timeframe'}), 400
    mode = data.get('consolidation_mode', 'fixed')
    try:
        if mode == 'range':
            min_len = int(data.get('consolidation_min', 10)); max_len = int(data.get('consolidation_max', 20))
            if min_len < 10 or max_len > 30 or min_len > max_len:
                raise ValueError
            lengths = list(range(min_len, max_len + 1))
            consolidation = {'mode':'range', 'length':None, 'min':min_len, 'max':max_len}
        elif mode == 'fixed':
            fixed_len = int(data.get('consolidation_length', 10))
            if fixed_len not in (10, 15, 20):
                raise ValueError
            lengths = [fixed_len]
            consolidation = {'mode':'fixed', 'length':fixed_len, 'min':fixed_len, 'max':fixed_len}
        else:
            raise ValueError
    except (TypeError, ValueError):
        return jsonify({'error': 'Invalid consolidation settings. Choose fixed 10, 15, 20 or a range from 10 to 30.'}), 400
    with JOB_LOCK:
        if JOB['running']:
            return jsonify({'error': 'A scan is already running'}), 409
        JOB.update({'running': True, 'progress': 0, 'total': 0, 'scanned': 0, 'timeframe': timeframe, 'consolidation': consolidation, 'results': [], 'counts': {'ZS':0,'Pre-ZS':0,'iZS':0,'Pre-iZS':0}, 'error': None, 'started_at': time.time(), 'finished_at': None})
    threading.Thread(target=run_scan, args=(timeframe, lengths, consolidation), daemon=True).start()
    return jsonify({'started': True, 'timeframe': timeframe})

@app.get('/api/scan/status')
def scan_status():
    with JOB_LOCK:
        return jsonify(dict(JOB))

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(__import__('os').environ.get('PORT', '10000')))
