"""Systemwide school-commute service watcher for MTA Maryland local bus.

Runs once per school-commute window (AM or PM). For the whole window it polls
Swiftly GTFS-RT vehicle positions every ~30 seconds (trip updates every ~2
minutes) and compares what buses actually did against the published GTFS
schedule, for every route at once.

What it measures (aggregate only; no rider is tracked):
  * observed stop times at scheduled timepoints -> on-time / early / late,
    using MTA's own on-time window from config/settings.json
  * trips MTA's own feed marked CANCELED
  * scheduled trips with no real-time record at all (labelled "no record",
    NOT "no-show": a bus with a broken GPS unit looks the same)
  * stops a trip was flagged to SKIP (detours)

It cannot see whether a bus passed a waiting rider. Pass-ups need rider
reports; this data shows when and where the bus was.

Usage:
  python scripts/school_commute_watch.py --window auto|am|pm [--date YYYY-MM-DD]
  python scripts/school_commute_watch.py --summarize-only
"""
import argparse, csv, gzip, io, json, math, os, statistics, sys, time, urllib.error, urllib.request, zipfile
from collections import defaultdict
from datetime import datetime, timedelta, timezone, date as date_cls
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
CONFIG = json.loads((ROOT / 'config' / 'settings.json').read_text())
SC = CONFIG.get('school_commute', {})
TZ = ZoneInfo(CONFIG.get('agency_timezone', 'America/New_York'))
WINDOWS = SC.get('windows', {'am': ['06:00', '09:30'], 'pm': ['14:00', '17:30']})
POLL_SECONDS = int(SC.get('poll_seconds', 30))
TRIP_UPDATE_EVERY = int(SC.get('trip_update_every_polls', 4))
GRACE_MIN = int(SC.get('grace_minutes', 20))
GAP_SECONDS = int(SC.get('coverage_gap_seconds', 300))
MAX_INTERP_SECONDS = int(SC.get('max_interpolation_seconds', 180))
EARLY_S = int(CONFIG.get('on_time_early_minutes', 2)) * 60
LATE_S = int(CONFIG.get('on_time_late_minutes', 7)) * 60
SEVERE_S = int(SC.get('severe_late_minutes', 15)) * 60
NO_SCHOOL = set(SC.get('no_school_dates', []))
GTFS_URL = CONFIG.get('gtfs_url', 'https://feeds.mta.maryland.gov/gtfs/local-bus')
RT_BASE = 'https://api.goswift.ly/real-time/' + CONFIG.get('agency_key', 'mta-maryland')
UA = 'BaltimoreTransitAccountability/1.0'
PUBLIC = ROOT / 'docs' / 'data' / 'school-commute'
RAW = ROOT / 'data' / 'school-commute-raw'

RAW_FIELDS = ['service_date', 'window', 'route_id', 'route_name', 'trip_id', 'direction_id',
              'stop_id', 'stop_sequence', 'timepoint', 'scheduled_local', 'actual_local',
              'delay_seconds', 'outcome', 'time_method', 'uncertainty_seconds']


# ---------------------------------------------------------------- utilities
def http_get(url, headers=None, timeout=60):
    req = urllib.request.Request(url, headers={'User-Agent': UA, **(headers or {})})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        payload = r.read()
    if not payload:
        raise ValueError('empty response from ' + url)
    return payload


def gtfs_seconds(clock):
    h, m, s = (int(x) for x in clock.strip().split(':'))
    return h * 3600 + m * 60 + s


def hhmm_seconds(text):
    h, m = (int(x) for x in text.split(':'))
    return h * 3600 + m * 60


def local_clock(service_day, secs):
    return (datetime.combine(service_day, datetime.min.time(), TZ) + timedelta(seconds=secs)).strftime('%Y-%m-%d %H:%M:%S')


def haversine_m(lat1, lon1, lat2, lon2):
    p = math.pi / 180
    a = (math.sin((lat2 - lat1) * p / 2) ** 2
         + math.cos(lat1 * p) * math.cos(lat2 * p) * math.sin((lon2 - lon1) * p / 2) ** 2)
    return 12742000 * math.asin(math.sqrt(a))


def csv_rows(z, name):
    if name not in z.namelist():
        return
    with z.open(name) as f:
        yield from csv.DictReader(io.TextIOWrapper(f, encoding='utf-8-sig'))


