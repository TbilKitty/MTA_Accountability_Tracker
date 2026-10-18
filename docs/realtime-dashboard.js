(async function(){
 const $=id=>document.getElementById(id);
 const tbody=$('realtime-observations');
 if(!tbody)return;
 try{
   const response=await fetch('./data/realtime-status.json',{cache:'no-store'});
   if(!response.ok)throw Error('No successful monitor run published yet');
   const d=await response.json();
   $('rt-updated').textContent=d.last_success_utc?new Date(d.last_success_utc).toLocaleString():'Unavailable';
   $('rt-vehicles').textContent=(d.vehicle_positions_entities??'—').toLocaleString();
   $('rt-predictions').textContent=(d.prediction_samples_last_7_days??'—').toLocaleString();
   $('rt-5min').textContent=(d.predicted_over_5_min_samples_last_7_days??'—').toLocaleString();
   $('rt-15min').textContent=(d.predicted_over_15_min_samples_last_7_days??'—').toLocaleString();
   tbody.replaceChildren();
   const list=d.latest_prediction_samples||[];
   if(!list.length){const tr=document.createElement('tr');const td=document.createElement('td');td.colSpan=5;td.textContent='No delay predictions in the latest snapshot.';tr.append(td);tbody.append(tr)}
   for(const x of list){const tr=document.createElement('tr');for(const v of [x.route_name||x.route_id,x.trip_id,x.stop_id,Math.round(x.predicted_delay_seconds/60)+' min',x.vehicle_seen_in_same_snapshot?'Yes':'No']){const td=document.createElement('td');td.textContent=String(v??'');tr.append(td)}tbody.append(tr)}
 }catch(err){$('rt-updated').textContent='Not yet running';tbody.replaceChildren();const tr=document.createElement('tr'),td=document.createElement('td');td.colSpan=5;td.textContent='Waiting for the first successful GitHub Actions monitoring run.';tr.append(td);tbody.append(tr)}
})();
