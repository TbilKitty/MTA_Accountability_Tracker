"""Tag every MTA bus stop with its census tract, whether it is inside Baltimore
City, and the tract's income and poverty rate. Writes data/reference/stop_areas.csv,
which the Project C Colab and scripts/make_claim_chart.py both read.

Sources (all public):
  * Stop locations: MTA local bus GTFS (stops.txt), the same schedule the tracker uses.
  * Tract boundaries: U.S. Census Bureau TIGER/Line 2023 tracts for Maryland.
  * Neighborhood names: Baltimore City's neighborhood boundaries (or BNIA
    Community Statistical Areas), found through ArcGIS Online search.
  * Income and poverty: American Community Survey (ACS) 2019-2023 5-year estimates,
    B19013_001E (median household income), B17001 (people below poverty),
    B25044 (households with no vehicle available), B09001 (children age 5 to 17)
    and B01003 (total population).

A stop is "in Baltimore City" when it falls inside a tract whose GEOID starts with
24510 (Maryland = 24, Baltimore City = 510). Baltimore City is its own county-level
area, so its tracts exactly cover the city limits.

Run by .github/workflows/stop-areas.yml (the census sites can't be reached from
every computer). Also writes docs/data/school-commute/city_tracts.geojson (city tract shapes for the
web page map).

Usage: python scripts/build_stop_areas.py
"""
import io
import os
import zipfile
from pathlib import Path

import geopandas as gpd
import pandas as pd
import requests

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "reference" / "stop_areas.csv"
MAP_OUT = ROOT / "docs" / "data" / "school-commute" / "city_tracts.geojson"
GTFS_URL = "https://feeds.mta.maryland.gov/gtfs/local-bus"
TRACTS_URL = "https://www2.census.gov/geo/tiger/TIGER2023/TRACT/tl_2023_24_tract.zip"
SCHOOL_AGE = [f"B09001_00{i}E" for i in range(5, 10)]  # children age 5, 6-8, 9-11, 12-14, 15-17
ACS_VARS = ["B19013_001E", "B17001_001E", "B17001_002E", "B25044_001E", "B25044_003E", "B25044_010E",
            "B01003_001E"] + SCHOOL_AGE
# Baltimore City is county 510 in Maryland (24). Only city tracts need Census numbers.
ACS_BASE = "https://api.census.gov/data/2023/acs/acs5"
ACS_PLACES = [{"for": "tract:*", "in": "state:24 county:510"},
              {"for": "tract:*", "in": ["state:24", "county:510"]}]


def get_acs():
    """Download the ACS table for every Baltimore City tract.

    The Census Bureau API now asks for a free key. With a CENSUS_API_KEY secret
    we use it; without one we use Census Reporter (censusreporter.org), which
    republishes the same ACS 5-year tables and needs no key."""
    key = os.environ.get("CENSUS_API_KEY")
    if key:
        r = requests.get(ACS_BASE, params={"get": ",".join(ACS_VARS), "for": "tract:*",
                                           "in": "state:24 county:510", "key": key}, timeout=120)
        try:
            rows = r.json()
            print("ACS source: Census Bureau API,", ACS_BASE)
            return pd.DataFrame(rows[1:], columns=rows[0])
        except ValueError:
            print(f"Census API answered {r.status_code}: {r.text[:200]}")
    tables = sorted({v.split("_")[0] for v in ACS_VARS})
    data = {}
    for table in tables:  # one table per request keeps each answer small
        for release in ("acs2023_5yr", "latest"):
            r = requests.get(f"https://api.censusreporter.org/1.0/data/show/{release}",
                             params={"table_ids": table, "geo_ids": "140|05000US24510"}, timeout=180,
                             headers={"User-Agent": "mta-school-commute-tracker/1.0 (student data project)"})
            try:
                d = r.json()
            except ValueError:
                d = {}
            if "data" in d:
                print(f"ACS {table}: Census Reporter, {d.get('release', {}).get('name')}")
                for geo, t in d["data"].items():
                    data.setdefault(geo, {}).update(t)
                break
            print(f"Census Reporter {release} {table} answered {r.status_code}: {r.text[:300]}")
        else:
            raise SystemExit(f"Could not download ACS table {table}")
    d = {"data": data}
    rows = []
    for geo, t in d["data"].items():
        row = {"GEOID": geo.split("US")[-1]}
        for v in ACS_VARS:
            table, num = v.split("_")[0], v.split("_")[1][:-1]
            row[v] = t.get(table, {}).get("estimate", {}).get(f"{table}{num}")
        rows.append(row)
    acs = pd.DataFrame(rows)
    acs["state"], acs["county"], acs["tract"] = acs["GEOID"].str[:2], acs["GEOID"].str[2:5], acs["GEOID"].str[5:]
    return acs.drop(columns="GEOID")