# ----------------------------------------------------------- static schedule
def active_service_ids(z, day):
    ymd = day.strftime('%Y%m%d')
    weekday = ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday'][day.weekday()]
    active = set()
    for r in csv_rows(z, 'calendar.txt'):
        if r['start_date'] <= ymd <= r['end_date'] and r.get(weekday) == '1':
            active.add(r['service_id'])
    for r in csv_rows(z, 'calendar_dates.txt'):
        if r['date'] == ymd:
            if r['exception_type'] == '1':
                active.add(r['service_id'])
            elif r['exception_type'] == '2':
                active.discard(r['service_id'])
    return active


def load_schedule(gtfs_zip_bytes, day, win_start_s, win_end_s):
    """Return {trip_id: trip} for trips with at least one timed stop inside the window."""
    with zipfile.ZipFile(io.BytesIO(gtfs_zip_bytes)) as z:
        services = active_service_ids(z, day)
        routes = {r['route_id']: r for r in csv_rows(z, 'routes.txt')}
        trips = {}
        for r in csv_rows(z, 'trips.txt'):
            if r['service_id'] in services:
                route = routes.get(r['route_id'], {})
                trips[r['trip_id']] = {
                    'trip_id': r['trip_id'], 'route_id': r['route_id'],
                    'route_name': route.get('route_short_name') or route.get('route_long_name') or r['route_id'],
                    'direction_id': r.get('direction_id', ''), 'stops': []}
        for r in csv_rows(z, 'stop_times.txt'):
            trip = trips.get(r['trip_id'])
            if trip is None:
                continue
            clock = (r.get('arrival_time') or r.get('departure_time') or '').strip()
            trip['stops'].append({
                'seq': int(r['stop_sequence']), 'stop_id': r['stop_id'],
                'sched': gtfs_seconds(clock) if clock else None,
                # GTFS: empty timepoint column means "exact" when a time is given.
                'timepoint': (r.get('timepoint', '') or ('1' if clock else '0')).strip() == '1' and bool(clock)})
        stops = {r['stop_id']: {'name': r.get('stop_name', ''), 'lat': float(r['stop_lat']), 'lon': float(r['stop_lon'])}
                 for r in csv_rows(z, 'stops.txt') if r.get('stop_lat') and r.get('stop_lon')}
    selected = {}
    for tid, trip in trips.items():
        trip['stops'].sort(key=lambda s: s['seq'])
        timed = [s['sched'] for s in trip['stops'] if s['sched'] is not None]
        if not timed or max(timed) < win_start_s or min(timed) > win_end_s:
            continue
        trip['index_by_seq'] = {s['seq']: i for i, s in enumerate(trip['stops'])}
        trip['index_by_stop'] = {}
        for i, s in enumerate(trip['stops']):
            trip['index_by_stop'].setdefault(s['stop_id'], i)
        selected[tid] = trip
    return selected, stops


# ------------------------------------------------------- real-time tracking
class TripTracker:
    """Turns a stream of vehicle positions into per-stop passage times."""

    def __init__(self, trip):
        self.trip = trip
        self.reached = {}          # stop index -> (epoch seconds, method, uncertainty)
        self.last_idx = None       # highest stop index known reached
        self.last_t = None
        self.seen = False
        self.canceled = False
        self.skipped = set()       # stop indexes the feed marked SKIPPED

    def observe(self, idx, stopped_at, t):
        """idx: index of the vehicle's current/next stop. stopped_at: at that stop now."""
        self.seen = True
        upto = idx if stopped_at else idx - 1
        if self.last_idx is None and upto < 0:
            # Approaching the first stop: a baseline, so the first passage gets a tight time.
            self.last_idx, self.last_t = -1, t
            return
        if self.last_idx is None:
            # First sighting: earlier stops were passed at an unknown time.
            if stopped_at:
                self.reached[idx] = (t, 'stopped_at', 0)
            self.last_idx, self.last_t = upto, t
            return
        if upto < self.last_idx:
            return  # GPS jitter backwards; ignore
        if upto == self.last_idx:
            # Still hasn't passed the next stop as of t: tighten the bound.
            self.last_t = max(self.last_t, t)
            return
        span = t - self.last_t
        steps = upto - self.last_idx + (0 if stopped_at else 1)
        for k, i in enumerate(range(self.last_idx + 1, upto + 1), start=1):
            if stopped_at and i == upto:
                self.reached[i] = (t, 'stopped_at', 0)
            else:
                self.reached[i] = (round(self.last_t + span * k / steps), 'interpolated', span)
        self.last_idx, self.last_t = upto, t


