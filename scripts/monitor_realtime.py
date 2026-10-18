"""Sample Swiftly GTFS-RT feeds; publish *prediction observations*, not proven arrivals.
Run in GitHub Actions with SWIFTLY_API_KEY. No secrets are logged or committed.
"""
import csv, io, json, os, sys, urllib.request, urllib.error, zipfile
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from google.transit import gtfs_realtime_pb2

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / 'docs' / 'data'
RAW = ROOT / 'realtime-raw'
AGENCY = 'mta-maryland'
BASE = f'https://api.goswift.ly/real-time/{AGENCY}'
HEADERS = {'Authorization': os.environ['SWIFTLY_API_KEY'].strip(), 'User-Agent': 'BaltimoreTransitAccountability/1.0'}

def get(url):
    req = urllib.request.Request(url, headers=HEADERS, method='GET')
    with urllib.request.urlopen(req, timeout=45) as r:
        payload = r.read()
        if not payload: raise ValueError('Empty response')
        return payload

def decode(payload):
    msg = gtfs_realtime_pb2.FeedMessage()
    msg.ParseFromString(payload)
    if not msg.HasField('header'): raise ValueError('Not a GTFS-RT FeedMessage')
    return msg

def read_csv(z, filename):
    with z.open(filename) as f:
        return list(csv.DictReader(io.TextIOWrapper(f, encoding='utf-8-sig')))

def get_schedule():
    # Use same static feed as real-time bus mode; refresh for each scheduled run.
    url='https://feeds.mta.maryland.gov/gtfs/local-bus'
    with urllib.request.urlopen(urllib.request.Request(url, headers={'User-Agent':'BaltimoreTransitAccountability/1.0'}),timeout=75) as r:
        blob=r.read()
    with zipfile.ZipFile(io.BytesIO(blob)) as z:
        trips={x['trip_id']:x for x in read_csv(z,'trips.txt')}
        routes={x['route_id']:x for x in read_csv(z,'routes.txt')}
        # stop_times may be large; only use rows for sampled trip IDs after realtime fetch.
        return trips,routes

def main():
    DATA.mkdir(parents=True,exist_ok=True); RAW.mkdir(parents=True,exist_ok=True)
    now=datetime.now(timezone.utc)
    stamp=now.strftime('%Y%m%dT%H%M%SZ')
    feeds={}
    for typ in ('gtfs-rt-trip-updates','gtfs-rt-vehicle-positions'):
        payload=get(f'{BASE}/{typ}')
        feeds[typ]=decode(payload)
        (RAW/f'{stamp}_{typ}.pb').write_bytes(payload)
    trips,routes=get_schedule()
    updates=feeds['gtfs-rt-trip-updates']; positions=feeds['gtfs-rt-vehicle-positions']
    samples=[]; seen=set(); trip_ids=set(); vehicle_trip_ids=set()
    for e in positions.entity:
        if e.HasField('vehicle') and e.vehicle.HasField('trip') and e.vehicle.trip.trip_id:
            vehicle_trip_ids.add(e.vehicle.trip.trip_id)
    for e in updates.entity:
        if not e.HasField('trip_update'): continue
        u=e.trip_update; tid=u.trip.trip_id
        if not tid: continue
        trip_ids.add(tid)
        static=trips.get(tid,{})
        rid=u.trip.route_id or static.get('route_id','')
        route=routes.get(rid,{})
        for stop in u.stop_time_update:
            if not stop.stop_id: continue
            # Prediction event.time is not proof of actual arrival. Delay can be observed as prediction only.
            ev=stop.arrival if stop.HasField('arrival') else (stop.departure if stop.HasField('departure') else None)
            if ev is None or not ev.HasField('delay'): continue
            delay=int(ev.delay)
            key=(tid,stop.stop_id)
            if key in seen: continue
            seen.add(key)
            samples.append({'sampled_at_utc':now.isoformat(timespec='seconds'), 'trip_id':tid,
                'route_id':rid,'route_name':route.get('route_short_name') or route.get('route_long_name') or rid,
                'stop_id':stop.stop_id,'predicted_delay_seconds':delay,
                'predicted_time_utc':datetime.fromtimestamp(ev.time,timezone.utc).isoformat() if ev.HasField('time') else None,
                'vehicle_seen_in_same_snapshot':tid in vehicle_trip_ids,
                'classification':'prediction_only_not_confirmed_arrival'})
    # Daily per-sample summaries avoid publishing vehicle location histories or identifiers.
    date=now.strftime('%Y-%m-%d'); daily=DATA/f'predictions-{date}.json'
    previous=[]
    if daily.exists():
        try: previous=json.loads(daily.read_text()).get('samples',[])
        except (ValueError,TypeError): previous=[]
    previous.extend(samples)
    # bound public daily file; sample at most one prediction per trip/stop per run
    obj={'date_utc':date,'source':'Swiftly GTFS-RT trip updates for mta-maryland',
         'meaning':'These are forecast delays at collection time, not measured arrivals, verified lateness, or no-shows.',
         'samples':previous}
    daily.write_text(json.dumps(obj,separators=(',',':'))+'\n')
    history=[]
    for f in sorted(DATA.glob('predictions-????-??-??.json'))[-7:]:
        try:
            d=json.loads(f.read_text()); history.extend(d.get('samples',[]))
        except (ValueError,TypeError): pass
    latest={'last_success_utc':now.isoformat(timespec='seconds'), 'agency':AGENCY,
      'feed_timestamp_utc':datetime.fromtimestamp(updates.header.timestamp,timezone.utc).isoformat() if updates.header.HasField('timestamp') else None,
      'trip_updates_entities':sum(e.HasField('trip_update') for e in updates.entity),
      'vehicle_positions_entities':sum(e.HasField('vehicle') for e in positions.entity),
      'sampled_prediction_count_this_run':len(samples),
      'prediction_samples_last_7_days':len(history),
      'predicted_over_5_min_samples_last_7_days':sum(x['predicted_delay_seconds']>=300 for x in history),
      'predicted_over_15_min_samples_last_7_days':sum(x['predicted_delay_seconds']>=900 for x in history),
      'verified_late_arrivals':None,'verified_missed_trips':None,
      'methodology':'Forecast delay samples; the same trip/stop may appear in multiple polls. Counts are observations, not unique late buses. No-show detection is not enabled.',
      'latest_prediction_samples':sorted(samples,key=lambda x:x['predicted_delay_seconds'],reverse=True)[:60]}
    (DATA/'realtime-status.json').write_text(json.dumps(latest,indent=2)+'\n')
    print(f'OK: {len(samples)} prediction samples, {latest["vehicle_positions_entities"]} vehicle entities, {latest["trip_updates_entities"]} trip update entities')

if __name__=='__main__':
    if not os.environ.get('SWIFTLY_API_KEY'):
        sys.exit('SWIFTLY_API_KEY GitHub Actions secret is missing')
    main()
