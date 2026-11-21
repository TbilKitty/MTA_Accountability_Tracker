"""Rebuild docs/baltimore-city-map.html from the Project C Colab notebook.

Runs every code box of notebooks/Baltimore_City_MTA_Map_Colab.ipynb, with
USE_LATEST switched on and this checkout as the data source, so the website map
uses every school day collected so far and the same code as the Colab. The
in-Colab preview and the published-page check are skipped. If anything fails,
the existing page is left as it is.
"""
import json
import os
from pathlib import Path
import shutil
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

page = work / "Baltimore_City_MTA_Reliability_Map.html"
target = repo / "docs/baltimore-city-map.html"
shutil.copyfile(page, target.with_suffix(".tmp"))
target.with_suffix(".tmp").replace(target)
print(f"Updated {target.relative_to(repo)} through {names['payload']['dates']['last']}")