def vehicle_stop_index(v, trip, stops_ll, after_idx):
    """Locate a vehicle on its trip. Returns (index, stopped_at) or None."""
    from google.transit import gtfs_realtime_pb2 as rt
    stopped = v.HasField('current_status') and v.current_status == rt.VehiclePosition.STOPPED_AT
    if v.HasField('current_stop_sequence') and v.current_stop_sequence in trip['index_by_seq']:
        return trip['index_by_seq'][v.current_stop_sequence], stopped
    if v.stop_id and v.stop_id in trip['index_by_stop']:
        return trip['index_by_stop'][v.stop_id], stopped
    if v.HasField('position'):
        # Fallback: nearest stop on this trip within 40 m, at or after progress so far.
        lat, lon = v.position.latitude, v.position.longitude
        best = None
        for i in range(max(after_idx or 0, 0), len(trip['stops'])):
            st = stops_ll.get(trip['stops'][i]['stop_id'])
            if st:
                d = haversine_m(lat, lon, st['lat'], st['lon'])
                if d <= 40 and (best is None or d < best[1]):
                    best = (i, d)
        if best:
            return best[0], True
    return None


class Watcher:
    def __init__(self, trips, stops_ll, service_day, window, fetch):
        self.trips, self.stops_ll, self.day, self.window, self.fetch = trips, stops_ll, service_day, window, fetch
        self.trackers = {tid: TripTracker(t) for tid, t in trips.items()}
        self.polls_ok = []         # epoch seconds of successful vehicle polls
        self.errors = []
        self.vehicles_seen = set()
        self.vehicles_unmatched = set()

    def poll(self, now_epoch, with_trip_updates):
        from google.transit import gtfs_realtime_pb2 as rt
        try:
            feed = rt.FeedMessage()
            feed.ParseFromString(self.fetch('gtfs-rt-vehicle-positions'))
        except Exception as exc:  # keep running; gaps are recorded, not hidden
            self.errors.append({'at': now_epoch, 'feed': 'vehicle-positions', 'error': str(exc)[:200]})
            return
        header_t = feed.header.timestamp or now_epoch
        self.polls_ok.append(now_epoch)
        for e in feed.entity:
            if not e.HasField('vehicle'):
                continue
            v = e.vehicle
            vid = v.vehicle.id or e.id
            self.vehicles_seen.add(vid)
            tid = v.trip.trip_id if v.HasField('trip') else ''
            tracker = self.trackers.get(tid)
            if tracker is None:
                if tid:
                    self.vehicles_unmatched.add(vid)
                continue
            loc = vehicle_stop_index(v, tracker.trip, self.stops_ll, tracker.last_idx)
            if loc is None:
                tracker.seen = True
                continue
            tracker.observe(loc[0], loc[1], v.timestamp or header_t)
        if with_trip_updates:
            try:
                tu = rt.FeedMessage()
                tu.ParseFromString(self.fetch('gtfs-rt-trip-updates'))
            except Exception as exc:
                self.errors.append({'at': now_epoch, 'feed': 'trip-updates', 'error': str(exc)[:200]})
                return
            for e in tu.entity:
                if not e.HasField('trip_update'):
                    continue
                u = e.trip_update
                tracker = self.trackers.get(u.trip.trip_id)
                if tracker is None:
                    continue
                if u.trip.schedule_relationship == rt.TripDescriptor.CANCELED:
                    tracker.canceled = True
                for s in u.stop_time_update:
                    if s.schedule_relationship == rt.TripUpdate.StopTimeUpdate.SKIPPED:
                        i = None
                        if s.HasField('stop_sequence'):
                            i = tracker.trip['index_by_seq'].get(s.stop_sequence)
                        if i is None and s.stop_id:
                            i = tracker.trip['index_by_stop'].get(s.stop_id)
                        if i is not None:
                            tracker.skipped.add(i)

    def covered(self, epoch):
        """True if a successful poll happened within GAP_SECONDS on both sides of epoch."""
        before = [t for t in self.polls_ok if t <= epoch]
        after = [t for t in self.polls_ok if t >= epoch]
        return bool(before and after and epoch - before[-1] <= GAP_SECONDS and after[0] - epoch <= GAP_SECONDS)

    def results(self, win_start_s, win_end_s):
        """One row per scheduled stop event in the window (timepoints, or all timed stops)."""
        midnight = datetime.combine(self.day, datetime.min.time(), TZ).timestamp()
        events = []
        for tid, tr in self.trackers.items():
            trip = tr.trip
            has_tp = any(s['timepoint'] for s in trip['stops'])
            for i, s in enumerate(trip['stops']):
                if s['sched'] is None or not (win_start_s <= s['sched'] <= win_end_s):
                    continue
                if has_tp and not s['timepoint']:
                    continue
                sched_epoch = midnight + s['sched']
                row = {'service_date': self.day.isoformat(), 'window': self.window,
                       'route_id': trip['route_id'], 'route_name': trip['route_name'], 'trip_id': tid,
                       'direction_id': trip['direction_id'], 'stop_id': s['stop_id'], 'stop_sequence': s['seq'],
                       'timepoint': int(s['timepoint']), 'scheduled_local': local_clock(self.day, s['sched']),
                       'actual_local': '', 'delay_seconds': '', 'time_method': '', 'uncertainty_seconds': ''}
                if not self.covered(sched_epoch):
                    row['outcome'] = 'not_monitored'
                elif tr.canceled and not tr.seen:
                    row['outcome'] = 'canceled'
                elif i in tr.skipped:
                    row['outcome'] = 'skipped'
                elif not tr.seen:
                    row['outcome'] = 'no_realtime_record'
                elif i in tr.reached:
                    t, method, unc = tr.reached[i]
                    delay = round(t - sched_epoch)
                    row.update(actual_local=datetime.fromtimestamp(t, TZ).strftime('%Y-%m-%d %H:%M:%S'),
                               delay_seconds=delay, time_method=method, uncertainty_seconds=unc)
                    if unc > MAX_INTERP_SECONDS:
                        row['outcome'] = 'observed_imprecise'
                    elif delay < -EARLY_S:
                        row['outcome'] = 'early'
                    elif delay <= LATE_S:
                        row['outcome'] = 'on_time'
                    elif delay <= SEVERE_S:
                        row['outcome'] = 'late'
                    else:
                        row['outcome'] = 'severely_late'
                elif tr.last_idx is not None and i > tr.last_idx:
                    # Tracking stopped before this stop (trip short-turned, or GPS lost).
                    row['outcome'] = 'trip_seen_stop_not_reached'
                else:
                    row['outcome'] = 'trip_seen_stop_unobserved'
                events.append(row)
        return events