# Neighborhood names. Baltimore City publishes its official neighborhood
# boundaries (and BNIA its Community Statistical Areas) as ArcGIS layers. Layer
# addresses change over time, so search ArcGIS Online for them and use the first
# that returns Baltimore polygons with a name field.
ARCGIS_SEARCH = "https://www.arcgis.com/sharing/rest/search"
NAME_SEARCHES = ['title:"Neighborhood Statistical Area" Baltimore', 'title:Neighborhoods Baltimore City',
                 'title:"Community Statistical Areas" Baltimore']
NAME_FIELDS = ["NBRDESC", "Name", "NAME", "Neighborhood", "NEIGHBORHOOD", "LABEL", "Label", "CSA2020", "Community", "CSA2010"]


def find_neighborhoods():
    """Return (polygons with a 'neighborhood' column, source URL), or (None, None)."""
    for q in NAME_SEARCHES:
        try:
            hits = requests.get(ARCGIS_SEARCH, params={"q": q + ' type:"Feature Service"', "f": "json", "num": 10},
                                timeout=60).json().get("results", [])
        except Exception as e:  # keep going: names are nice to have, not required
            print("search failed:", e)
            continue
        for h in hits:
            url = (h.get("url") or "").rstrip("/")
            if not url:
                continue
            layer = url if url.split("/")[-1].isdigit() else url + "/0"
            try:
                g = gpd.read_file(layer + "/query?where=1%3D1&outFields=*&outSR=4326&f=geojson")
            except Exception:
                continue
            field = next((f for f in NAME_FIELDS if f in g.columns), None)
            if field is None or len(g) < 40 or not len(g):
                continue
            x, y = g.to_crs("EPSG:4326").union_all().centroid.coords[0]
            if not (-76.75 < x < -76.5 and 39.2 < y < 39.4):  # must be Baltimore City
                continue
            print(f"Neighborhood names: {h.get('title')} ({layer}), field {field}, {len(g)} areas")
            return g.rename(columns={field: "neighborhood"})[["neighborhood", "geometry"]].to_crs("EPSG:4326"), layer
    print("No neighborhood layer found; the map will show tract numbers instead")
    return None, None


def tract_labels(city, hoods):
    """Name each tract after the neighborhoods covering it: the biggest first,
    plus any other that covers at least a quarter of the tract (at most 3)."""
    t = city[["GEOID", "geometry"]].to_crs("EPSG:26985")
    t["tract_area"] = t.area
    pieces = gpd.overlay(t, hoods.to_crs("EPSG:26985"), how="intersection")
    pieces["share"] = pieces.area / pieces["tract_area"]
    labels = {}
    for geoid, g in pieces.sort_values("share", ascending=False).groupby("GEOID", sort=False):
        names = [str(n).strip().title() for n, sh in zip(g["neighborhood"], g["share"]) if sh >= 0.25 or n == g["neighborhood"].iloc[0]]
        names = list(dict.fromkeys(names))[:3]
        labels[geoid] = " / ".join(names)
    return labels

ACS_COLS = ["median_household_income", "poverty_rate", "pct_no_vehicle", "pct_school_age", "school_age_children"]


