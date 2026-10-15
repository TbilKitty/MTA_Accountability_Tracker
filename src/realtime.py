"""Opt-in raw GTFS-RT archival. No no-show inference from absent feed records."""
import os,sys
from .collect import archive

def main():
    kind=sys.argv[1] if len(sys.argv)>1 else 'trip_updates'
    if kind not in ('trip_updates','vehicle_positions'):raise SystemExit('Choose trip_updates or vehicle_positions')
    url=os.environ.get('SWIFTLY_'+kind.upper()+'_URL')
    key=os.environ.get('SWIFTLY_API_KEY')
    if not url or not key:raise SystemExit('Configure authorized Swiftly URL and API key per current provider documentation. Do not commit credentials.')
    # Swiftly authorization method must be confirmed from its current API docs.
    # This deliberately avoids assuming a credential header and leaking keys.
    raise SystemExit('Adapter is not activated: validate Swiftly endpoint and authentication method, then implement authenticated fetch with tests. No data collected.')
if __name__=='__main__':main()