# --------------------------------------------------------------- summaries
MEASURED = ('early', 'on_time', 'late', 'severely_late')


def pct(n, d):
    return round(100 * n / d, 1) if d else None


def summarize_events(events):
    out = defaultdict(int)
    delays = []
    for e in events:
        out[e['outcome']] += 1
        if e['outcome'] in MEASURED:
            delays.append(int(e['delay_seconds']))
    measured = sum(out[k] for k in MEASURED)
    missing = out['canceled'] + out['no_realtime_record']
    monitored = len(events) - out['not_monitored']
    return {
        'scheduled_stop_events': len(events),
        'monitored_stop_events': monitored,
        'measured_stop_events': measured,
        'on_time': out['on_time'], 'early': out['early'], 'late_7_to_15_min': out['late'],
        'late_over_15_min': out['severely_late'],
        'canceled_by_mta': out['canceled'], 'no_realtime_record': out['no_realtime_record'],
        'skipped_stops': out['skipped'],
        'pct_on_time': pct(out['on_time'], measured),
        'pct_early': pct(out['early'], measured),
        'pct_late_over_7_min': pct(out['late'] + out['severely_late'], measured),
        'pct_late_over_15_min': pct(out['severely_late'], measured),
        # Share of monitored scheduled stops where the bus was 15+ min late, canceled, or left no record.
        'pct_failed_15min_or_missing': pct(out['severely_late'] + missing, measured + missing),
        'median_delay_min': round(statistics.median(delays) / 60, 1) if delays else None,
    }


