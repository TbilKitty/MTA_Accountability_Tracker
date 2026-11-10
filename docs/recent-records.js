// "Historical MTA observations" panel. Reads docs/data/explorer-summary.json, which the
// collector rebuilds every 15 minutes from the published daily files (no database needed).
(() => {
  'use strict';
  const $ = id => document.getElementById(id);
  const state = $('db-state');
  if (!state) return;
  const fmt = n => Number(n || 0).toLocaleString('en-US');
  const esc = x => String(x ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const routeLabel = id => window.mtaRouteLabel ? window.mtaRouteLabel(id) : 'Route ' + id;
  const dt = s => s ? new Date(s).toLocaleString('en-US', {timeZone:'America/New_York', dateStyle:'short', timeStyle:'short'}) : '—';
  let summary = null, rows = [];
  function status(msg, bad=false) { state.textContent = msg; state.classList.toggle('error', bad); }
  function csv() {
    const head = ['observed_at_utc','route_id','trip_id','stop_id','predicted_delay_seconds','max_delay_seconds','polls'];
    const cell = v => '"' + String(v ?? '').replace(/"/g, '""') + '"';
    const data = [head.join(','), ...rows.map(r => head.map(k => cell(r[k])).join(','))].join('\r\n');
    const url = URL.createObjectURL(new Blob([data], {type:'text/csv;charset=utf-8'}));
    const a = document.createElement('a'); a.href = url; a.download = 'mta-recent-observations.csv'; a.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }
  function render() {
    if (!summary) return;
    const days = Number($('db-days').value) || 7;
    const q = $('db-route').value.trim().toLowerCase();
    const matches = id => !q || String(id).toLowerCase() === q || routeLabel(id).toLowerCase().includes(q);
    // Summary counts: stop rankings for the selected period, filtered by route.
    const stops = (summary.stops[String(days)] || []).filter(s => matches(s[1]));
    $('db-total').textContent = fmt(stops.length);
    $('db-routes').textContent = fmt(new Set(stops.map(s => s[1])).size);
    $('db-five').textContent = fmt(stops.reduce((n, s) => n + s[3], 0));
    $('db-fifteen').textContent = fmt(stops.reduce((n, s) => n + s[4], 0));
    const c = summary.recent_columns;
    const since = Date.now() - days * 864e5;
    rows = summary.recent.map(r => Object.fromEntries(c.map((k, i) => [k === 'sampled_at_utc' ? 'observed_at_utc' : k, r[i]])))
      .filter(r => matches(r.route_id) && new Date(r.observed_at_utc).getTime() >= since);
    $('db-body').innerHTML = rows.length ? rows.slice(0, 200).map(r => '<tr><td>' + esc(dt(r.observed_at_utc)) + '</td><td>' + esc(routeLabel(r.route_id)) + '</td><td>' + esc(r.trip_id) + '</td><td>' + esc(r.stop_id) + '</td><td>' + esc(r.predicted_delay_seconds === null ? 'Unknown' : (Number(r.predicted_delay_seconds) / 60).toFixed(1) + ' min') + '</td><td>Forecast only</td></tr>').join('') : '<tr><td colspan="6">No observations for these filters.</td></tr>';
    status('Updated ' + dt(summary.generated_utc) + ' Eastern. Covers ' + (summary.dates[0] || '—') + ' to ' + (summary.dates[summary.dates.length - 1] || '—') + ' (UTC dates).');
  }
  async function load() {
    status('Loading recent observations…');
    $('db-refresh').disabled = true;
    try {
      const res = await fetch('./data/explorer-summary.json', {cache:'no-store'});
      if (!res.ok) throw new Error('HTTP ' + res.status);
      summary = await res.json();
      if (!summary.stops || !Array.isArray(summary.recent)) throw new Error('Unexpected file shape');
      render();
    } catch (e) { status('Unable to load recent observations: ' + e.message, true); }
    finally { $('db-refresh').disabled = false; }
  }
  $('db-refresh').addEventListener('click', load);
  $('db-days').addEventListener('change', render);
  $('db-route').addEventListener('input', render);
  $('db-csv').addEventListener('click', csv);
  load();
})();
