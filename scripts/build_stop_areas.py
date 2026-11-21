"""Tag every MTA bus stop with its census tract, whether it is inside Baltimore
City, and the tract's income and poverty rate. Writes data/reference/stop_areas.csv,
which the Project C Colab and scripts/make_claim_chart.py both read.

Sources (all public):
  * Stop locations: MTA local bus GTFS (stops.txt), the same schedule the tracker uses.
  * Tract boundaries: U.S. Census Bureau TIGER/Line 2023 tracts for Maryland.
  * Income and poverty: American Community Survey (ACS) 2019-2023 5-year estimates,
    B19013_001E (median household income) and B17001 (people below poverty).

A stop is "in Baltimore City" when it falls inside a tract whose GEOID starts with
24510 (Maryland = 24, Baltimore City = 510). Baltimore City is its own county-level
area, so its tracts exactly cover the city limits.

Run by .github/workflows/stop-areas.yml (the census sites can't be reached from
every computer). Also writes docs/data/school-commute/city_tracts.geojson (city tract shapes for the
web page map).

Usage: python scripts/build_stop_areas.py
"""
import io
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
ACS_URL = ("https://api.census.gov/data/2023/acs/acs5?get=B19013_001E,B17001_001E,B17001_002E"
           "&for=tract:*&in=state:24&in=county:*")


def main():
    gtfs = zipfile.ZipFile(io.BytesIO(requests.get(GTFS_URL, timeout=120).content))
    stops = pd.read_csv(gtfs.open("stops.txt"), dtype={"stop_id": str})
    stops = stops[["stop_id", "stop_name", "stop_lat", "stop_lon"]]
    points = gpd.GeoDataFrame(stops, geometry=gpd.points_from_xy(stops.stop_lon, stops.stop_lat), crs="EPSG:4326")

    tracts = gpd.read_file(TRACTS_URL)[["GEOID", "NAMELSAD", "ALAND", "geometry"]].to_crs("EPSG:4326")
    joined = gpd.sjoin(points, tracts[["GEOID", "geometry"]], how="left", predicate="within").drop(
        columns=["geometry", "index_right"])

    rows = requests.get(ACS_URL, timeout=120).json()
    acs = pd.DataFrame(rows[1:], columns=rows[0])
    acs["GEOID"] = acs["state"] + acs["county"] + acs["tract"]
    acs["median_household_income"] = pd.to_numeric(acs["B19013_001E"], errors="coerce")
    acs.loc[acs["median_household_income"] < 0, "median_household_income"] = None  # census "no data" codes
    total, poor = pd.to_numeric(acs["B17001_001E"]), pd.to_numeric(acs["B17001_002E"])
    acs["poverty_rate"] = (poor / total * 100).where(total > 0).round(1)

    out = joined.merge(acs[["GEOID", "median_household_income", "poverty_rate"]], on="GEOID", how="left")
    out = out.rename(columns={"GEOID": "tract_geoid"})
    out["in_baltimore_city"] = out["tract_geoid"].fillna("").str.startswith("24510")
    OUT.parent.mkdir(parents=True, exist_ok=True)
    out.sort_values("stop_id").to_csv(OUT, index=False)

    # A small map of the city's tracts for the web page (water-only tracts dropped,
    # shapes simplified to about 20 m so the file stays small).
    city = tracts[tracts["GEOID"].str.startswith("24510") & (tracts["ALAND"] > 0)].copy()
    city = city.merge(acs[["GEOID", "median_household_income", "poverty_rate"]], on="GEOID", how="left")
    city["geometry"] = city.to_crs("EPSG:26985").simplify(20).to_crs("EPSG:4326").set_precision(0.00001)
    city = city.rename(columns={"NAMELSAD": "name"})[["GEOID", "name", "median_household_income", "poverty_rate", "geometry"]]
    MAP_OUT.write_text(city.to_json(drop_id=True, to_wgs84=True))
    print(f"{len(out):,} stops; {out.in_baltimore_city.sum():,} in Baltimore City; "
          f"{out.poverty_rate.notna().sum():,} with poverty data")


if __name__ == "__main__":
    main()
