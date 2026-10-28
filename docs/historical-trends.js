(() => {
  'use strict';
  const $=id=>document.getElementById(id);
  const cfg=window.MTA_SUPABASE_PUBLIC||{};
  const fmt=n=>Number(n||0).toLocaleString('en-US');
  const pct=(n,d)=>d?((100*n/d).toFixed(1)+'%'):'—';
  const routeLabel=id=>window.mtaRouteLabel?window.mtaRouteLabel(id):'Route '+id;
  const safe=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  let data=[],filtered=[];
  const state=(msg,error=false)=>{const el=$('trend-state');el.textContent=msg;el.classList.toggle('error',error);};
  function matchHour(h,win){
    if(win==='morning')return h>=6&&h<9;
    if(win==='afternoon')return h>=14&&h<17;
    if(win==='other')return !((h>=6&&h<9)||(h>=14&&h<17));
    return true;
  }
  function svgLine(daily){
    const w=740,h=250,left=53,right=15,top=20,bottom=48;
    if(!daily.length)return '<p class="dash-muted">No records for the selected period.</p>';
    const plotW=w-left-right,plotH=h-top-bottom;
    const maxY=Math.max(5,Math.ceil(Math.max(...daily.map(d=>Math.max(d.five/d.total*100,d.fifteen/d.total*100)))/5)*5);
    const x=i=>left+(daily.length===1?plotW/2:i*plotW/(daily.length-1));
    const y=v=>top+plotH*(1-v/maxY);
    const path=key=>daily.map((d,i)=>(i?'L':'M')+x(i).toFixed(1)+','+y(100*d[key]/d.total).toFixed(1)).join(' ');
    const ticks=[0,.25,.5,.75,1].map(t=>`<line x1="${left}" x2="${w-right}" y1="${y(t*maxY)}" y2="${y(t*maxY)}" stroke="#c7ccd1" stroke-dasharray="3 4"/><text x="${left-8}" y="${y(t*maxY)+4}" text-anchor="end" font-size="12" fill="currentColor">${Math.round(t*maxY)}%</text>`).join('');
    const labels=daily.map((d,i)=>`<text x="${x(i)}" y="${h-24}" font-size="11" text-anchor="middle" fill="currentColor">${safe(d.date.slice(5))}</text>`).join('');
    const dots=key=>daily.map((d,i)=>`<circle cx="${x(i)}" cy="${y(100*d[key]/d.total)}" r="3.5" fill="${key==='five'?'#9f4538':'#284e75'}"><title>${safe(d.date)}: ${pct(d[key],d.total)} of ${fmt(d.total)} observations</title></circle>`).join('');
    return `<svg viewBox="0 0 ${w} ${h}" width="100%" role="img" aria-label="Daily percentage of observations predicting delays of at least five or fifteen minutes">${ticks}${labels}<path d="${path('five')}" fill="none" stroke="#9f4538" stroke-width="3"/>${dots('five')}<path d="${path('fifteen')}" fill="none" stroke="#284e75" stroke-width="3"/>${dots('fifteen')}</svg><p class="dash-muted"><span style="color:#9f4538">■</span> 5+ minutes predicted late &nbsp; <span style="color:#284e75">■</span> 15+ minutes predicted late</p>`;
  }
  function render(){
    const win=$('trend-window').value;
    filtered=data.filter(r=>matchHour(Number(r.service_hour),win));
    const total=filtered.reduce((n,r)=>n+Number(r.observation_count||0),0);
    const five=filtered.reduce((n,r)=>n+Number(r.predictions_5min_late||0),0);
    const fifteen=filtered.reduce((n,r)=>n+Number(r.predictions_15min_late||0),0);
    $('trend-observations').textContent=fmt(total);
    $('trend-5rate').textContent=pct(five,total);
    $('trend-15rate').textContent=pct(fifteen,total);
    $('trend-coverage').textContent=fmt(filtered.length);
    const byDay=new Map(),byRoute=new Map();
    for(const r of filtered){
      const n=Number(r.observation_count||0),a=Number(r.predictions_5min_late||0),b=Number(r.predictions_15min_late||0);
      const day=byDay.get(r.service_date)||{date:r.service_date,total:0,five:0,fifteen:0};
      day.total+=n;day.five+=a;day.fifteen+=b;byDay.set(r.service_date,day);
      const route=byRoute.get(r.route_id)||{route:r.route_id,total:0,five:0,fifteen:0,hours:0};
      route.total+=n;route.five+=a;route.fifteen+=b;route.hours++;byRoute.set(r.route_id,route);
    }
    const days=[...byDay.values()].filter(d=>d.total>0).sort((a,b)=>a.date.localeCompare(b.date));
    $('trend-chart').innerHTML=svgLine(days);
    const routes=[...byRoute.values()].sort((a,b)=>(b.five/b.total)-(a.five/a.total));
    $('trend-routes-body').innerHTML=routes.length?routes.map(r=>`<tr><td>${safe(routeLabel(r.route))}</td><td>${fmt(r.total)}</td><td>${pct(r.five,r.total)} (${fmt(r.five)})</td><td>${pct(r.fifteen,r.total)} (${fmt(r.fifteen)})</td><td>${fmt(r.hours)}</td></tr>`).join(''):'<tr><td colspan="5">No observations for these filters.</td></tr>';
    $('trend-coverage-note').textContent=`${days.length} date(s) with observations in this selection. ${fmt(filtered.length)} route-hour summary rows. Blank dates are not treated as on-time service. Last loaded: ${new Date().toLocaleString('en-US',{timeZone:'America/New_York'})} Eastern.`;
  }
  async function load(){
    const url=String(cfg.url||'').trim().replace(/\/+$/,'');
    const key=String(cfg.publishableKey||'').trim();
    if(!/^https:\/\/[a-z0-9-]+\.supabase\.co$/i.test(url)||!key||key.includes('PASTE_')){
      state('Supabase public configuration missing. Existing dashboard remains available.',true);return;
    }
    state('Loading hourly summaries…');
    $('trend-refresh').disabled=true;
    try{
      const response=await fetch(url+'/rest/v1/rpc/mta_public_hourly_trends',{
        method:'POST',
        headers:{'apikey':key,'Content-Type':'application/json','Content-Profile':'public','Accept-Profile':'public'},
        body:JSON.stringify({p_days:Number($('trend-days').value),p_route:$('trend-route').value.trim()||null})
      });
      if(!response.ok)throw new Error('HTTP '+response.status+': '+(await response.text()).slice(0,500));
      const payload=await response.json();
      if(!Array.isArray(payload))throw new Error('Unexpected response shape');
      data=payload;
      render();
      state('Connected to Supabase hourly summaries. Charts updated.');
    }catch(e){state('Unable to load trends: '+e.message,true);}
    finally{$('trend-refresh').disabled=false;}
  }
  $('trend-days').addEventListener('change',load);
  $('trend-route').addEventListener('change',load);
  $('trend-window').addEventListener('change',render);
  $('trend-refresh').addEventListener('click',load);
  $('trend-export').addEventListener('click',()=>{
    const cols=['service_date','service_hour','route_id','observation_count','predictions_5min_late','predictions_15min_late','average_predicted_delay_seconds'];
    const quote=v=>'"'+String(v??'').replace(/"/g,'""')+'"';
    const csv=[cols.join(','),...filtered.map(r=>cols.map(c=>quote(r[c])).join(','))].join('\r\n');
    const url=URL.createObjectURL(new Blob([csv],{type:'text/csv;charset=utf-8'}));
    const a=document.createElement('a');a.href=url;a.download='mta-hourly-prediction-summaries.csv';a.click();
    setTimeout(()=>URL.revokeObjectURL(url),1000);
  });
  load();
})();
