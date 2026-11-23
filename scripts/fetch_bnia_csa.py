"""Download the official BNIA-JFI Vital Signs layers used by the CSA overlap map.

Saves an exact copy of each ArcGIS layer (attributes + boundaries, GeoJSON in
longitude/latitude) and its metadata (field aliases, description, edit dates)
under data/reference/bnia/raw/. build_csa_overlap.py reads only these saved
copies, so the education and Census layers stay fixed at the downloaded release
while the transit figures refresh. Rerun this by hand (Actions > "Build stop
areas" > job = bnia) only when you mean to move to a newer BNIA release.

Source: BNIA-JFI ArcGIS Online organization (services1.arcgis.com/mVFRs7NF4iFitgbY),
the host behind https://bniajfi.org/vital_signs/data_downloads/.
"""
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

BASE = "https://services1.arcgis.com/mVFRs7NF4iFitgbY/ArcGIS/rest/services"
SERVICES = {
    # service name: what it is
    "Community_Statistical_Areas_2020": "CSA 2020 boundaries",
    "Drop": "High school dropout/withdrawal rate",
    "Compl": "High school completion rate",
    "Hhpov": "Percent of family households living below the poverty line",
    "Novhcl": "Percent of households with no vehicle available",
    "Hhchpov": "Percent of children living below the poverty line",
    "Tract2020_to_CSA2020": "Census tract 2020 to CSA 2020 crosswalk",
}
out = Path(__file__).resolve().parents[1] / "data/reference/bnia/raw"
out.mkdir(parents=True, exist_ok=True)
session = requests.Session()
session.headers["User-Agent"] = "mta-accountability-tracker (course project)"


def get(url, **params):
    for attempt in range(4):
        try:
            r = session.get(url, params=params, timeout=120)
            r.raise_for_status()
            return r
        except requests.RequestException as error:
            print(f"  retry {attempt + 1}: {error}")
            time.sleep(5 * (attempt + 1))
    raise SystemExit(f"Could not download {url}")


manifest = {"downloaded_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"), "source": BASE, "layers": {}}
failed = []
for name, label in SERVICES.items():
    print(name)
    service = get(f"{BASE}/{name}/FeatureServer", f="json").json()
    if "error" in service:
        print("  not found:", service["error"]); failed.append(name); continue
    (out / f"{name}.service.json").write_text(json.dumps(service, indent=1))
    for layer in service.get("layers", []) + service.get("tables", []):
        lid = layer["id"]
        meta = get(f"{BASE}/{name}/FeatureServer/{lid}", f="json").json()
        (out / f"{name}_{lid}.meta.json").write_text(json.dumps(meta, indent=1))
        params = dict(where="1=1", outFields="*", f="geojson", outSR=4326, returnGeometry="true")
        if meta.get("type") == "Table":
            params["f"] = "json"
        rows, offset = None, 0
        while True:
            page = get(f"{BASE}/{name}/FeatureServer/{lid}/query", resultOffset=offset, **params).json()
            if "error" in page:
                raise SystemExit(f"{name}/{lid}: {page['error']}")
            if rows is None:
                rows = page
            else:
                rows["features"].extend(page["features"])
            got = len(page.get("features", []))
            offset += got
            if not got or not (page.get("exceededTransferLimit") or page.get("properties", {}).get("exceededTransferLimit")):
                break
        suffix = "geojson" if params["f"] == "geojson" else "json"
        (out / f"{name}_{lid}.{suffix}").write_text(json.dumps(rows))
        manifest["layers"][f"{name}_{lid}"] = {
            "label": label, "layer_name": meta.get("name"), "url": f"{BASE}/{name}/FeatureServer/{lid}",
            "features": len(rows.get("features", [])),
            "fields": {f["name"]: f.get("alias") for f in meta.get("fields", [])},
            "last_edit": (meta.get("editingInfo") or {}).get("lastEditDate"),
            "data_last_edit": (meta.get("editingInfo") or {}).get("dataLastEditDate"),
        }
        print(f"  layer {lid} {meta.get('name')!r}: {len(rows.get('features', []))} features")

# BNIA's own pages describing the indicators (saved for the record).
for page, url in {"data_downloads.html": "https://bniajfi.org/vital_signs/data_downloads/",
                  "vital_signs.html": "https://bniajfi.org/vital_signs/",
                  "communities.html": "https://bniajfi.org/communities/"}.items():
    try:
        (out / page).write_text(get(url).text)
    except SystemExit as error:
        print(error)
# Source documents cited next to the map (graduation context), kept so the cited
# figures can be checked against an exact copy.
docs = Path(__file__).resolve().parents[1] / "data/reference/sources"
docs.mkdir(parents=True, exist_ok=True)
for page, url in {
        "city_schools_2025_graduation_article.html": "https://www.baltimorecityschools.org/article/2661885",
        "city_schools_2025_graduation_board_deck.pdf": "https://files-backend.assets.thrillshare.com/documents/asset/uploaded_file/3843/Bcps/305b6500-44e6-4baf-9d87-8c29df253852/2025-Graduation-Rate-Results-Board-Deck.pdf?disposition=inline",
        "mdot_attainment_report_2026_goal2.pdf": "https://www.mdot.maryland.gov/OPCP/AR/AR_2026_ADA_RegRes_Goal2.pdf",
        "mdot_attainment_report_page.html": "https://www.mdot.maryland.gov/tso/pages/Index.aspx?PageId=121",
        "mta_performance_improvement.html": "https://www.mta.maryland.gov/performance-improvement",
        "dls_fy2027_J00H01_MTA.pdf": "https://mgaleg.maryland.gov/pubs/budgetfiscal/2027fy-budget-docs-operating-J00H01-MDOT-Maryland-Transit-Administration.pdf",
        "dls_fy2026_J00H01_MTA.pdf": "https://mgaleg.maryland.gov/pubs/budgetfiscal/2026fy-budget-docs-operating-J00H01-MDOT-Maryland-Transit-Administration.pdf",
        "dls_fy2025_J00H01_MTA.pdf": "https://mgaleg.maryland.gov/pubs/budgetfiscal/2025fy-budget-docs-operating-J00H01-MDOT-Maryland-Transit-Administration.pdf",
        "md_transportation_7-710.html": "https://mgaleg.maryland.gov/mgawebsite/Laws/StatuteText?article=gtr&section=7-710&enactments=false",
        }.items():
    try:
        (docs / page).write_bytes(get(url).content)
    except SystemExit as error:
        print(error)
manifest["missing_services"] = failed
(out / "manifest.json").write_text(json.dumps(manifest, indent=1))
print("done; missing:", failed)
