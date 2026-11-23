"""Build the three standalone Project C pages for home.ubalt.edu from the GitHub Pages site.

Usage:  python build_ubalt_pages.py /path/to/MTA_Accountability_Tracker [output_folder]

Reads docs/index.html, docs/routes.html and docs/accountability.html and writes
  project_c.html                 (Findings & Map)
  project_c_routes.html          (Explore Routes & Stops)
  project_c_accountability.html  (MTA Accountability)
Each copy inlines the two stylesheets, links its sibling pages by relative name (so the
three files must sit in the same UBalt folder), adds the author byline and the label "Course submission · data updates from the live tracker",
and loads the live data from GitHub Pages, with raw.githubusercontent.com as a backup.
Rebuild whenever any of the three docs pages changes.
"""
import re
import sys
from pathlib import Path

repo = Path(sys.argv[1])
out = Path(sys.argv[2]) if len(sys.argv) > 2 else Path(__file__).resolve().parent
docs = repo / "docs"
PAGES = "https://tbilkitty.github.io/MTA_Accountability_Tracker/"
DATA = [PAGES + "data/school-commute/",
        "https://raw.githubusercontent.com/TbilKitty/MTA_Accountability_Tracker/main/docs/data/school-commute/"]
FILES = {"index.html": "project_c.html", "routes.html": "project_c_routes.html",
         "accountability.html": "project_c_accountability.html"}
LIVE = {"index.html": PAGES, "routes.html": PAGES + "routes.html", "accountability.html": PAGES + "accountability.html"}

css = "\n".join((docs / name).read_text() for name in ("baltimore-theme.css", "project-c.css"))
css = re.sub(r"url\('\./([^']+)'\)", lambda m: f"url('{PAGES}{m.group(1)}')", css)

for source, target in FILES.items():
    html = (docs / source).read_text()
    links = re.findall(r'<link href="\./(?:baltimore-theme|project-c)\.css" rel="stylesheet"/>\n', html)
    assert len(links) == 2, source
    html = html.replace(links[0], "<!-- Standalone copy for home.ubalt.edu: the site stylesheets are inlined below, and the data load live "
                                  "from the GitHub Pages tracker (updated after each school commute). -->\n<style>\n" + css + "\n</style>\n", 1)
    html = html.replace(links[1], "", 1)

    # Links between the three pages, including links to sections (./#evidence, ./routes.html?route=22).
    def relink(match):
        path, rest = match.group(1), match.group(2) or ""
        return f'href="{FILES["index.html" if path in ("", "index.html") else path]}{rest}"'
    html = re.sub(r'href="\./((?:index|routes|accountability)\.html|)([#?][^"]*)?"', relink, html)
    assert 'href="./' not in html, source

    # Author byline under the eyebrow, as on the earlier UBalt copy.
    html = html.replace('<div class="eyebrow">Project C · Data Science for Lawyers</div>\n',
                        '<div class="eyebrow">Project C · Data Science for Lawyers</div>\n'
                        '  <p class="pc-byline" style="margin:4px 0 0;font-weight:700;color:var(--navy)">Audriana Duvall</p>\n'
                        '  <p class="pc-status" style="margin:6px 0 0;font-size:.9rem;font-weight:700;letter-spacing:.02em">'
                        'Course submission · data updates from the live tracker</p>\n', 1)
    assert "Course submission · data updates from the live tracker" in html, source
    html = html.replace("Wikimedia Commons, used with attribution.</footer>",
                        f'Wikimedia Commons, used with attribution. Live version of this page: <a href="{LIVE[source]}">{LIVE[source]}</a>.</footer>', 1)

    # Live data with a backup address.
    sources = "const SOURCES = [" + ", ".join(f"'{u}'" for u in DATA) + "];"
    if source == "index.html":
        old = re.search(r"  const BASE = './data/school-commute/';\n  const fresh = .*?\n  let data, svgText;\n  try \{\n"
                        r"    \[data, svgText\] = await Promise.all\(\[\n.*?\n.*?\]\);\n", html, re.S)
        assert old, "map loader not found"
        html = html.replace(old.group(0), (
            "  const fresh = '?v=' + Date.now();\n"
            "  // Live data: GitHub Pages first, then the same files on raw.githubusercontent.com as a backup.\n"
            f"  {sources}\n"
            "  // Both files come from the same address, so the figures and the map shapes are always the same version.\n"
            "  let data, svgText;\n  try {\n"
            "    for (const base of SOURCES) {\n"
            "      try {\n"
            "        const [j, v] = await Promise.all([fetch(base + 'neighborhood_map.json' + fresh), fetch(base + 'neighborhood_map.svg' + fresh)]);\n"
            "        if (j.ok && v.ok) { [data, svgText] = await Promise.all([j.json(), v.text()]); break; }\n"
            "      } catch (e) {}\n"
            "    }\n"
            "    if (!data) throw new Error('load failed');\n"))
    else:
        assert html.count("const SOURCES = ['./data/school-commute/'];") == 1, source
        html = html.replace("const SOURCES = ['./data/school-commute/'];", sources)
    assert "./data/" not in html, source
    (out / target).write_text(html)
    print(f"wrote {out / target} ({len(html) / 1e3:.0f} KB)")