def main():
    gtfs = zipfile.ZipFile(io.BytesIO(requests.get(GTFS_URL, timeout=120).content))
    stops = pd.read_csv(gtfs.open("stops.txt"), dtype={"stop_id": str})
    stops = stops[["stop_id", "stop_name", "stop_lat", "stop_lon"]]
    points = gpd.GeoDataFrame(stops, geometry=gpd.points_from_xy(stops.stop_lon, stops.stop_lat), crs="EPSG:4326")

    tracts = gpd.read_file(TRACTS_URL)[["GEOID", "NAMELSAD", "ALAND", "geometry"]].to_crs("EPSG:4326")
    joined = gpd.sjoin(points, tracts[["GEOID", "geometry"]], how="left", predicate="within").drop(
        columns=["geometry", "index_right"])

    acs = get_acs()
    acs["GEOID"] = acs["state"] + acs["county"] + acs["tract"]
    acs["median_household_income"] = pd.to_numeric(acs["B19013_001E"], errors="coerce")
    acs.loc[acs["median_household_income"] < 0, "median_household_income"] = None  # census "no data" codes
    total, poor = pd.to_numeric(acs["B17001_001E"]), pd.to_numeric(acs["B17001_002E"])
    acs["poverty_rate"] = (poor / total * 100).where(total > 0).round(1)
    # Households with no vehicle (owners + renters) out of all households: who depends on transit.
    hh = pd.to_numeric(acs["B25044_001E"])
    no_car = pd.to_numeric(acs["B25044_003E"]) + pd.to_numeric(acs["B25044_010E"])
    acs["pct_no_vehicle"] = (no_car / hh * 100).where(hh > 0).round(1)
    # School-age children (5 to 17) as a share of all residents.
    pop = pd.to_numeric(acs["B01003_001E"])
    kids = sum(pd.to_numeric(acs[c]) for c in SCHOOL_AGE)
    acs["school_age_children"] = kids
    acs["pct_school_age"] = (kids / pop * 100).where(pop > 0).round(1)

    out = joined.merge(acs[["GEOID"] + ACS_COLS], on="GEOID", how="left")
    out = out.rename(columns={"GEOID": "tract_geoid"})
    out["in_baltimore_city"] = out["tract_geoid"].fillna("").str.startswith("24510")
    OUT.parent.mkdir(parents=True, exist_ok=True)

    # A small map of the city's tracts for the web page (water-only tracts dropped,
    # shapes simplified to about 20 m so the file stays small).
    city = tracts[tracts["GEOID"].str.startswith("24510") & (tracts["ALAND"] > 0)].copy()
    city = city.merge(acs[["GEOID"] + ACS_COLS], on="GEOID", how="left")
    city["geometry"] = city.to_crs("EPSG:26985").simplify(20).to_crs("EPSG:4326").set_precision(0.00001)
    try:  # names are nice to have; never let them stop the build
        hoods, source = find_neighborhoods()
        labels = tract_labels(city, hoods) if hoods is not None else {}
    except Exception as e:
        print("Neighborhood names skipped:", e)
        source, labels = None, {}
    city["neighborhood"] = city["GEOID"].map(labels)
    city = city.rename(columns={"NAMELSAD": "name"})[["GEOID", "name", "neighborhood", *ACS_COLS, "geometry"]]
    out = out.merge(city[["GEOID", "neighborhood"]].rename(columns={"GEOID": "tract_geoid"}), on="tract_geoid", how="left")
    out.sort_values("stop_id").to_csv(OUT, index=False)
    if source:
        (OUT.parent / "neighborhood_source.txt").write_text(source + "\n")
    MAP_OUT.write_text(city.to_json(drop_id=True, to_wgs84=True))
    print(f"{len(out):,} stops; {out.in_baltimore_city.sum():,} in Baltimore City; "
          f"{out.poverty_rate.notna().sum():,} with poverty data")


if __name__ == "__main__":
    main()
