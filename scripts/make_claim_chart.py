"""Redraw the Project C charts and headline numbers from every saved commute file.

Same logic as the Project C Colab notebook: read the trip-level files in
data/school-commute-raw/ (*-am.csv.gz for the ride to school, *-pm.csv.gz for
the ride home), keep rows with a known outcome, group by half hour of
scheduled arrival, and draw one stacked bar per half hour.

Writes, next to each other in docs/data/school-commute/:
  project_c_claim.png      morning chart (6:00 to 9:00 AM blocks)
  project_c_afternoon.png  afternoon chart (2:00 to 5:00 PM blocks)
  project_c_overall.png    both commutes on one timeline (the "Overall" view)
  project_c_claim.json     headline numbers the web page reads

The school-commute workflow runs this after each collection, so the GitHub
Pages site always shows the latest charts and numbers.

Usage: python scripts/make_claim_chart.py [--out PATH]   (PATH = morning PNG)
"""
import argparse
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")  # no screen on GitHub's runner
import matplotlib.pyplot as plt
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "school-commute-raw"
DEFAULT_OUT = ROOT / "docs" / "data" / "school-commute" / "project_c_claim.png"
AFTERNOON_NAME = "project_c_afternoon.png"
OVERALL_NAME = "project_c_overall.png"

ORDER = ["on_time", "early", "late", "severely_late", "canceled"]
FAILED = ["late", "severely_late", "canceled"]  # canceled or 7+ minutes late
LABELS = {"on_time": "On time", "early": "Early (2+ min)", "late": "Late (7 to 15 min)",
          "severely_late": "Very late (15+ min)", "canceled": "Canceled"}
COLORS = {"on_time": "#2E8B57", "early": "#B8B8B8", "late": "#F2A541",
          "severely_late": "#D1495B", "canceled": "#3D2C3E"}

# Each commute window: which files, the last half hour to drop (the window
# ends then, so that block is incomplete), and how the chart is labeled.
WINDOWS = {
    "am": {"pattern": "*-am.csv.gz", "drop": "9:30", "noun": "mornings", "xlabel": "Scheduled arrival time (AM)",
           "title": "Morning buses are least reliable right before school starts",
           "shade": ("8:00", "8:30", "Typical bell times")},
    "pm": {"pattern": "*-pm.csv.gz", "drop": "5:30", "noun": "afternoons", "xlabel": "Scheduled arrival time (PM)",
           "title": "The ride home: afternoon bus reliability by half hour",
           "shade": None},
    # Both windows together: morning and afternoon half hours on one timeline.
    "all": {"noun": "school days", "xlabel": "Scheduled arrival time",
            "title": "Across the school day: the ride to school and the ride home",
            "shade": None},  # the morning chart shows bell times
}


def load_known(window):
    """All rows for one window whose outcome is known, with a half-hour label."""
    w = WINDOWS[window]
    # The pattern skips the per-stop summaries (*-am-stops.csv.gz).
    files = sorted(RAW.glob(w["pattern"]))
    if not files:
        return None
    df = pd.concat([pd.read_csv(f) for f in files], ignore_index=True)
    known = df[df["outcome"].isin(ORDER)].copy()
    # Round each scheduled time down to its half hour: 7:42 becomes 7:30.
    half = pd.to_datetime(known["scheduled_local"]).dt.floor("30min")
    known["half_hour"] = half.dt.strftime("%I:%M").str.lstrip("0")
    known["_sort"] = half.dt.hour * 60 + half.dt.minute
    return known[known["half_hour"] != w["drop"]]


def by_half_hour(known):
    """Percent of each outcome in each half hour, in time order."""
    table = (known.groupby("half_hour")["outcome"].value_counts(normalize=True)
             .unstack().reindex(columns=ORDER, fill_value=0).fillna(0) * 100)
    order = known.groupby("half_hour")["_sort"].first().sort_values().index
    return table.loc[order]


