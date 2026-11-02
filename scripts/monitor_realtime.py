"""Sample Swiftly GTFS-RT feeds; publish *prediction observations*, not proven arrivals.
Run in GitHub Actions with SWIFTLY_API_KEY. No secrets are logged or committed.
"""
import csv, io, json, os, sys, urllib.request, urllib.error, zipfile, hashlib, time
from collections import Counter
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo
from pathlib import Path
from google.transit import gtfs_realtime_pb2

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / 'docs' / 'data'
RAW = ROOT / 'realtime-raw'
AGENCY = 'mta-maryland'
BASE = f'https://api.goswift.ly/real-time/{AGENCY}'
HEADERS = {'Authorization': os.environ['SWIFTLY_API_KEY'].strip(), 'User-Agent': 'BaltimoreTransitAccountability/1.0'}

def fetch(url, headers, timeout, attempts=3):
    """GET with retries: a single slow or busy response should not fail the whole run."""
    for attempt in range(1, attempts + 1):
        try:
            req = urllib.request.Request(url, headers=headers, method='GET')
            with urllib.request.urlopen(req, timeout=timeout) as r:
                payload = r.read()
            if not payload:
                raise ValueError('Empty response')
            return payload
        except urllib.error.HTTPError as exc:
            if exc.code not in (408, 429, 500, 502, 503, 504) or attempt == attempts:
                raise
            print(f'HTTP {exc.code} from {url.split("?")[0]}; retry {attempt}/{attempts - 1}', flush=True)
        except (urllib.error.URLError, TimeoutError, ValueError, ConnectionError) as exc:
            if attempt == attempts:
                raise
            print(f'{type(exc).__name__} from {url.split("?")[0]}; retry {attempt}/{attempts - 1}', flush=True)
        time.sleep(10 * attempt)

def get(url):
    return fetch(url, HEADERS, timeout=45)

_SCHEDULE_BLOB = None

def schedule_blob():
    """Download the static schedule once per run (it was fetched twice)."""
    global _SCHEDULE_BLOB
    if _SCHEDULE_BLOB is None:
        _SCHEDULE_BLOB = fetch('https://feeds.mta.maryland.gov/gtfs/local-bus',
                               {'User-Agent': 'BaltimoreTransitAccountability/1.0'}, timeout=75)
    return _SCHEDULE_BLOB

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
    with zipfile.ZipFile(io.BytesIO(schedule_blob())) as z:
        trips={x['trip_id']:x for x in read_csv(z,'trips.txt')}
        routes={x['route_id']:x for x in read_csv(z,'routes.txt')}
        return trips,routes

def scheduled_stop_times(target_trip_ids):
    """Read only requested trip stop-times from the static GTFS schedule."""
    result = {}
    if not target_trip_ids:
        return result
    with zipfile.ZipFile(io.BytesIO(schedule_blob())) as z:
        with z.open('stop_times.txt') as raw:
            reader = csv.DictReader(io.TextIOWrapper(raw, encoding='utf-8-sig'))
            for row in reader:
                tid = row.get('trip_id')
                if tid in target_trip_ids:
                    key = (tid, row.get('stop_sequence', ''))
                    result[key] = row
    return result


def scheduled_timestamp(service_date, clock, tz=ZoneInfo('America/New_York')):
    """Convert GTFS service-day HH:MM:SS (including 24+ hours) to UTC."""
    if not service_date or not clock:
        return None
    try:
        day = datetime.strptime(service_date, '%Y%m%d').replace(tzinfo=tz)
        hh, mm, ss = map(int, clock.split(':'))
        return (day + timedelta(hours=hh, minutes=mm, seconds=ss)).astimezone(timezone.utc)
    except (ValueError, TypeError):
        return None


