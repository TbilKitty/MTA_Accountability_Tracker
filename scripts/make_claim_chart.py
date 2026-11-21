"""Redraw the Project C charts and headline numbers from every saved commute file.

This script repeats the Project C Colab notebook step for step, so the web page
and the notebook always show the same numbers:

  1. Load every raw trip file in data/school-commute-raw/ (*-am.csv.gz is the
     ride to school, *-pm.csv.gz the ride home) and every per-stop file
     (*-stops.csv.gz, used for drive-pasts).
  2. Clean: remove duplicates, parse times, keep the two commute windows, and
     give each scheduled arrival one status using MTA's on-time rule
     (no more than 2 minutes early, no more than 7 minutes late).
  3. Measure three views: overall (both rides), morning and afternoon.
  4. Draw the charts in Maryland flag colors and write the numbers the page reads.

Writes, in docs/data/school-commute/:
  project_c_claim.png       morning, by half hour       (+ _days, _routes)
  project_c_afternoon.png   afternoon, by half hour     (+ _days, _routes)
  project_c_overall.png     both rides on one timeline  (+ _days, _routes)
  project_c_claim.json      every number the web page shows

The school-commute workflow runs this after each collection, so the GitHub
Pages site updates itself every school day.

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
CHART_NAMES = {"am": "project_c_claim", "pm": "project_c_afternoon", "all": "project_c_overall"}

# --- Maryland flag colors -------------------------------------------------
BLACK, GOLD, RED, WHITE = "#111111", "#FFB81C", "#C8102E", "#FFFFFF"
PALE_GOLD, PINK_RED, GRAY = "#FFF1CC", "#EE7D8B", "#C9C9C9"

# The five outcomes a scheduled arrival can have once its time is known.
ORDER = ["On time", "Early", "Late", "Very late", "Canceled"]
FAILED = ["Late", "Very late", "Canceled"]  # "canceled or 7+ minutes late"
LABELS = {"On time": "On time", "Early": "Early (2+ min)", "Late": "Late (7 to 15 min)",
          "Very late": "Very late (15+ min)", "Canceled": "Canceled"}
COLORS = {"On time": GOLD, "Early": GRAY, "Late": PINK_RED, "Very late": RED, "Canceled": BLACK}
# Keys the web page already uses for each outcome.
KEYS = {"On time": "on_time", "Early": "early", "Late": "late", "Very late": "severely_late",
        "Canceled": "canceled"}

WINDOWS = {
    "am": {"noun": "mornings", "xlabel": "Scheduled arrival time (AM)", "which": "morning buses",
           "title": "Morning buses are least reliable right before school starts",
           "shade": ("8:00", "8:30", "Typical bell times"), "bell": ("08:00", "09:00")},
    "pm": {"noun": "afternoons", "xlabel": "Scheduled arrival time (PM)", "which": "afternoon buses",
           "title": "The ride home: afternoon bus reliability by half hour",
           "shade": ("3:00", "3:30", "Typical dismissal times"), "bell": ("15:00", "16:00")},
    "all": {"noun": "school days", "xlabel": "Scheduled arrival time", "which": "school-commute buses",
            "title": "Across the school day: the ride to school and the ride home", "shade": None},
}


# ==========================================================================
# 1. Load
# ==========================================================================
def load_raw():
    """Every trip file (not the *-stops files), stacked into one table."""
    files = sorted(RAW.glob("*-am.csv.gz")) + sorted(RAW.glob("*-pm.csv.gz"))
    if not files:
        raise SystemExit(f"No commute files in {RAW}")
    return pd.concat([pd.read_csv(f) for f in files], ignore_index=True)


def load_stops():
    files = sorted(RAW.glob("*-stops.csv.gz"))
    return pd.concat([pd.read_csv(f) for f in files], ignore_index=True) if files else None


# ==========================================================================
# 2. Clean (same rules as Colab Steps 3 to 9)
# ==========================================================================
KEY = ["service_date", "trip_id", "stop_id", "stop_sequence"]
# Tracker labels for rows with no usable time, and what we call them.
NO_TIME = {"canceled": "Canceled", "no_realtime_record": "No record", "skipped": "Skipped",
           "trip_seen_stop_not_reached": "Unconfirmed", "trip_seen_stop_unobserved": "Unconfirmed",
           "not_monitored": "Not monitored"}


def status_of(outcome, delay_min, fuzzy):
    """One status per scheduled arrival, using MTA's -2 / +7 minute rule."""
    if outcome == "canceled":
        return "Canceled"
    if pd.isna(delay_min):
        return NO_TIME.get(outcome, "Unconfirmed")
    if fuzzy or delay_min < -30 or delay_min > 60:   # fuzzy estimate or impossible time
        return "Unconfirmed"
    if delay_min < -2:
        return "Early"
    if delay_min <= 7:
        return "On time"
    if delay_min <= 15:
        return "Late"
    return "Very late"