def draw(known, window, out):
    w = WINDOWS[window]
    by_time = by_half_hour(known)
    pct_failed = known["outcome"].isin(FAILED).mean() * 100

    wide = window == "all"
    fig, ax = plt.subplots(figsize=(13, 6) if wide else (10, 6))
    bottom = pd.Series(0.0, index=by_time.index)
    for col in ORDER:
        ax.bar(by_time.index, by_time[col], bottom=bottom, color=COLORS[col],
               label=LABELS[col], width=0.75, edgecolor="white")
        bottom += by_time[col]
    # Print the on-time percent inside each green bar.
    for i, v in enumerate(by_time["on_time"]):
        ax.text(i, v / 2, f"{v:.0f}%", ha="center", va="center", color="white",
                fontsize=10.5 if wide else 12, fontweight="bold")

    idx = list(by_time.index)
    if w["shade"] and w["shade"][0] in idx:
        first, last, text = w["shade"]
        start = idx.index(first)
        end = idx.index(last) if last in idx else start
        ax.axvspan(start - 0.5, end + 0.5, color="#FFE8A3", alpha=0.45, zorder=0)
        ax.text((start + end) / 2, 101, text, ha="center", va="bottom", fontsize=10)

    if window == "all":
        # A dashed line between the last morning and first afternoon bar.
        pm_start = next((i for i, t in enumerate(idx) if t.endswith("PM")), None)
        if pm_start:
            ax.axvline(pm_start - 0.5, color="gray", linestyle="--", linewidth=1)
            ax.text(pm_start / 2 - 0.5, 101, "Ride to school", ha="center", va="bottom", fontsize=10, color="gray")
            ax.text((pm_start + len(idx)) / 2 - 0.5, 101, "Ride home", ha="center", va="bottom", fontsize=10, color="gray")
        # Two-line tick labels ("6:00" over "AM") so they don't collide.
        ax.set_xticks(range(len(idx)), [t.replace(" ", "\n") for t in idx])

    ax.set_ylim(0, 108)
    ax.set_ylabel("% of scheduled bus arrivals")
    ax.set_xlabel(w["xlabel"])
    ax.spines[["top", "right"]].set_visible(False)
    ax.legend(loc="upper left", bbox_to_anchor=(1.0, 1.0), frameon=False, reverse=True)

    days = known["service_date"].nunique()
    noun = w["noun"]
    which = {"am": "morning buses", "pm": "afternoon buses", "all": "school-commute buses"}[window]
    ax.set_title(f"{w['title']}\n"
                 f"Overall, {pct_failed:.0f}% of {which} were canceled or 7+ minutes late",
                 fontsize=14, fontweight="bold", loc="left")
    fig.text(0.01, 0.01,
             f"MTA local bus, {days} {'' if window == 'all' else 'school '}{noun} ({known.service_date.min()} to "
             f"{known.service_date.max()}), {len(known):,} scheduled arrivals. "
             "Source: MTA real-time feed vs. GTFS schedule, collected by the author. Updated automatically.",
             fontsize=8.5, color="gray")
    plt.tight_layout(rect=(0, 0.04, 1, 1))
    out.parent.mkdir(parents=True, exist_ok=True)
    # Fixed metadata so the PNG only changes when the data does.
    fig.savefig(out, dpi=200, bbox_inches="tight", metadata={"Software": None})
    plt.close(fig)
    print(f"Saved {out.name} ({days} {noun}, {len(known):,} arrivals, {pct_failed:.0f}% failed)")
    return by_time, pct_failed


def breakdown(known):
    """How every arrival turned out: count and percent for each outcome.

    Same five outcomes and order as the chart legend, so the page's breakdown
    and the stacked bars always agree. The percents add up to 100 (before
    rounding), and late + very late + canceled = the "canceled or 7+ minutes
    late" headline.
    """
    counts = known["outcome"].value_counts().reindex(ORDER, fill_value=0)
    pct = counts / counts.sum() * 100
    return {o: {"label": LABELS[o], "color": COLORS[o], "count": int(counts[o]),
                "pct": round(float(pct[o]), 1), "display": f"{pct[o]:.0f}%"} for o in ORDER}


def summarize(known, by_time, pct_failed, noun):
    pct_on_time = (known["outcome"] == "on_time").mean() * 100
    return {
        "breakdown": breakdown(known),
        f"school_{noun}": int(known["service_date"].nunique()),
        "first_date": str(known.service_date.min()),
        "last_date": str(known.service_date.max()),
        "scheduled_arrivals": int(len(known)),
        "pct_on_time": round(float(pct_on_time), 1),
        "pct_canceled_or_late": round(float(pct_failed), 1),
        "pct_on_time_by_half_hour": {t: round(float(v), 1) for t, v in by_time["on_time"].items()},
        # Rounded the same way as the chart labels, so page and chart agree.
        "display": {"canceled_or_late": f"{pct_failed:.0f}%", "on_time": f"{pct_on_time:.0f}%"},
    }


def main(out):
    am = load_known("am")
    if am is None:
        raise SystemExit(f"No morning files in {RAW}")
    am_time, am_failed = draw(am, "am", out)
    stats = summarize(am, am_time, am_failed, "mornings")

    # Morning extras: the hour before school (8:00 and 8:30 blocks) and 6:00.
    peak = [t for t in ("8:00", "8:30") if t in am_time.index]
    if peak:
        v = am_time.loc[peak, "on_time"].mean()
        stats["pct_on_time_8_to_9"] = round(float(v), 1)
        stats["display"]["on_time_8_to_9"] = f"{v:.0f}%"
    if "6:00" in am_time.index:
        stats["display"]["on_time_6"] = f"{am_time.loc['6:00', 'on_time']:.0f}%"

    pm = load_known("pm")
    stats["afternoon"] = None
    if pm is not None and len(pm):
        pm_time, pm_failed = draw(pm, "pm", out.with_name(AFTERNOON_NAME))
        stats["afternoon"] = summarize(pm, pm_time, pm_failed, "afternoons")

    # Overall: both commutes together, on one timeline with AM/PM labels.
    if pm is not None and len(pm):
        both = pd.concat([am.assign(half_hour=am["half_hour"] + " AM"),
                          pm.assign(half_hour=pm["half_hour"] + " PM")], ignore_index=True)
        all_time, all_failed = draw(both, "all", out.with_name(OVERALL_NAME))
        stats["overall"] = summarize(both, all_time, all_failed, "days")

    # School days with any data, morning or afternoon.
    dates = set(am["service_date"]) | (set(pm["service_date"]) if pm is not None else set())
    stats["school_days"] = len(dates)
    out.with_suffix(".json").write_text(json.dumps(stats, indent=2) + "\n")


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--out", type=Path, default=DEFAULT_OUT)
    main(p.parse_args().out)