def upload_to_supabase(samples):
    """Upsert forecast observations via Supabase REST, using server-only credentials."""
    url = os.environ.get('SUPABASE_URL', '').strip().rstrip('/')
    key = os.environ.get('SUPABASE_SERVICE_ROLE_KEY', '').strip()
    if not url or not key:
        raise RuntimeError('Missing SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY GitHub Actions secret')
    if not url.startswith('https://') or '/' in url[len('https://'):]:
        raise ValueError('SUPABASE_URL must be the HTTPS project base URL')
    rows = []
    for sample in samples:
        canonical = json.dumps(sample, sort_keys=True, separators=(',', ':'))
        rows.append({
            'observed_at': sample['sampled_at_utc'],
            'route_id': sample.get('route_id'),
            'trip_id': sample.get('trip_id'),
            'stop_id': sample.get('stop_id'),
            'delay_seconds': sample.get('predicted_delay_seconds'),
            'observation_type': 'prediction',
            'evidence_status': 'forecast',
            'source': 'swiftly_gtfs_rt',
            'raw_record': sample,
            'record_hash': hashlib.sha256(canonical.encode('utf-8')).hexdigest(),
        })
    endpoint = url + '/rest/v1/mta_observations?on_conflict=record_hash'
    for offset in range(0, len(rows), 250):
        batch = rows[offset:offset + 250]
        payload = json.dumps(batch, separators=(',', ':')).encode('utf-8')
        for attempt in range(3):

            req = urllib.request.Request(endpoint, data=payload, method='POST', headers={
                'apikey': key,
                'Authorization': 'Bearer ' + key,
                'Content-Type': 'application/json',
                'Content-Profile': 'public',
                'Accept-Profile': 'public',
                'Prefer': 'resolution=ignore-duplicates,return=minimal',
                'User-Agent': 'BaltimoreTransitAccountability/1.0',
            })

            try:
                with urllib.request.urlopen(req, timeout=60) as response:
                    if response.status not in (200, 201, 204):
                        raise RuntimeError('Supabase unexpected HTTP status ' + str(response.status))
                break
            except urllib.error.HTTPError as exc:
                if attempt == 2 or exc.code not in (429, 500, 502, 503, 504):
                    details = exc.read().decode("utf-8", errors="replace")
                    raise RuntimeError(
                        f"Supabase upload failed (HTTP {exc.code}): "
                        f"{details[:1000]}"
                    ) from None
                time.sleep(2 ** attempt)
            except urllib.error.URLError:
                if attempt == 2:
                    raise RuntimeError('Supabase upload failed (network error)') from None
                time.sleep(2 ** attempt)
    print(f'Supabase upload completed: {len(rows)} forecast observations submitted (duplicates ignored)')

LATE_SECONDS=300; EARLY_SECONDS=-120; MAX_DAILY_RECORDS=120000
CLASSIFICATION='prediction_only_not_confirmed_arrival'

def _delay(x):
    v=x.get('predicted_delay_seconds')
    return v if isinstance(v,(int,float)) and not isinstance(v,bool) else None

def _notable(v):
    return v is not None and (v>=LATE_SECONDS or v<=EARLY_SECONDS)

def load_daily(path):
    """Read a daily file in either the old (every poll) or compact (one row per trip/stop/event) format."""
    out={'totals':{'samples':0,'over_5_min':0,'over_15_min':0},'records':{}}
    if not path.exists():
        return {**out,'samples':[]}
    try:
        d=json.loads(path.read_text())
    except (ValueError,TypeError):
        return {**out,'samples':[]}
    if d.get('format')==2:
        out['totals']={**out['totals'],**d.get('totals',{})}
        for x in d.get('samples',[]):
            out['records'][(x.get('trip_id'),x.get('stop_id'),x.get('event_type'))]=x
    else:
        merge_samples(out,d.get('samples',[]))
    out['samples']=list(out['records'].values())
    return out

def merge_samples(day,samples):
    t=day['totals']; recs=day['records']
    for x in samples:
        v=_delay(x)
        t['samples']+=1
        if v is not None and v>=300: t['over_5_min']+=1
        if v is not None and v>=900: t['over_15_min']+=1
        key=(x.get('trip_id'),x.get('stop_id'),x.get('event_type'))
        prev=recs.get(key)
        if prev is None and not _notable(v):
            continue
        row={k:x.get(k) for k in ('sampled_at_utc','trip_id','route_id','route_name','stop_id','event_type','predicted_delay_seconds','delay_method','predicted_time_utc','vehicle_seen_in_same_snapshot')}
        if prev:
            row['first_sampled_at_utc']=prev.get('first_sampled_at_utc') or prev.get('sampled_at_utc')
            row['polls']=prev.get('polls',1)+1
            pmax=_delay({'predicted_delay_seconds':prev.get('max_delay_seconds',prev.get('predicted_delay_seconds'))})
            row['max_delay_seconds']=max([d for d in (pmax,v) if d is not None],default=None)
        else:
            row['first_sampled_at_utc']=x.get('sampled_at_utc'); row['polls']=1; row['max_delay_seconds']=v
        recs[key]=row
    day['samples']=list(recs.values())