def clean(raw):
    df = raw.drop_duplicates(subset=KEY, keep="last").copy()
    df["scheduled"] = pd.to_datetime(df["scheduled_local"], errors="coerce")
    df["actual"] = pd.to_datetime(df["actual_local"], errors="coerce")
    df = df.dropna(subset=["scheduled"])
    hour = df["scheduled"].dt.hour + df["scheduled"].dt.minute / 60
    in_am = (df["window"] == "am") & (hour >= 6) & (hour < 9.5)
    in_pm = (df["window"] == "pm") & (hour >= 14) & (hour < 17.5)
    df = df[in_am | in_pm].copy()
    df["delay_min"] = (df["actual"] - df["scheduled"]).dt.total_seconds() / 60
    df["status"] = [status_of(o, d, u > 120) for o, d, u in
                    zip(df["outcome"], df["delay_min"], df["uncertainty_seconds"].fillna(0))]
    df["route_name"] = df["route_name"].astype(str).str.strip()
    df["half_hour"] = df["scheduled"].dt.floor("30min").dt.strftime("%I:%M").str.lstrip("0")
    df["_sort"] = df["scheduled"].dt.hour * 60 + df["scheduled"].dt.minute
    df["failed"] = df["status"].isin(FAILED)
    return df


# ==========================================================================
# 3. Measure
# ==========================================================================
def known_rows(rows):
    return rows[rows["status"].isin(ORDER)]


def breakdown(known):
    counts = known["status"].value_counts().reindex(ORDER, fill_value=0)
    pct = counts / counts.sum() * 100
    return {KEYS[o]: {"label": LABELS[o], "color": COLORS[o], "count": int(counts[o]),
                      "pct": round(float(pct[o]), 1), "display": f"{pct[o]:.0f}%"} for o in ORDER}


# The strict count: start from every scheduled arrival the tracker was watching
# and take away everything that was not a confirmed on-time bus.
FUNNEL = [("canceled", "Canceled by MTA", ["Canceled"]),
          ("missing", "Never showed up in MTA's live data", ["No record"]),
          ("skipped", "Stop skipped (flagged by MTA)", ["Skipped"]),
          ("late", "Late by more than 7 minutes", ["Late", "Very late"]),
          ("early", "Left more than 2 minutes early", ["Early"]),
          ("unverified", "Couldn't confirm the time (GPS gap or fuzzy estimate)", ["Unconfirmed"])]


def funnel(rows):
    watched = rows[rows["status"] != "Not monitored"]
    total = len(watched)
    pct = lambda n: round(n / total * 100, 1) if total else None
    steps = [{"key": k, "label": lab, "count": int(watched["status"].isin(s).sum()),
              "pct": pct(int(watched["status"].isin(s).sum()))} for k, lab, s in FUNNEL]
    on_time = int((watched["status"] == "On time").sum())
    assert total - sum(s["count"] for s in steps) == on_time, "funnel does not add up"
    return {"scheduled": total, "steps": steps, "on_time": on_time,
            "pct_on_time": pct(on_time), "display_on_time": f"{on_time / total * 100:.0f}%"}


def by_half_hour(known, label_suffix=""):
    k = known.assign(half_hour=known["half_hour"] + label_suffix)
    table = (k.groupby("half_hour")["status"].value_counts(normalize=True)
             .unstack().reindex(columns=ORDER, fill_value=0).fillna(0) * 100)
    order = k.groupby("half_hour")["_sort"].first().sort_values().index
    return table.loc[order]


def by_day(known):
    """Percent canceled or 7+ minutes late on each school day."""
    return (known.groupby("service_date")["failed"].mean() * 100).sort_index()


