"""Redraw the Project C morning on-time chart from every saved morning file.

Same logic as the Project C Colab notebook (project_c_analysis.ipynb):
read data/school-commute-raw/*-am.csv.gz, keep rows with a known outcome,
group by half hour of scheduled arrival (6:00 to 9:00 blocks), and draw one
stacked bar per half hour. The school-commute workflow runs this after each
collection, so the GitHub Pages site always shows the latest chart. It also
writes the headline numbers to project_c_claim.json next to the image, which
the home page reads so its text matches the chart.

Usage: python scripts/make_claim_chart.py [--out PATH]
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

ORDER = ["on_time", "early", "late", "severely_late", "canceled"]
LABELS = {"on_time": "On time", "early": "Early (2+ min)", "late": "Late (7 to 15 min)",
          "severely_late": "Very late (15+ min)", "canceled": "Canceled"}
COLORS = {"on_time": "#2E8B57", "early": "#B8B8B8", "late": "#F2A541",
          "severely_late": "#D1495B", "canceled": "#3D2C3E"}


def load_known():
    # Morning trip-level files only; skips -pm and the -am-stops summaries.
    files = sorted(RAW.glob("*-am.csv.gz"))
    if not files:
        raise SystemExit(f"No morning files in {RAW}")
    df = pd.concat([pd.read_csv(f) for f in files], ignore_index=True)
    known = df[df["outcome"].isin(ORDER)].copy()
    # Round each scheduled time down to its half hour; drop 9:30 (window ends then).
    half = pd.to_datetime(known["scheduled_local"]).dt.floor("30min")
    known["half_hour"] = half.dt.strftime("%I:%M").str.lstrip("0")
    known["_sort"] = half.dt.hour * 60 + half.dt.minute
    return known[known["half_hour"] != "9:30"]


def afternoon_stats():
    """Same measure as the morning claim, for the afternoon ride home (supporting context)."""
    files = sorted(RAW.glob("*-pm.csv.gz"))
    if not files:
        return None
    df = pd.concat([pd.read_csv(f) for f in files], ignore_index=True)
    known = df[df["outcome"].isin(ORDER)]
    failed = known["outcome"].isin(["late", "severely_late", "canceled"]).mean() * 100
    on_time = (known["outcome"] == "on_time").mean() * 100
    return {
        "school_afternoons": int(known["service_date"].nunique()),
        "scheduled_arrivals": int(len(known)),
        "pct_on_time": round(float(on_time), 1),
        "pct_canceled_or_late": round(float(failed), 1),
        "display": {"canceled_or_late": f"{failed:.0f}%", "on_time": f"{on_time:.0f}%"},
    }


def draw(known, out):
    failed = known["outcome"].isin(["late", "severely_late", "canceled"])
    pct_failed = failed.mean() * 100
    by_time = (known.groupby("half_hour")["outcome"].value_counts(normalize=True)
               .unstack().reindex(columns=ORDER, fill_value=0).fillna(0) * 100)
    order = known.groupby("half_hour")["_sort"].first().sort_values().index
    by_time = by_time.loc[order]

    fig, ax = plt.subplots(figsize=(10, 6))
    bottom = pd.Series(0.0, index=by_time.index)
    for col in ORDER:
        ax.bar(by_time.index, by_time[col], bottom=bottom, color=COLORS[col],
               label=LABELS[col], width=0.75, edgecolor="white")
        bottom += by_time[col]
    for i, v in enumerate(by_time["on_time"]):
        ax.text(i, v / 2, f"{v:.0f}%", ha="center", va="center", color="white",
                fontsize=12, fontweight="bold")

    # Shade the 8:00 and 8:30 blocks, the usual school start window.
    idx = list(by_time.index)
    if "8:00" in idx:
        start = idx.index("8:00")
        end = idx.index("8:30") if "8:30" in idx else start
        ax.axvspan(start - 0.5, end + 0.5, color="#FFE8A3", alpha=0.45, zorder=0)
        ax.text((start + end) / 2, 101, "Typical bell times", ha="center", va="bottom", fontsize=10)

    ax.set_ylim(0, 108)
    ax.set_ylabel("% of scheduled bus arrivals")
    ax.set_xlabel("Scheduled arrival time (AM)")
    ax.spines[["top", "right"]].set_visible(False)
    ax.legend(loc="upper left", bbox_to_anchor=(1.0, 1.0), frameon=False, reverse=True)

    days = known["service_date"].nunique()
    ax.set_title("Morning buses are least reliable right before school starts\n"
                 f"Overall, {pct_failed:.0f}% of morning buses were canceled or 7+ minutes late",
                 fontsize=14, fontweight="bold", loc="left")
    fig.text(0.01, 0.01,
             f"MTA local bus, {days} school mornings ({known.service_date.min()} to "
             f"{known.service_date.max()}), {len(known):,} scheduled arrivals. "
             "Source: MTA real-time feed vs. GTFS schedule, collected by the author. Updated automatically.",
             fontsize=8.5, color="gray")
    plt.tight_layout(rect=(0, 0.04, 1, 1))
    out.parent.mkdir(parents=True, exist_ok=True)
    # Fixed metadata so the PNG only changes when the data does.
    fig.savefig(out, dpi=200, bbox_inches="tight", metadata={"Software": None})
    # Headline numbers for the home page, from the same data as the chart.
    peak = [t for t in ("8:00", "8:30") if t in by_time.index]
    stats = {
        "school_mornings": int(days),
        "first_date": str(known.service_date.min()),
        "last_date": str(known.service_date.max()),
        "scheduled_arrivals": int(len(known)),
        "pct_on_time": round(float((known["outcome"] == "on_time").mean() * 100), 1),
        "pct_canceled_or_late": round(float(pct_failed), 1),
        "pct_on_time_8_to_9": round(float(by_time.loc[peak, "on_time"].mean()), 1) if peak else None,
        "pct_on_time_by_half_hour": {t: round(float(v), 1) for t, v in by_time["on_time"].items()},
    }
    # Pre-formatted the same way as the chart labels, so the page and the
    # chart always show the same rounded numbers.
    stats["display"] = {
        "canceled_or_late": f"{pct_failed:.0f}%",
        "on_time_8_to_9": f"{by_time.loc[peak, 'on_time'].mean():.0f}%" if peak else None,
        "on_time_6": f"{by_time.loc['6:00', 'on_time']:.0f}%" if "6:00" in by_time.index else None,
    }
    stats["afternoon"] = afternoon_stats()
    out.with_suffix(".json").write_text(json.dumps(stats, indent=2) + "\n")
    print(f"Saved {out} ({days} mornings, {len(known):,} arrivals, {pct_failed:.0f}% failed)")


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--out", type=Path, default=DEFAULT_OUT)
    draw(load_known(), p.parse_args().out)
