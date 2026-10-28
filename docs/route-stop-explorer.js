(()=>{
'use strict';
const el=id=>document.getElementById(id),cfg=()=>window.MTA_SUPABASE_PUBLIC||{};
let tab='routes',routeData=[],stopData=[],loadedDays=null;
const n=v=>Number(v)||0,fmt=v=>n(v).toLocaleString('en-US'),pct=(a,b)=>b?100*a/b:0;
const escape=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const routeLabel=id=>window.mtaRouteLabel?window.mtaRouteLabel(id):'Route '+id;
const state=(s,error=false)=>{el('ex-state').textContent=s;el('ex-state').classList.toggle('error',error)};
async function rpc(name,days){
 const c=cfg(),url=String(c.url||'').replace(/\/+$/,''),key=String(c.publishableKey||'');
 if(!/^https:\/\/[a-z0-9-]+\.supabase\.co$/i.test(url)||!key)throw Error('Public Supabase configuration is missing');
 const r=await fetch(url+'/rest/v1/rpc/'+name,{method:'POST',headers:{'apikey':key,'Content-Type':'application/json','Content-Profile':'public','Accept-Profile':'public'},body:JSON.stringify({p_days:days,p_route:null})});
 if(!r.ok)throw Error(name+' HTTP '+r.status+': '+(await r.text()).slice(0,400));
 const result=await r.json();if(!Array.isArray(result))throw Error('Unexpected API response');return result;
}
function aggregateRoutes(rows){const m=new Map();for(const r of rows){const id=String(r.route_id??'Unknown');let a=m.get(id);if(!a){a={id,total:0,five:0,fifteen:0,days:new Set(),hours:0};m.set(id,a)}a.total+=n(r.observation_count);a.five+=n(r.predictions_5min_late);a.fifteen+=n(r.predictions_15min_late);a.days.add(r.service_date);a.hours++}return [...m.values()].map(a=>({...a,days:a.days.size}))}
function aggregateStops(rows){return rows.map(r=>({id:String(r.stop_id??'Unknown'),route:String(r.route_id??'Unknown'),total:n(r.observation_count),five:n(r.predictions_5min_late),fifteen:n(r.predictions_15min_late),days:n(r.days_observed)}))}
function render(){
 for(const name of ['routes','stops','missed']){const b=el('ex-'+name);b.classList.toggle('ex-active',tab===name);b.setAttribute('aria-pressed',String(tab===name))}
 el('ex-controls').hidden=tab==='missed';
 if(tab==='missed'){state('Verification system not yet established.');el('ex-results').innerHTML='<div class="explorer-empty"><h3>No verified missed-service counts yet</h3><p>A missing prediction does not prove a bus failed to arrive. A defensible no-show investigation must compare scheduled service with vehicle evidence and, where available, dispatch records or corroborated rider reports.</p><p>Until those checks exist, this section will not rank routes or stops by no-shows.</p></div>';return}
 const q=el('ex-search').value.trim().toLowerCase(),sort=el('ex-sort').value;
 let arr=tab==='routes'?aggregateRoutes(routeData):aggregateStops(stopData);
 arr=arr.filter(a=>(a.id+' '+(a.route||'')+' '+routeLabel(tab==='routes'?a.id:a.route)).toLowerCase().includes(q));
 const score=a=>sort==='count'?a.five:sort==='severe'?pct(a.fifteen,a.total):pct(a.five,a.total);
 arr.sort((a,b)=>score(b)-score(a)||b.total-a.total);
 const title=tab==='routes'?'Routes with the highest predicted-delay rates':'Stops with the highest predicted-delay rates';
 const sample=arr.slice(0,30),max=Math.max(1,...sample.map(score));
 const metric=a=>sort==='count'?fmt(a.five):pct(sort==='severe'?a.fifteen:a.five,a.total).toFixed(1)+'%';
 el('ex-results').innerHTML='<h3>'+title+'</h3>'+(!sample.length?'<p class="explorer-empty">No matching observations for this selection.</p>':sample.map(a=>`<div class="explorer-rank"><div><strong>${tab==='routes'?escape(routeLabel(a.id)):'Stop '+escape(a.id)}</strong><small>${tab==='stops'?escape(routeLabel(a.route))+' · ':''}${fmt(a.total)} observations · ${fmt(a.days)} day(s)</small></div><div class="explorer-meter" aria-hidden="true"><span style="width:${Math.max(0,Math.min(100,100*score(a)/max))}%"></span></div><div class="ex-number">${metric(a)}</div></div>`).join(''));
 const limit=tab==='routes'?10000:1000;
 const raw=tab==='routes'?routeData:stopData;
 state('Loaded '+fmt(raw.length)+' summary rows from Supabase'+(raw.length>=limit?' (API row limit reached; rankings may be incomplete)':''));
 el('ex-disclosure').textContent='Showing up to 30 matches, ranked by '+el('ex-sort').selectedOptions[0].text+'. Percentages are based on prediction observations, not distinct late buses. Data covers only dates and hours with observations. '+(tab==='stops'?'Stop IDs may need a GTFS stop-name lookup to display street names. ':'')+(raw.length>=limit?'The API response reached its row cap; rankings are incomplete.':'');
}
async function load(){const days=Number(el('ex-days').value);state('Loading route and stop summaries…');try{const [r,s]=await Promise.all([rpc('mta_public_hourly_trends',days),rpc('mta_public_stop_rankings',days)]);routeData=r;stopData=s;loadedDays=days;render()}catch(e){state('Unable to load rankings: '+e.message,true);el('ex-results').innerHTML='<p class="explorer-empty">Existing historical records are still available below.</p>'}}
for(const name of ['routes','stops','missed'])el('ex-'+name).addEventListener('click',()=>{tab=name;render()});
el('ex-days').addEventListener('change',load);el('ex-search').addEventListener('input',render);el('ex-sort').addEventListener('change',render);
load();
})();
