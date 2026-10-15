"""Generate aggregated descriptive dashboard from private, self-reported incidents."""
import csv,pathlib,json,html,collections
ROOT=pathlib.Path(__file__).resolve().parents[1]
F=ROOT/'data/private/rider_reports.csv'
def main():
    if not F.exists():
        print('No private rider reports. Copy data/rider_reports_template.csv to data/private/rider_reports.csv and enter reports.');return
    records=list(csv.DictReader(F.open(newline='',encoding='utf-8-sig')))
    def num(r,k):
        try:return max(0,float(r.get(k,'') or 0))
        except ValueError:return 0
    total_hours=sum(num(r,'work_hours_missed') for r in records)
    confirmed_wages=sum(num(r,'documented_wages_lost_usd') for r in records)
    travel=sum(num(r,'extra_transport_cost_usd') for r in records)
    stats={'report_count':len(records),'self_reported_work_hours_missed':round(total_hours,2),'self_reported_documented_wages_lost_usd':round(confirmed_wages,2),'self_reported_extra_transport_cost_usd':round(travel,2),'verification_note':'Self-reported; not independently verified; not attributed legal liability.'}
    (ROOT/'docs/summary.json').write_text(json.dumps(stats,indent=2))
    print(json.dumps(stats,indent=2))
if __name__=='__main__':main()