def worst_routes(known, min_arrivals=200, top=10):
    """Routes ranked by the share of arrivals canceled or 7+ minutes late."""
    g = known.groupby("route_name")["status"].value_counts().unstack(fill_value=0)
    g = g.reindex(columns=ORDER, fill_value=0)
    g["n"] = g[ORDER].sum(axis=1)
    g = g[g["n"] >= min_arrivals]
    pct = g[ORDER].div(g["n"], axis=0) * 100
    pct["failed"] = pct[FAILED].sum(axis=1)
    pct["n"] = g["n"]
    return pct.sort_values("failed", ascending=False), int((pct["failed"] >= 40).sum()), len(pct)


def regular_buses(known, bands, min_days=8):
    """A 'regular bus': the same route, direction, stop and scheduled time each
    school day, the bus a student would plan around. Kept if we know how it
    turned out on at least min_days days."""
    tod = known["scheduled"].dt.strftime("%H:%M")
    in_band = pd.Series(False, index=known.index)
    for lo, hi in bands:
        in_band |= (tod >= lo) & (tod < hi)
    k = known[in_band].assign(tod=tod[in_band], ok=lambda x: x["status"] == "On time")
    g = k.groupby(["window", "route_name", "direction_id", "stop_id", "tod"]).agg(
        days=("service_date", "nunique"), always_ok=("ok", "all"), fail_share=("failed", "mean"))
    g = g[g["days"] >= min_days]
    return {"buses": int(len(g)), "min_days": min_days,
            "pct_on_time_every_day": round(float(g["always_ok"].mean() * 100), 1),
            "pct_failed_1_in_5_days": round(float((g["fail_share"] >= 0.2).mean() * 100), 1),
            "display": {"on_time_every_day": f"{g['always_ok'].mean() * 100:.0f}%",
                        "failed_1_in_5_days": f"{(g['fail_share'] >= 0.2).mean() * 100:.0f}%"}}


def lateness(known):
    late = known.loc[known["status"].isin(["Late", "Very late"]), "delay_min"]
    return {"median_min": round(float(late.median()), 1), "p90_min": round(float(late.quantile(0.9)), 1),
            "display": {"median": f"{late.median():.0f}", "p90": f"{late.quantile(0.9):.0f}"}}


def drive_pasts(stops, window):
    s = stops if window == "all" else stops[stops["window"] == window]
    pct = s["drove_past"].sum() / s["visits"].sum() * 100
    return {"visits": int(s["visits"].sum()), "drove_past": int(s["drove_past"].sum()),
            "pct_drove_past": round(float(pct), 1), "display": f"{pct:.0f}%"}


# ==========================================================================
# 4. Charts (Maryland flag colors)
# ==========================================================================
def style(ax):
    ax.spines[["top", "right"]].set_visible(False)
    ax.spines[["left", "bottom"]].set_color(BLACK)
    ax.tick_params(colors=BLACK)


def footer(fig, known, window, extra=""):
    w = WINDOWS[window]
    fig.text(0.01, 0.01,
             f"MTA local bus, {known.service_date.nunique()} {'' if window == 'all' else 'school '}{w['noun']} "
             f"({known.service_date.min()} to {known.service_date.max()}), {len(known):,} scheduled arrivals"
             f"{extra}. Source: MTA real-time feed vs. GTFS schedule, collected by the author. Updated automatically.",
             fontsize=8.5, color="#555555")


def save(fig, out):
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, dpi=200, bbox_inches="tight", metadata={"Software": None})
    plt.close(fig)
    print(f"Saved {out.name}")


