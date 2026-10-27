# Bitunix PRE-ZS / ZS Screener

Web-based screener for open Bitunix USDT perpetual contracts. Default timeframe: **1H**. Public market data only; no API key is required and the app does not place trades.

## Included
- Timeframes: 1m, 3m, 15m, 1H, 4H, 1D, 1W
- Consolidation length selector: fixed 10, 15, or 20 candles; or an inclusive custom range from 10 to 30 candles (for example 10–20)
- Signal labels/counts: ZS, Pre-ZS, iZS, Pre-iZS
- Green long signals and red short signals
- Scan button and progress indicator
- Latest returned **closed** futures candle only; official Bitunix kline docs state the forming candle is not returned
- EMA 19, SMA 23, SMA 100, RSI 14
- Only open contracts quoted in USDT

## Strategy rules implemented

Let the latest closed candle be candle 10 in the setup window. The preceding 50 candles are checked against their own rolling SMA100 values. The selected consolidation length is evaluated independently; in range mode, any qualifying length in the inclusive range can trigger the signal. A symbol is shown at most once per signal label, even if multiple lengths qualify.

- **Pre-ZS (long):** The preceding 50 closes are below their SMA100. All 10 setup closes are above EMA19 and SMA23 and below SMA100. Latest RSI(14) >= 50.
- **ZS (long):** The preceding 50 closes are below SMA100. The first 9 setup closes are above EMA19 and SMA23 and below SMA100; the latest close is above EMA19, SMA23 and SMA100. Latest RSI(14) >= 50.
- **Pre-iZS (short):** The preceding 50 closes are above their SMA100. All 10 setup closes are below EMA19 and SMA23 and above SMA100. Latest RSI(14) <= 50.
- **iZS (short):** The preceding 50 closes are above SMA100. The first 9 setup closes are below EMA19 and SMA23 and above SMA100; the latest close is below EMA19, SMA23 and SMA100. Latest RSI(14) <= 50.

“Close below/above SMA100” is interpreted relative to the SMA100 value at that candle. “Touched” means candle close reaches/crosses the SMA100, rather than intrabar high/low touching it. As requested, the 50 prior candles do not need to meet EMA19/SMA23 conditions.

## Deploy on Render

1. Extract this ZIP.
2. Create a new GitHub repository and upload the files/folders in this project to the repository root.
3. In Render, choose **New + → Blueprint** and connect that repository. Render reads `render.yaml` and creates the web service.
4. Wait for deployment, then open the `.onrender.com` URL Render gives you.

If you already use the previous screener's GitHub/Render setup, use a **new repository and new Render service** so the existing MACD screener is not overwritten.

## Local run (optional)

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
# macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
python app.py
```
Then visit `http://127.0.0.1:10000`.

## Notes
- Public API requests are made server-side so the browser does not need direct cross-origin access.
- A scan requests candle history per listed open USDT perpetual pair. Scans can take time and can be affected by Bitunix API limits or network availability; individual pair errors are skipped rather than failing the entire scan.
- This is an initial implementation. Before relying on results, compare a few symbols against Bitunix/TradingView charts, especially RSI and EMA initialization, and validate all four signal definitions against your intended examples.