def trip_counts(events):
    by_trip = defaultdict(set)
    for e in events:  # trip_ids repeat every day, so key by date and window too
        by_trip[(e['service_date'], e['window'], e['trip_id'])].add(e['outcome'])
    c = defaultdict(int)
    for outs in by_trip.values():
        if outs <= {'not_monitored'}:
            c['not_monitored'] += 1
        elif 'canceled' in outs:
            c['canceled'] += 1
        elif 'no_realtime_record' in outs:
            c['no_realtime_record'] += 1
        else:
            c['operated'] += 1
    return {'scheduled_trips': len(by_trip), 'trips_operated': c['operated'],
            'trips_canceled_by_mta': c['canceled'], 'trips_no_realtime_record': c['no_realtime_record'],
            'trips_not_monitored': c['not_monitored']}


def read_raw(path):
    with gzip.open(path, 'rt', newline='') as f:
        return list(csv.DictReader(f))


def write_summary():
    """Recompute the public cumulative summary from every archived window."""
    days, all_events = [], []
    for path in sorted(RAW.glob('*.csv.gz')):
        events = read_raw(path)
        if not events:
            continue
        meta_path = PUBLIC / path.name.replace('.csv.gz', '.json')
        meta = json.loads(meta_path.read_text()) if meta_path.exists() else {}
        if not meta.get('school_day', True):
            continue
        all_events.extend(events)
        days.append({'service_date': events[0]['service_date'], 'window': events[0]['window'],
                     'coverage': meta.get('coverage', {}), **trip_counts(events), **summarize_events(events)})
    by_route = defaultdict(list)
    by_stop = defaultdict(list)
    for e in all_events:
        by_route[(e['route_id'], e['route_name'])].append(e)
        by_stop[e['stop_id']].append(e)
    routes = [{'route_id': rid, 'route_name': name, **trip_counts(ev), **summarize_events(ev)}
              for (rid, name), ev in by_route.items()]
    routes.sort(key=lambda r: (r['pct_failed_15min_or_missing'] or 0), reverse=True)
    stop_ll = {}
    names_path = PUBLIC / 'stops.json'
    if names_path.exists():
        stop_ll = json.loads(names_path.read_text())
    stops = []
    for sid, ev in by_stop.items():
        s = summarize_events(ev)
        if s['measured_stop_events'] + s['canceled_by_mta'] + s['no_realtime_record'] < 10:
            continue  # too few observations to say anything about one stop
        info = stop_ll.get(sid, {})
        stops.append({'stop_id': sid, 'stop_name': info.get('name', ''), 'lat': info.get('lat'), 'lon': info.get('lon'),
                      'routes': sorted({e['route_name'] for e in ev}), **s})
    stops.sort(key=lambda r: (r['pct_failed_15min_or_missing'] or 0), reverse=True)
    summary = {
        'generated_utc': datetime.now(timezone.utc).isoformat(timespec='seconds'),
        'definitions': {
            'on_time': f'{EARLY_S // 60} min early to {LATE_S // 60} min late at a scheduled timepoint (MTA definition)',
            'late_over_15_min': f'arrived more than {SEVERE_S // 60} minutes after the scheduled time',
            'canceled_by_mta': "MTA's own real-time feed marked the trip CANCELED",
            'no_realtime_record': 'scheduled trip never appeared in the real-time feed; a likely missed trip, '
                                  'but a bus with failed tracking equipment looks the same',
            'pct_failed_15min_or_missing': 'scheduled stop visits that were 15+ min late, canceled, or had no record, '
                                           'out of all monitored visits with an outcome',
            'windows_local_time': WINDOWS,
        },
        'school_windows_counted': len(days),
        'overall': {**trip_counts(all_events), **summarize_events(all_events)},
        'by_window_type': {w: summarize_events([e for e in all_events if e['window'] == w]) for w in WINDOWS},
        'days': days,
        'routes': routes,
        'stops_worst_100': stops[:100],
    }
    PUBLIC.mkdir(parents=True, exist_ok=True)
    (PUBLIC / 'summary.json').write_text(json.dumps(summary, indent=1) + '\n')
    return summary


# ---------------------------------------------------------------------- main
def pick_window(arg, now_local):
    if arg in WINDOWS:
        return arg
    return 'am' if now_local.hour < 12 else 'pm'