def draw_half_hours(table, known, window, out):
    w = WINDOWS[window]
    pct_failed = known["failed"].mean() * 100
    wide = window == "all"
    fig, ax = plt.subplots(figsize=(13, 6) if wide else (10, 6))
    bottom = pd.Series(0.0, index=table.index)
    for col in ORDER:
        ax.bar(table.index, table[col], bottom=bottom, color=COLORS[col], label=LABELS[col],
               width=0.75, edgecolor=WHITE)
        bottom += table[col]
    for i, v in enumerate(table["On time"]):  # on-time percent inside each gold bar
        ax.text(i, v / 2, f"{v:.0f}%", ha="center", va="center", color=BLACK,
                fontsize=10.5 if wide else 12, fontweight="bold")
    idx = list(table.index)
    if w["shade"] and w["shade"][0] in idx:
        first, last, text = w["shade"]
        start, end = idx.index(first), idx.index(last) if last in idx else idx.index(first)
        ax.axvspan(start - 0.5, end + 0.5, color=PALE_GOLD, zorder=0)
        ax.text((start + end) / 2, 101, text, ha="center", va="bottom", fontsize=10, color=RED,
                fontweight="bold")
    if wide:
        pm_start = next((i for i, t in enumerate(idx) if t.endswith("PM")), None)
        if pm_start:
            ax.axvline(pm_start - 0.5, color=BLACK, linestyle="--", linewidth=1)
            ax.text(pm_start / 2 - 0.5, 101, "Ride to school", ha="center", va="bottom", fontsize=10)
            ax.text((pm_start + len(idx)) / 2 - 0.5, 101, "Ride home", ha="center", va="bottom", fontsize=10)
        ax.set_xticks(range(len(idx)), [t.replace(" ", "\n") for t in idx])
    ax.set_ylim(0, 108)
    ax.set_ylabel("% of scheduled bus arrivals")
    ax.set_xlabel(w["xlabel"])
    style(ax)
    ax.legend(loc="upper left", bbox_to_anchor=(1.0, 1.0), frameon=False, reverse=True)
    ax.set_title(f"{w['title']}\nOverall, {pct_failed:.0f}% of {w['which']} were canceled or 7+ minutes late",
                 fontsize=14, fontweight="bold", loc="left", color=BLACK)
    footer(fig, known, window)
    plt.tight_layout(rect=(0, 0.04, 1, 1))
    save(fig, out)


def draw_days(days, window, known, out):
    """One bar per school day: the share canceled or 7+ minutes late."""
    fig, ax = plt.subplots(figsize=(11, 5))
    if window == "all":  # morning and afternoon side by side for each day
        x = range(len(days))
        ax.bar([i - 0.2 for i in x], days["am"], width=0.4, color=RED, label="Morning")
        ax.bar([i + 0.2 for i in x], days["pm"], width=0.4, color=BLACK, label="Afternoon")
        low = days.min().min()
        labels = days.index
    else:
        ax.bar(range(len(days)), days.values, width=0.7, color=RED)
        for i, v in enumerate(days.values):
            ax.text(i, v + 1, f"{v:.0f}%", ha="center", va="bottom", fontsize=9.5)
        low = days.min()
        labels = days.index
    # A gold line at the best day: even the best day sits well above zero.
    ax.axhline(low, color=GOLD, linewidth=2.5, zorder=0, label=f"Best day: {low:.0f}%")
    ax.legend(frameon=False, loc="upper left", bbox_to_anchor=(1.0, 1.0))
    ax.set_xticks(range(len(days)), [pd.Timestamp(d).strftime("%a\n%b %-d") for d in labels], fontsize=9)
    ax.set_ylim(0, 100)
    ax.set_ylabel("% canceled or 7+ min late")
    style(ax)
    which = WINDOWS[window]["which"]
    ax.set_title(f"No good days: {which} failed riders every single school day",
                 fontsize=14, fontweight="bold", loc="left", color=BLACK)
    footer(fig, known, window)
    plt.tight_layout(rect=(0, 0.05, 1, 1))
    save(fig, out)


def draw_routes(routes, n_bad, n_routes, window, known, out, min_arrivals):
    """The ten worst routes, split into late, very late and canceled."""
    top = routes.head(10).iloc[::-1]  # worst at the top
    fig, ax = plt.subplots(figsize=(10, 5.5))
    left = pd.Series(0.0, index=top.index)
    for col in FAILED:
        ax.barh(top.index, top[col], left=left, color=COLORS[col], label=LABELS[col], edgecolor=WHITE)
        left += top[col]
    for i, v in enumerate(top["failed"]):
        ax.text(v + 1, i, f"{v:.0f}%", va="center", fontsize=10, fontweight="bold")
    ax.set_xlim(0, 100)
    ax.set_xlabel("% of scheduled arrivals canceled or 7+ min late")
    style(ax)
    ax.legend(frameon=False, loc="lower right")
    ax.set_title(f"The 10 least reliable routes ({n_bad} of {n_routes} routes failed 40%+ of arrivals)",
                 fontsize=13, fontweight="bold", loc="left", color=BLACK)
    footer(fig, known, window, f"; routes with {min_arrivals}+ arrivals")
    plt.tight_layout(rect=(0, 0.05, 1, 1))
    save(fig, out)


