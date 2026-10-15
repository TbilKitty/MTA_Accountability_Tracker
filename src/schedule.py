"""Show scheduled GTFS trips for a stop and service date, accounting for calendar exceptions."""
import argparse,csv,pathlib,datetime as dt
ROOT=pathlib.Path(__file__).resolve().parents[1]/'data/processed'
def rows(name):
    f=ROOT/name
    return list(csv.DictReader(f.open(newline='',encoding='utf-8-sig'))) if f.exists() else []
def active_services(day):
    d=dt.date.fromisoformat(day);key=d.strftime('%Y%m%d');weekday=d.strftime('%A').lower()
    ids={r['service_id'] for r in rows('calendar.csv') if r['start_date']<=key<=r['end_date'] and r[weekday]=='1'}
    for r in rows('calendar_dates.csv'):
        if r['date']==key:
            if r['exception_type']=='1':ids.add(r['service_id'])
            elif r['exception_type']=='2':ids.discard(r['service_id'])
    return ids

def schedule(day,stop):
    ids=active_services(day)
    trips={r['trip_id']:r for r in rows('trips.csv') if r['service_id'] in ids}
    output=[]
    for r in rows('stop_times.csv'):
        if r['stop_id']==stop and r['trip_id'] in trips:
            t=trips[r['trip_id']]
            output.append({'date':day,'stop_id':stop,'trip_id':r['trip_id'],'route_id':t['route_id'],'direction_id':t.get('direction_id',''),'scheduled_arrival':r['arrival_time'],'stop_sequence':r['stop_sequence']})
    return sorted(output,key=lambda x:x['scheduled_arrival'])
if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--date',required=True);ap.add_argument('--stop',required=True);args=ap.parse_args()
    for item in schedule(args.date,args.stop):print(item)