def main(argv=None, fetch_static=None, fetch_rt=None, clock=time.time, sleep=time.sleep):
    ap = argparse.ArgumentParser()
    ap.add_argument('--window', default='auto')
    ap.add_argument('--date')
    ap.add_argument('--summarize-only', action='store_true')
    ap.add_argument('--force', action='store_true', help='run even if not a school day or already collected')
    args = ap.parse_args(argv)
    if args.summarize_only:
        write_summary()
        return 0

    now_local = datetime.fromtimestamp(clock(), TZ)
    day = date_cls.fromisoformat(args.date) if args.date else now_local.date()
    window = pick_window(args.window, now_local)
    tag = f'{day.isoformat()}-{window}'
    in_year = SC.get('school_year_start', '0000') <= day.isoformat() <= SC.get('school_year_end', '9999')
    school_day = in_year and day.weekday() < 5 and day.isoformat() not in NO_SCHOOL
    if window == 'pm' and day.isoformat() in SC.get('early_dismissal_dates', []):
        school_day = False  # students leave around midday; the PM window would measure the wrong trips
    if not school_day and not args.force:
        print(f'{day} {window} is not a regular school commute per config; nothing to collect.')
        return 0
    raw_path = RAW / f'{tag}.csv.gz'
    if raw_path.exists() and not args.force:
        print(f'{tag} already collected (backup trigger); exiting.')
        return 0

    key = os.environ.get('SWIFTLY_API_KEY', '').strip()
    if fetch_rt is None:
        if not key:
            sys.exit('SWIFTLY_API_KEY GitHub Actions secret is missing')
        fetch_rt = lambda feed: http_get(f'{RT_BASE}/{feed}', {'Authorization': key}, timeout=30)
    fetch_static = fetch_static or (lambda: http_get(GTFS_URL, timeout=120))

    win_start_s, win_end_s = (hhmm_seconds(x) for x in WINDOWS[window])
    midnight = datetime.combine(day, datetime.min.time(), TZ).timestamp()
    if clock() >= midnight + win_end_s and not args.force:
        print(f'{tag}: window already over; nothing to watch.')
        return 0
    trips, stops_ll = load_schedule(fetch_static(), day, win_start_s, win_end_s)
    print(f'{tag}: {len(trips)} scheduled trips touch the {WINDOWS[window][0]}-{WINDOWS[window][1]} window', flush=True)
    watcher = Watcher(trips, stops_ll, day, window, fetch_rt)

    stop_at = midnight + win_end_s + GRACE_MIN * 60
    started = clock()
    n = 0
    while clock() < stop_at:
        t0 = clock()
        watcher.poll(t0, with_trip_updates=(n % TRIP_UPDATE_EVERY == 0))
        n += 1
        if n % 20 == 0:
            print(f'  poll {n}: {len(watcher.polls_ok)} ok, {len(watcher.errors)} errors, '
                  f'{sum(t.seen for t in watcher.trackers.values())} trips seen', flush=True)
        sleep(max(0, POLL_SECONDS - (clock() - t0)))

    events = watcher.results(win_start_s, win_end_s)
    RAW.mkdir(parents=True, exist_ok=True)
    PUBLIC.mkdir(parents=True, exist_ok=True)
    with gzip.open(raw_path, 'wt', newline='') as f:
        w = csv.DictWriter(f, fieldnames=RAW_FIELDS)
        w.writeheader()
        w.writerows(events)
    coverage = {
        'collection_started_local': datetime.fromtimestamp(started, TZ).isoformat(timespec='seconds'),
        'window_start_local': WINDOWS[window][0], 'window_end_local': WINDOWS[window][1],
        'polls_attempted': n, 'polls_succeeded': len(watcher.polls_ok),
        'feed_errors': len(watcher.errors), 'first_errors': watcher.errors[:5],
        'distinct_vehicles_seen': len(watcher.vehicles_seen),
        'vehicles_on_unscheduled_trip_ids': len(watcher.vehicles_unmatched)}
    day_summary = {'service_date': day.isoformat(), 'window': window, 'school_day': school_day,
                   'coverage': coverage, **trip_counts(events), **summarize_events(events)}
    (PUBLIC / f'{tag}.json').write_text(json.dumps(day_summary, indent=1) + '\n')
    # Public stop names/coordinates for the report map (static, non-personal).
    (PUBLIC / 'stops.json').write_text(json.dumps(stops_ll, separators=(',', ':')) + '\n')
    write_summary()
    print(json.dumps({k: v for k, v in day_summary.items() if k != 'coverage'}, indent=1))
    return 0


if __name__ == '__main__':
    sys.exit(main())