# ==========================================================================
# 5. Put it together
# ==========================================================================
def measure(rows, window, stops, folder):
    """Every number and chart for one view (am, pm or all)."""
    known = known_rows(rows)
    if known.empty:
        return None
    w = WINDOWS[window]
    if window == "all":
        am, pm = known[known["window"] == "am"], known[known["window"] == "pm"]
        table = pd.concat([by_half_hour(am, " AM"), by_half_hour(pm, " PM")])
        days = pd.DataFrame({"am": by_day(am), "pm": by_day(pm)})  # a day may lack one ride
        bands = [WINDOWS["am"]["bell"], WINDOWS["pm"]["bell"]]
        min_arrivals = 400
    else:
        table = by_half_hour(known)
        days = by_day(known)
        bands = [w["bell"]]
        min_arrivals = 200
    name = CHART_NAMES[window]
    draw_half_hours(table, known, window, folder / f"{name}.png")
    draw_days(days, window, known, folder / f"{name}_days.png")
    routes, n_bad, n_routes = worst_routes(known, min_arrivals)
    draw_routes(routes, n_bad, n_routes, window, known, folder / f"{name}_routes.png", min_arrivals)

    pct_failed = known["failed"].mean() * 100
    pct_on_time = (known["status"] == "On time").mean() * 100
    day_fail = days.stack().dropna() if window == "all" else days
    stats = {
        "breakdown": breakdown(known),
        f"school_{w['noun'].replace('school ', '')}": int(known["service_date"].nunique()),
        "first_date": str(known.service_date.min()),
        "last_date": str(known.service_date.max()),
        "scheduled_arrivals": int(len(known)),
        "pct_on_time": round(float(pct_on_time), 1),
        "pct_canceled_or_late": round(float(pct_failed), 1),
        "pct_on_time_by_half_hour": {t: round(float(v), 1) for t, v in table["On time"].items()},
        "display": {"canceled_or_late": f"{pct_failed:.0f}%", "on_time": f"{pct_on_time:.0f}%"},
        "funnel": funnel(rows),
        "drive_pasts": drive_pasts(stops, window) if stops is not None else None,
        "by_day": {"best_pct": round(float(day_fail.min()), 1), "worst_pct": round(float(day_fail.max()), 1),
                   "display": {"best": f"{day_fail.min():.0f}%", "worst": f"{day_fail.max():.0f}%"}},
        "regular_buses": regular_buses(known, bands),
        "lateness": lateness(known),
        "worst_routes": {"routes_ranked": n_routes, "routes_40_plus": n_bad, "min_arrivals": min_arrivals,
                         "top": [{"route": r, "pct_failed": round(float(v), 1)}
                                 for r, v in routes["failed"].head(10).items()]},
    }
    return stats, table


def main(out):
    folder = out.parent
    rows = clean(load_raw())
    stops = load_stops()

    stats, am_table = measure(rows[rows["window"] == "am"], "am", stops, folder)
    # Morning extras: the hour before school (8:00 and 8:30 blocks) and 6:00.
    peak = [t for t in ("8:00", "8:30") if t in am_table.index]
    if peak:
        v = am_table.loc[peak, "On time"].mean()
        stats["pct_on_time_8_to_9"] = round(float(v), 1)
        stats["display"]["on_time_8_to_9"] = f"{v:.0f}%"
    if "6:00" in am_table.index:
        stats["display"]["on_time_6"] = f"{am_table.loc['6:00', 'On time']:.0f}%"

    stats["afternoon"] = None
    pm_rows = rows[rows["window"] == "pm"]
    if len(known_rows(pm_rows)):
        pm, pm_table = measure(pm_rows, "pm", stops, folder)
        aft = [t for t in ("3:00", "3:30") if t in pm_table.index]
        if aft:
            v = pm_table.loc[aft, "On time"].mean()
            pm["pct_on_time_3_to_4"] = round(float(v), 1)
            pm["display"]["on_time_3_to_4"] = f"{v:.0f}%"
        if "2:00" in pm_table.index:
            pm["display"]["on_time_2"] = f"{pm_table.loc['2:00', 'On time']:.0f}%"
        stats["afternoon"] = pm
        stats["overall"], _ = measure(rows, "all", stops, folder)

    stats["school_days"] = int(known_rows(rows)["service_date"].nunique())
    out.with_suffix(".json").write_text(json.dumps(stats, indent=2) + "\n")
    print(f"Morning {stats['display']['canceled_or_late']} canceled or 7+ late; "
          f"afternoon {stats['afternoon']['display']['canceled_or_late'] if stats['afternoon'] else '-'}")


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--out", type=Path, default=DEFAULT_OUT)
    main(p.parse_args().out)
