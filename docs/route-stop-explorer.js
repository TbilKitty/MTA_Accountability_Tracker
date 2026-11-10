(()=>{
'use strict';
const el=id=>document.getElementById(id),_unused=null;
let tab='routes',routeData=[],stopData=[],loadedDays=null;
const n=v=>Number(v)||0,fmt=v=>n(v).toLocaleString('en-US'),pct=(a,b)=>b?100*a/b:0;
const escape=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const routeLabel=id=>window.mtaRouteLabel?window.mtaRouteLabel(id):'Route '+id;
const state=(s,error=false)=>{el('ex-state').textContent=s;el('ex-state').classList.toggle('error',error)};
// Reads two files the collector publishes every 15 minutes (no database needed):
// hourly-totals.json (all forecasts per route per hour) and explorer-summary.json (stop rankings).
async function getJSON(url){const r=await fetch(url,{cache:'no-store'});if(!r.ok)throw Error(url+' HTTP '+r.status);return r.json()}
let hourlyFile=null,summaryFile=null;
async function fetchData(days){
 if(!hourlyFile)[hourlyFile,summaryFile]=await Promise.all([getJSON('./data/hourly-totals.json'),getJSON('./data/explorer-summary.json')]);
 const dates=[...new Set(hourlyFile.rows.map(r=>r[0]))].sort().slice(-days);
 const keep=new Set(dates);
 const routes=hourlyFile.rows.filter(r=>keep.has(r[0])).map(r=>({service_date:r[0],service_hour:r[1],route_id:r[2],observation_count:r[3],predictions_5min_late:r[4],predictions_15min_late:r[5]}));
 const stops=(summaryFile.stops[String(days)]||[]).map(s=>({stop_id:s[0],route_id:s[1],observation_count:s[3],predictions_5min_late:s[3],predictions_15min_late:s[4],days_observed:s[5]}));
 return [routes,stops];
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
 const score=a=>sort==='severe'?a.fifteen:a.five;
 arr.sort((a,b)=>score(b)-score(a)||b.five-a.five);
 const title=tab==='routes'?'Routes with the most predicted delays':'Stops with the most predicted delays';
 const sample=arr.slice(0,30),max=Math.max(1,...sample.map(score));
 const metric=a=>fmt(score(a));
 el('ex-results').innerHTML='<h3>'+title+'</h3>'+(!sample.length?'<p class="explorer-empty">No matching observations for this selection.</p>':sample.map(a=>`<div class="explorer-rank"><div><strong>${tab==='routes'?escape(routeLabel(a.id)):'Stop '+escape(a.id)}</strong><small>${tab==='stops'?escape(routeLabel(a.route))+' · ':''}${fmt(a.total)} ${tab==='routes'?'forecasts collected':'notable trip/stop forecasts'} · ${fmt(a.days)} day(s)</small></div><div class="explorer-meter" aria-hidden="true"><span style="width:${Math.max(0,Math.min(100,100*score(a)/max))}%"></span></div><div class="ex-number">${metric(a)}</div></div>`).join(''));
 const raw=tab==='routes'?routeData:stopData;
 state('Loaded '+fmt(raw.length)+' summary rows'+(tab==='stops'&&raw.length>=1000?' (top 1,000 stops only)':''));
 el('ex-disclosure').textContent='Showing up to 30 matches, ranked by '+el('ex-sort').selectedOptions[0].text+'. '+(tab==='routes'?'Route counts are prediction observations (every 15-minute poll), not distinct late buses. ':'Stop counts are trip/stop forecasts whose largest predicted delay reached the threshold during the day, not distinct late buses. Stop IDs may need a GTFS stop-name lookup to display street names. ')+'Data covers only dates and hours with observations.';
}
async function load(){const days=Number(el('ex-days').value);state('Loading route and stop summaries…');try{const [r,s]=await fetchData(days);routeData=r;stopData=s;loadedDays=days;render()}catch(e){state('Unable to load rankings: '+e.message,true);el('ex-results').innerHTML='<p class="explorer-empty">Existing historical records are still available below.</p>'}}
for(const name of ['routes','stops','missed'])el('ex-'+name).addEventListener('click',()=>{tab=name;render()});
el('ex-days').addEventListener('change',load);el('ex-search').addEventListener('input',render);el('ex-sort').addEventListener('change',render);
load();
})();
