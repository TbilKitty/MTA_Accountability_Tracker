(() => {
  'use strict';
  const $ = id => document.getElementById(id);
  const cfg = window.MTA_SUPABASE_PUBLIC || {};
  const state = $('db-state');
  const fmt = n => Number(n || 0).toLocaleString('en-US');
  const esc = x => String(x ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const routeLabel=id=>window.mtaRouteLabel?window.mtaRouteLabel(id):'Route '+id;
  const dt = s => s ? new Date(s).toLocaleString('en-US',{timeZone:'America/New_York',dateStyle:'short',timeStyle:'short'}) : '—';
  let rows = [];
  function status(msg, bad=false) { state.textContent=msg; state.classList.toggle('error',bad); }
  function csv() {
    const head=['observed_at_utc','route_id','trip_id','stop_id','predicted_delay_seconds','evidence_status'];
    const cell=v=>'"'+String(v??'').replace(/"/g,'""')+'"';
    const data=[head.join(','),...rows.map(r=>head.map(k=>cell(r[k])).join(','))].join('\r\n');
    const url=URL.createObjectURL(new Blob([data],{type:'text/csv;charset=utf-8'}));
    const a=document.createElement('a'); a.href=url; a.download='mta-supabase-observations.csv'; a.click(); setTimeout(()=>URL.revokeObjectURL(url),1000);
  }
  async function load() {
    const url=String(cfg.url||'').trim().replace(/\/+$/,'');
    const key=String(cfg.publishableKey||'').trim();
    if(!/^https:\/\/[a-z0-9-]+\.supabase\.co$/i.test(url) || !key || key.includes('PASTE_')) {
      status('Historical database connection is not configured yet. Existing GitHub-published observations remain available below.',true); return;
    }
    status('Loading Supabase history…');
    $('db-refresh').disabled=true;
    try {
      const res=await fetch(url+'/rest/v1/rpc/mta_public_dashboard',{
        method:'POST',
        headers:{
          'apikey':key,
          'Content-Type':'application/json',
          'Content-Profile':'public',
          'Accept-Profile':'public'
        },
        body:JSON.stringify({p_days:Number($('db-days').value),p_route:$('db-route').value.trim()||null})
      });
      if (!res.ok) {
        const details = await res.text();
        throw new Error(`Supabase HTTP ${res.status}: ${details.slice(0, 1000)}`);
      }
      const result=await res.json();
      rows=Array.isArray(result.records)?result.records:[];
      const s=result.summary||{};
      $('db-total').textContent=fmt(s.total);
      $('db-routes').textContent=fmt(s.routes);
      $('db-five').textContent=fmt(s.five_plus);
      $('db-fifteen').textContent=fmt(s.fifteen_plus);
      $('db-body').innerHTML=rows.length ? rows.map(r=>'<tr><td>'+esc(dt(r.observed_at_utc))+'</td><td>'+esc(routeLabel(r.route_id))+'</td><td>'+esc(r.trip_id)+'</td><td>'+esc(r.stop_id)+'</td><td>'+esc(r.predicted_delay_seconds===null?'Unknown':(Number(r.predicted_delay_seconds)/60).toFixed(1)+' min')+'</td><td>'+esc(r.evidence_status)+'</td></tr>').join('') : '<tr><td colspan="6">No observations for these filters.</td></tr>';
      status('Connected to Supabase. Historical summary and recent records loaded.');
    } catch(e) {status('Unable to load Supabase history: '+e.message,true);}
    finally {$('db-refresh').disabled=false;}
  }
  $('db-refresh').addEventListener('click',load);
  $('db-days').addEventListener('change',load);
  $('db-route').addEventListener('change',load);
  $('db-csv').addEventListener('click',csv);
  load();
})();
