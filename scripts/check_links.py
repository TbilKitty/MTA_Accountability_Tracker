"""Check that every outside link on the Project C pages loads (HTTP status below 400).

Usage: python scripts/check_links.py   (prints one line per link; exits 1 if any fails)
Run from Actions: "Build stop areas" > job = links.
"""
import re
import sys
from pathlib import Path

import requests

docs = Path(__file__).resolve().parents[1] / "docs"
links = {}
for page in ("index.html", "routes.html", "accountability.html"):
    for url in re.findall(r'href="(https?://[^"]+)"', (docs / page).read_text()):
        links.setdefault(url.replace("&amp;", "&"), set()).add(page)
headers = {"User-Agent": "Mozilla/5.0 (link check for a course project)"}
failed = 0
for url, pages in sorted(links.items()):
    try:
        r = requests.get(url, headers=headers, timeout=60, allow_redirects=True, stream=True)
        status, kind = r.status_code, r.headers.get("content-type", "").split(";")[0]
        r.close()
    except requests.RequestException as error:
        status, kind = "ERR", type(error).__name__
    ok = isinstance(status, int) and status < 400
    failed += not ok
    print(f"{'ok  ' if ok else 'FAIL'} {status} {kind:<24} {url}  ({', '.join(sorted(pages))})")
print(f"{len(links)} links, {failed} failed")
sys.exit(1 if failed else 0)
