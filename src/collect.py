"""Archive exact bytes from official public sources with SHA256 and UTC timestamps."""
import argparse, hashlib, json, datetime as dt, pathlib, requests, zipfile, csv, io
ROOT=pathlib.Path(__file__).resolve().parents[1]
CFG=json.loads((ROOT/'config/settings.json').read_text())
def archive(url, name):
    stamp=dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    r=requests.get(url,timeout=40,headers={'User-Agent':'BaltimoreTransitAccountability/0.1 research contact via project README'})
    r.raise_for_status()
    out=ROOT/'data/raw'/f'{stamp}_{name}';out.parent.mkdir(parents=True,exist_ok=True)
    out.write_bytes(r.content)
    meta={'retrieved_at_utc':dt.datetime.now(dt.timezone.utc).isoformat(),'source_url':url,'sha256':hashlib.sha256(r.content).hexdigest(),'http_status':r.status_code,'content_type':r.headers.get('Content-Type'),'bytes':len(r.content),'file':out.name}
    out.with_suffix(out.suffix+'.json').write_text(json.dumps(meta,indent=2))
    print(json.dumps(meta,indent=2))
    return out

def static():
    f=archive(CFG['gtfs_url'],'local_bus_gtfs.zip')
    with zipfile.ZipFile(f) as z:
        for name in ('stops.txt','routes.txt','trips.txt','stop_times.txt','calendar.txt','calendar_dates.txt'):
            if name in z.namelist():
                target=ROOT/'data/processed'/name.replace('.txt','.csv');target.parent.mkdir(parents=True,exist_ok=True)
                target.write_bytes(z.read(name))
    print('Extracted GTFS tables to data/processed; raw zip preserved.')
def alerts():
    f=archive(CFG['alerts_url'],'alerts.pb')
    try:
        from google.transit import gtfs_realtime_pb2
        feed=gtfs_realtime_pb2.FeedMessage();feed.ParseFromString(f.read_bytes())
        records=[]
        for entity in feed.entity:
            if entity.HasField('alert'):
                a=entity.alert
                records.append({'entity_id':entity.id,'header':'; '.join(t.text for t in a.header_text.translation),'description':'; '.join(t.text for t in a.description_text.translation),'informed_entities':[{'route_id':x.route_id,'stop_id':x.stop_id,'trip_id':x.trip.trip_id} for x in a.informed_entity]})
        print(json.dumps({'alert_count':len(records),'alerts':records[:10]},indent=2))
    except Exception as exc: print('Archived raw alerts; parsing failed:',exc)
if __name__=='__main__':
    a=argparse.ArgumentParser();a.add_argument('--static',action='store_true');a.add_argument('--alerts',action='store_true');args=a.parse_args()
    if not(args.static or args.alerts): a.error('Specify --static and/or --alerts')
    if args.static: static()
    if args.alerts: alerts()
