"""Sample Swiftly GTFS-RT feeds; publish *prediction observations*, not proven arrivals.
Run in GitHub Actions with SWIFTLY_API_KEY. No secrets are logged or committed.
"""
import csv, io, json, os, sys, urllib.request, urllib.error, urllib.parse, zipfile, hashlib, time
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




# Hourly all-forecast totals per route (Eastern date and hour): the denominators for the trend chart.
# Kept in their own small public file because the database now holds only notable forecasts.
HOURLY = DATA / 'hourly-totals.json'
HOURLY_KEEP_DAYS = 120
ET = ZoneInfo('America/New_York')

def load_hourly():
    try:
        d = json.loads(HOURLY.read_text())
        return {(r[0], r[1], r[2]): r[3:6] for r in d.get('rows', [])}
    except (FileNotFoundError, ValueError, TypeError):
        return None

def update_hourly(hourly, samples, now):
    for x in samples:
        t = datetime.fromisoformat(x['sampled_at_utc']).astimezone(ET)
        k = (t.strftime('%Y-%m-%d'), t.hour, str(x.get('route_id')))
        c = hourly.setdefault(k, [0, 0, 0]); v = _delay(x)
        c[0] += 1; c[1] += int(v is not None and v >= 300); c[2] += int(v is not None and v >= 900)
    first = (now.astimezone(ET) - timedelta(days=HOURLY_KEEP_DAYS)).strftime('%Y-%m-%d')
    rows = sorted([list(k) + v for k, v in hourly.items() if k[0] >= first])
    HOURLY.write_text(json.dumps({'format': 1, 'meaning': 'All forecast observations per route per Eastern '
        'clock hour: [date, hour, route_id, forecasts, predicted 5+ min late, predicted 15+ min late]. '
        'Forecasts, not verified arrivals. Missing hours mean no data was collected, not on-time service.',
        'columns': ['date_et', 'hour_et', 'route_id', 'forecasts', 'over_5_min', 'over_15_min'],
        'rows': rows}, separators=(',', ':')) + '\n')

LATE_SECONDS=300; EARLY_SECONDS=-120; MAX_DAILY_RECORDS=120000


CLASSIFICATION='prediction_only_not_confirmed_arrival'

EXPLORER = DATA / 'explorer-summary.json'
EXPLORER_PERIODS = (1, 7)        # days offered on the website (the site keeps 7 daily files)
EXPLORER_MAX_STOPS = 1000
EXPLORER_RECENT_RECORDS = 500

def write_explorer_summary(now, today, today_path):
    """Small file for the website (replaces the old database queries): stop rankings and the most
    recent notable forecasts, computed from the daily files already published in docs/data."""
    files = sorted(DATA.glob('predictions-????-??-??.json'))[-max(EXPLORER_PERIODS):]
    days = [(f.stem.replace('predictions-', ''), today if f == today_path else load_daily(f)) for f in files]
    stops = {}
    for p in EXPLORER_PERIODS:
        acc = {}
        for date, d in days[-p:]:
            for x in d['samples']:
                v = _delay({'predicted_delay_seconds': x.get('max_delay_seconds', x.get('predicted_delay_seconds'))})
                if v is None or v < LATE_SECONDS:
                    continue
                k = (str(x.get('stop_id')), str(x.get('route_id')))
                a = acc.setdefault(k, [0, 0, 0, set()])
                a[0] += int(x.get('polls') or 1); a[1] += 1; a[2] += int(v >= 900); a[3].add(date)
        ranked = sorted(acc.items(), key=lambda kv: (kv[1][1], kv[1][2]), reverse=True)[:EXPLORER_MAX_STOPS]
        stops[str(p)] = [[k[0], k[1], a[0], a[1], a[2], len(a[3])] for k, a in ranked]
    recent = []
    for date, d in reversed(days):
        recent += d['samples']
        if len(recent) >= EXPLORER_RECENT_RECORDS * 4:
            break
    recent = sorted(recent, key=lambda x: str(x.get('sampled_at_utc', '')), reverse=True)[:EXPLORER_RECENT_RECORDS]
    EXPLORER.write_text(json.dumps({
        'format': 1, 'generated_utc': now.isoformat(timespec='seconds'),
        'meaning': 'Forecast observations, not verified arrivals. Built from the published daily files. '
                   'stops: per period in days, trip/stop forecasts whose largest predicted delay was 5+ minutes late. '
                   'recent: the most recent notable forecasts (5+ min late or 2+ min early).',
        'dates': [d for d, _ in days],
        'stop_columns': ['stop_id', 'route_id', 'polls', 'late_5_min_records', 'late_15_min_records', 'days'],
        'stops': stops,
        'recent_columns': ['sampled_at_utc', 'route_id', 'trip_id', 'stop_id', 'predicted_delay_seconds', 'max_delay_seconds', 'polls'],
        'recent': [[x.get(c) for c in ('sampled_at_utc', 'route_id', 'trip_id', 'stop_id', 'predicted_delay_seconds',
                                       'max_delay_seconds', 'polls')] for x in recent],
    }, separators=(',', ':')) + '\n')

