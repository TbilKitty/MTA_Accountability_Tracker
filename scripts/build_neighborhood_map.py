"""Rebuild the neighborhood map on the Project C page from the Colab notebook.

Runs every code box of notebooks/Baltimore_City_MTA_Map_Colab.ipynb, with
USE_LATEST switched on and this checkout as the data source, so the website map
uses every school day collected so far and the same code as the Colab. The
in-Colab preview and the published-page check are skipped. If anything fails,
the existing map files are left as they are.

The notebook writes a standalone map page. The website shows the map inside
docs/index.html instead, so this script keeps two pieces of that page:
  docs/data/school-commute/neighborhood_map.json  (the map data and claim figures)
  docs/data/school-commute/neighborhood_map.svg   (the drawn neighborhood shapes)
and the notebook's route and stop tables (Boxes 22-23) for docs/routes.html:
  docs/data/school-commute/routes_stops.json
docs/baltimore-city-map.html is now only a redirect to the map section.
"""
import json
import re
import os
from pathlib import Path
import tempfile

import matplotlib

matplotlib.use("Agg")                     # draw charts without a screen

repo = Path(__file__).resolve().parents[1]
notebook = json.loads((repo / "notebooks/Baltimore_City_MTA_Map_Colab.ipynb").read_text())
os.environ["MTA_REPO_DIR"] = str(repo)    # read records from this checkout, not GitHub

boxes = ["".join(cell["source"]) for cell in notebook["cells"] if cell["cell_type"] == "code"]
assert sum("USE_LATEST = False" in box for box in boxes) == 1
boxes = [box.replace("USE_LATEST = False", "USE_LATEST = True") for box in boxes
         if box.strip() != "display(HTML(page))" and "published = {" not in box]

work = Path(tempfile.mkdtemp(prefix="neighborhood-map-"))
os.chdir(work)
names = {"display": lambda *args, **kwargs: None, "__name__": "__main__"}
for number, box in enumerate(boxes, 1):
    exec(compile(box, f"notebook code box {number}", "exec"), names)

page = (work / "Baltimore_City_MTA_Reliability_Map.html").read_text()
data = re.search(r'<script id="data" type="application/json">(.*?)</script>', page, re.S).group(1)
json.loads(data)                          # must be valid JSON
maps = page[page.index('id="maps"'):]
svg = maps[maps.index("<svg"):maps.index("</svg>") + len("</svg>")]
svg = svg.replace("<svg ", '<svg xmlns="http://www.w3.org/2000/svg" ', 1) if "xmlns=" not in svg[:200] else svg
out = repo / "docs/data/school-commute"
routes = (work / "Baltimore_City_MTA_Routes_Stops.json").read_text()
json.loads(routes)                        # must be valid JSON
for name, text in [("neighborhood_map.json", data), ("neighborhood_map.svg", svg), ("routes_stops.json", routes)]:
    tmp = out / (name + ".tmp")
    tmp.write_text(text)
    tmp.replace(out / name)
print(f"Updated the map data and shapes through {names['payload']['dates']['last']}")
