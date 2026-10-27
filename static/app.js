const $ = (id) => document.getElementById(id);
const signalOrder = ['ZS','Pre-ZS','iZS','Pre-iZS'];
let poller = null;
function renderStatus(s) {
  $('progressBar').style.width = `${s.progress || 0}%`;
  $('progressText').textContent = `${s.progress || 0}%`;
  $('pairText').textContent = s.total ? `${s.scanned || 0} / ${s.total} pairs checked` : 'Loading USDT perpetual pairs…';
  const c = s.consolidation || {mode:'fixed', length:10, min:10, max:20};
  const cLabel = c.mode === 'range' ? `${c.min}–${c.max} candle range` : `${c.length} candles`;
  $('status').textContent = s.running ? `Scanning ${s.timeframe} candles · consolidation ${cLabel}…` : s.error ? `Scan failed: ${s.error}` : s.finished_at ? `Scan complete · ${s.timeframe} · ${cLabel}` : 'Ready to scan';
  $('scanBtn').disabled = !!s.running;
  $('scanBtn').textContent = s.running ? 'Scanning…' : 'Scan all USDT pairs →';
  const counts = s.counts || {};
  signalOrder.forEach(name => $( `count-${name}`).textContent = counts[name] || 0);
  const results = s.results || [];
  $('resultSummary').textContent = s.running ? `Checking pairs and updating signals as results arrive… ${results.length} matching signal(s) found so far.` : s.error ? 'The scan did not finish. Check server logs or try again.' : s.finished_at ? `${results.length} matching signal(s) across ${s.total} USDT perpetual pairs.` : 'No signals yet. Start a scan to populate the table.';
  const body = $('resultsBody');
  if (!results.length) {
    body.innerHTML = `<tr class="empty"><td colspan="3">${s.running ? 'No matching signals found yet — scan is still running.' : s.finished_at && !s.error ? 'No pairs matched the selected conditions on this scan.' : 'Your matching USDT perpetual pairs will appear here.'}</td></tr>`;
  } else {
    body.innerHTML = results.map(r => `<tr><td class="pair">${escapeHtml(r.symbol)}</td><td><span class="signal ${r.side}">${escapeHtml(r.signal)}</span></td><td class="direction">${r.side === 'long' ? 'LONG' : 'SHORT'}</td></tr>`).join('');
  }
  if (!s.running && poller) { clearInterval(poller); poller = null; }
}
function escapeHtml(v) { return String(v).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c])); }
async function refreshStatus() {
  try { const res = await fetch('/api/scan/status', {cache:'no-store'}); renderStatus(await res.json()); }
  catch (e) { $('status').textContent = 'Cannot connect to the screener server. Refresh the page and try again.'; }
}
$('scanBtn').addEventListener('click', async () => {
  $('scanBtn').disabled = true;
  $('status').textContent = 'Starting scan…';
  try {
    const res = await fetch('/api/scan/start', {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({timeframe:$('timeframe').value,consolidation_mode:$('consolidationMode').value,consolidation_length:Number($('consolidationLength').value),consolidation_min:Number($('consolidationMin').value),consolidation_max:Number($('consolidationMax').value)})});
    const payload = await res.json();
    if (!res.ok) throw new Error(payload.error || 'Could not start scan');
    await refreshStatus();
    if (poller) clearInterval(poller);
    poller = setInterval(refreshStatus, 1200);
  } catch (e) { $('status').textContent = e.message; $('scanBtn').disabled = false; }
});
refreshStatus();

function updateConsolidationFields() {
  const range = $('consolidationMode').value === 'range';
  $('fixedLengthField').hidden = range;
  $('rangeFields').hidden = !range;
}
$('consolidationMode').addEventListener('change', updateConsolidationFields);
$('consolidationMin').addEventListener('change', () => {
  if (Number($('consolidationMin').value) > Number($('consolidationMax').value)) $('consolidationMax').value = $('consolidationMin').value;
});
$('consolidationMax').addEventListener('change', () => {
  if (Number($('consolidationMax').value) < Number($('consolidationMin').value)) $('consolidationMin').value = $('consolidationMax').value;
});
updateConsolidationFields();