def _delay(x):
    v=x.get('predicted_delay_seconds')
    return v if isinstance(v,(int,float)) and not isinstance(v,bool) else None

def _notable(v):
    return v is not None and (v>=LATE_SECONDS or v<=EARLY_SECONDS)

# Format 3 stores each record as a short array (see "columns") instead of a repeated-key object,
# with route names listed once. Same information, about a fifth of the size.
COLUMNS=['sampled','first_sampled','trip_id','route_id','stop_id','event','delay','max_delay','polls','predicted','method','vehicle']
_EVENT={'arrival':'a','departure':'d'}; _METHOD={'feed_explicit':'e','derived_from_static_schedule':'s','unknown':'u'}

def _epoch(s):
    return int(datetime.fromisoformat(s).timestamp()) if s else None

def _iso(n):
    return datetime.fromtimestamp(n,timezone.utc).isoformat(timespec='seconds') if n is not None else None

def encode_rows(rows):
    routes={}; out=[]
    for x in rows:
        if x.get('route_id') is not None: routes[x['route_id']]=x.get('route_name')
        v=x.get('vehicle_seen_in_same_snapshot')
        out.append([_epoch(x.get('sampled_at_utc')),_epoch(x.get('first_sampled_at_utc')),x.get('trip_id'),x.get('route_id'),
                    x.get('stop_id'),_EVENT.get(x.get('event_type'),x.get('event_type')),x.get('predicted_delay_seconds'),
                    x.get('max_delay_seconds'),x.get('polls'),_epoch(x.get('predicted_time_utc')),
                    _METHOD.get(x.get('delay_method'),x.get('delay_method')),None if v is None else int(bool(v))])
    return routes,out

def decode_rows(d):
    ev={v:k for k,v in _EVENT.items()}; me={v:k for k,v in _METHOD.items()}; routes=d.get('routes',{})
    for r in d.get('rows',[]):
        c=dict(zip(d.get('columns',COLUMNS),r))
        yield {'sampled_at_utc':_iso(c['sampled']),'trip_id':c['trip_id'],'route_id':c['route_id'],
               'route_name':routes.get(c['route_id'],c['route_id']),'stop_id':c['stop_id'],
               'event_type':ev.get(c['event'],c['event']),'predicted_delay_seconds':c['delay'],
               'delay_method':me.get(c['method'],c['method']),'predicted_time_utc':_iso(c['predicted']),
               'vehicle_seen_in_same_snapshot':None if c['vehicle'] is None else bool(c['vehicle']),
               'first_sampled_at_utc':_iso(c['first_sampled']),'polls':c['polls'],'max_delay_seconds':c['max_delay']}

def load_daily(path):
    """Read a daily file in either the old (every poll) or compact (one row per trip/stop/event) format."""
    out={'totals':{'samples':0,'over_5_min':0,'over_15_min':0},'records':{}}
    if not path.exists():
        return {**out,'samples':[]}
    try:
        d=json.loads(path.read_text())
    except (ValueError,TypeError):
        return {**out,'samples':[]}
    if d.get('format') in (2,3):
        out['totals']={**out['totals'],**d.get('totals',{})}
        for x in (decode_rows(d) if d.get('format')==3 else d.get('samples',[])):
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
    routes,packed=encode_rows(sorted(rows,key=lambda x:str(x.get('sampled_at_utc',''))))
    obj={'format':3,'date_utc':date,'source':'Swiftly GTFS-RT trip updates for mta-maryland',
         'meaning':'Forecast observations, not verified arrivals or no-shows. One row per trip, stop and event per day: the latest forecast, how many 15-minute polls saw it, and the largest predicted delay. Only forecasts at least 5 minutes late or 2 minutes early are listed; totals count every poll. The complete raw feed for every poll is archived to the project Google Drive. Times are Unix seconds (UTC).',
         'classification':CLASSIFICATION,'thresholds':{'late_seconds':LATE_SECONDS,'early_seconds':EARLY_SECONDS},
         'totals':day['totals'],'routes':routes,'columns':COLUMNS,'rows':packed}
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
    # All-forecast hourly totals per route (the trend chart's denominators) live in GitHub.
    hourly = load_hourly() or {}
    update_hourly(hourly, samples, now)
    # Daily public files: one row per trip/stop/event per day (latest forecast, plus how many polls saw it
    # and the worst delay), limited to notable forecasts. Every raw feed file is archived to Google Drive,
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
    write_explorer_summary(now, current, daily)
    latest={'last_success_utc':now.isoformat(timespec='seconds'), 'agency':AGENCY,
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