def write_daily(path,date,day):
    rows=day['samples']
    if len(rows)>MAX_DAILY_RECORDS:  # safety cap: keep the largest delays/early departures
        rows=sorted(rows,key=lambda x:abs(_delay({'predicted_delay_seconds':x.get('max_delay_seconds')}) or 0),reverse=True)[:MAX_DAILY_RECORDS]
    obj={'format':2,'date_utc':date,'source':'Swiftly GTFS-RT trip updates for mta-maryland',
         'meaning':'Forecast observations, not verified arrivals or no-shows. One row per trip, stop and event per day: the latest forecast, how many 15-minute polls saw it, and the largest predicted delay. Only forecasts at least 5 minutes late or 2 minutes early are listed; totals count every poll. The complete record of every poll is kept in the project database.',
         'classification':CLASSIFICATION,'thresholds':{'late_seconds':LATE_SECONDS,'early_seconds':EARLY_SECONDS},
         'totals':day['totals'],'samples':sorted(rows,key=lambda x:str(x.get('sampled_at_utc','')))}
    path.write_text(json.dumps(obj,separators=(',',':'))+'\n')

def main():
    if DATA.exists() and not DATA.is_dir():
        raise RuntimeError("docs/data exists as a FILE; delete that file in GitHub before running the collector")
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
    samples=[]; seen=set(); vehicle_trip_ids=set()
    for e in positions.entity:
        if e.HasField('vehicle') and e.vehicle.HasField('trip') and e.vehicle.trip.trip_id:
            vehicle_trip_ids.add(e.vehicle.trip.trip_id)

    relevant_trip_ids = {e.trip_update.trip.trip_id for e in updates.entity
                         if e.HasField('trip_update') and e.trip_update.trip.trip_id}
    # Read scheduled stop times once, only for trips present in this feed.
    schedule = scheduled_stop_times(relevant_trip_ids)
    diagnostics = {'stop_updates': 0, 'with_event_time': 0, 'with_explicit_delay': 0,
                   'derived_delay': 0, 'without_delay': 0, 'without_stop_id': 0}
    for e in updates.entity:
        if not e.HasField('trip_update'):
            continue
        u=e.trip_update; tid=u.trip.trip_id
        if not tid:
            continue
        static=trips.get(tid,{})
        rid=u.trip.route_id or static.get('route_id','')
        route=routes.get(rid,{})
        for stop in u.stop_time_update:
            diagnostics['stop_updates'] += 1
            if not stop.stop_id:
                diagnostics['without_stop_id'] += 1
                continue
            # Keep an arrival/departure forecast even when no delay field exists.
            kind = 'arrival' if stop.HasField('arrival') else ('departure' if stop.HasField('departure') else None)
            if not kind:
                continue
            ev = getattr(stop, kind)
            has_time = ev.HasField('time')
            has_delay = ev.HasField('delay')
            if not (has_time or has_delay):
                continue
            if has_time:
                diagnostics['with_event_time'] += 1
            if has_delay:
                diagnostics['with_explicit_delay'] += 1
            predicted_time = datetime.fromtimestamp(ev.time, timezone.utc) if has_time else None
            delay = int(ev.delay) if has_delay else None
            delay_method = 'feed_explicit' if has_delay else 'unknown'
            if delay is None and predicted_time is not None:
                scheduled_row = schedule.get((tid, str(stop.stop_sequence))) if stop.HasField('stop_sequence') else None
                scheduled_clock = scheduled_row.get(kind + '_time') if scheduled_row else None
                # GTFS-RT start_date is essential: never guess the service day.
                service_date = u.trip.start_date if u.trip.HasField('start_date') else None
                scheduled_utc = scheduled_timestamp(service_date, scheduled_clock)
                if scheduled_utc is not None:
                    delay = round((predicted_time - scheduled_utc).total_seconds())
                    delay_method = 'derived_from_static_schedule'
                    diagnostics['derived_delay'] += 1
            if delay is None:
                diagnostics['without_delay'] += 1
            key=(tid, stop.stop_id, kind)
            if key in seen:
                continue
            seen.add(key)
            samples.append({'sampled_at_utc': now.isoformat(timespec='seconds'),
                'trip_id': tid, 'route_id': rid,
                'route_name': route.get('route_short_name') or route.get('route_long_name') or rid,
                'stop_id': stop.stop_id, 'event_type': kind,
                'predicted_delay_seconds': delay, 'delay_method': delay_method,
                'predicted_time_utc': predicted_time.isoformat() if predicted_time else None,
                'vehicle_seen_in_same_snapshot': tid in vehicle_trip_ids,
                'classification': 'prediction_only_not_confirmed_arrival'})
    print('Feed diagnostics: ' + json.dumps(diagnostics, sort_keys=True))
    # Archive to Supabase. If it fails (database full or briefly unavailable), keep going so the
    # public files still update, but flag it loudly in the run and in realtime-status.json.
    supabase_ok = True
    try:
        upload_to_supabase(samples)
    except Exception as exc:
        supabase_ok = False
        print(f'::warning title=Supabase upload failed::{str(exc)[:500]}', flush=True)
    # Daily public files: one row per trip/stop/event per day (latest forecast, plus how many polls saw it
    # and the worst delay), limited to notable forecasts. Every raw sample is already stored in Supabase,
    # and exact daily totals are kept so the 7-day counts stay accurate. This keeps each file well under
    # GitHub's 100 MB limit and small enough for the dashboard to load on a phone.
    date=now.strftime('%Y-%m-%d'); daily=DATA/f'predictions-{date}.json'
    current=load_daily(daily)
    merge_samples(current, samples)
    write_daily(daily, date, current)
    history_totals={'samples':0,'over_5_min':0,'over_15_min':0}; published_days=[]
    for f in sorted(DATA.glob('predictions-????-??-??.json'))[-7:]:
        d=current if f==daily else load_daily(f)
        for k in history_totals: history_totals[k]+=d['totals'].get(k,0)
        published_days.append({'date_utc':f.stem.replace('predictions-',''),'records':len(d['samples']),'bytes':f.stat().st_size})
    latest={'last_success_utc':now.isoformat(timespec='seconds'), 'agency':AGENCY,
      'supabase_archive_ok_this_run': supabase_ok,
      'feed_timestamp_utc':datetime.fromtimestamp(updates.header.timestamp,timezone.utc).isoformat() if updates.header.HasField('timestamp') else None,
      'trip_updates_entities':sum(e.HasField('trip_update') for e in updates.entity),
      'vehicle_positions_entities':sum(e.HasField('vehicle') for e in positions.entity),
      'sampled_prediction_count_this_run':len(samples),
      'samples_without_computable_delay_this_run':sum(x['predicted_delay_seconds'] is None for x in samples),
      'prediction_samples_last_7_days':history_totals['samples'],
      'predicted_over_5_min_samples_last_7_days':history_totals['over_5_min'],
      'predicted_over_15_min_samples_last_7_days':history_totals['over_15_min'],
      'published_days':published_days,
      'verified_late_arrivals':None,'verified_missed_trips':None,
      'methodology':'Forecast observations; delays may be explicit, derived from GTFS stop_times and start_date, or unknown. Same trip/stop may recur across polls. No-show detection is not enabled.',
      'latest_prediction_samples':sorted(samples,key=lambda x: x['predicted_delay_seconds'] if x['predicted_delay_seconds'] is not None else -999999,reverse=True)[:60]}
    (DATA/'realtime-status.json').write_text(json.dumps(latest,indent=2)+'\n')
    print(f'OK: {len(samples)} prediction samples, {latest["vehicle_positions_entities"]} vehicle entities, {latest["trip_updates_entities"]} trip update entities')

if __name__=='__main__':
    if not os.environ.get('SWIFTLY_API_KEY'):
        sys.exit('SWIFTLY_API_KEY GitHub Actions secret is missing')
    main()
