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
import numpy as np
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


STOP_AREAS = ROOT / "data" / "reference" / "stop_areas.csv"
INCOME_QUARTERS = ["Lowest income", "Lower middle", "Upper middle", "Highest income"]


def load_stop_areas():
    """Each stop's census tract, whether it is inside Baltimore City, and the
    tract's income and poverty rate (built by scripts/build_stop_areas.py)."""
    if not STOP_AREAS.exists():
        return None
    a = pd.read_csv(STOP_AREAS, dtype={"stop_id": str, "tract_geoid": str})
    # Income quarters: split the city's tracts (not stops) into four equal groups.
    city = a[a["in_baltimore_city"]].drop_duplicates("tract_geoid").dropna(subset=["median_household_income"])
    cuts = city["median_household_income"].quantile([0.25, 0.5, 0.75]).tolist()
    a["income_quarter"] = pd.cut(a["median_household_income"], [-np.inf, *cuts, np.inf], labels=INCOME_QUARTERS)
    a.attrs["income_cuts"] = cuts
    return a


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
# 4b. How strong is the evidence? (confidence intervals and consistency)
# ==========================================================================
BOOT_N, SEED = 2000, 2026   # fixed seed: the Colab gets the very same intervals


def day_totals(known, flag):
    """Per school day: how many arrivals had the flag, and how many in all."""
    return known.assign(_f=flag).groupby("service_date")["_f"].agg(["sum", "count"])


def boot_pct(d, rng_seed=SEED):
    """95% confidence interval for a percentage, resampling whole school days.

    Buses on the same day share weather, traffic and staffing, so the honest
    unit of chance is the day, not the single arrival (a 'cluster bootstrap').
    """
    rng = np.random.default_rng(rng_seed)
    idx = rng.integers(0, len(d), (BOOT_N, len(d)))
    sims = d["sum"].values[idx].sum(1) / d["count"].values[idx].sum(1) * 100
    lo, hi = np.percentile(sims, [2.5, 97.5])
    return {"pct": round(float(d["sum"].sum() / d["count"].sum() * 100), 1),
            "lo": round(float(lo), 1), "hi": round(float(hi), 1),
            "display": f"{lo:.0f}% to {hi:.0f}%"}


def boot_diff(a, b, rng_seed=SEED):
    """95% interval for (rate in b) minus (rate in a), resampling shared days."""
    both = a.index.intersection(b.index)
    a, b = a.loc[both], b.loc[both]
    rng = np.random.default_rng(rng_seed)
    idx = rng.integers(0, len(both), (BOOT_N, len(both)))
    rate = lambda d: d["sum"].values[idx].sum(1) / d["count"].values[idx].sum(1) * 100
    sims = rate(b) - rate(a)
    lo, hi = np.percentile(sims, [2.5, 97.5])
    diff = (b["sum"].sum() / b["count"].sum() - a["sum"].sum() / a["count"].sum()) * 100
    worse_days = int(((b["sum"] / b["count"]) > (a["sum"] / a["count"])).sum())
    return {"diff": round(float(diff), 1), "lo": round(float(lo), 1), "hi": round(float(hi), 1),
            "days": len(both), "days_b_worse": worse_days,
            "display": f"{diff:+.0f} points (95% CI {lo:+.0f} to {hi:+.0f})"}


def consistency(known, min_arrivals=200, bar=20):
    """Split the data into day-by-half-hour blocks. In what share of blocks did
    more than `bar`% of buses fail? A claim that only held at a few times or on a
    few days would show up here."""
    c = known.groupby(["window", "service_date", "half_hour"])["failed"].agg(["mean", "size"])
    c = c[c["size"] >= min_arrivals]
    share = (c["mean"] * 100 >= bar).mean() * 100
    return {"blocks": int(len(c)), "bar_pct": bar, "pct_blocks_at_or_above": round(float(share), 1),
            "lowest_block_pct": round(float(c["mean"].min() * 100), 1),
            "display": f"{share:.0f}%"}


def strength(known, window):
    on_time = known["status"] == "On time"
    out = {"failed_ci": boot_pct(day_totals(known, known["failed"])),
           "on_time_ci": boot_pct(day_totals(known, on_time)),
           "consistency": consistency(known)}
    if window in ("am", "pm"):
        bell = ["8:00", "8:30"] if window == "am" else ["3:00", "3:30"]
        k = known[known["half_hour"].isin(bell)]
        out["bell_on_time_ci"] = boot_pct(day_totals(k, k["status"] == "On time"))
    else:
        am, pm = known[known["window"] == "am"], known[known["window"] == "pm"]
        out["pm_minus_am"] = boot_diff(day_totals(am, am["failed"]), day_totals(pm, pm["failed"]))
    return out


# ==========================================================================
# 4c. Poorer vs. wealthier neighborhoods
# ==========================================================================
POVERTY_AREA = 20  # Census Bureau: a "poverty area" is a tract where 20%+ live below poverty


def neighborhoods(known):
    """Failure rate at stops in high-poverty tracts vs. the rest of the city,
    plus by income quarter (four equal-sized groups of city tracts)."""
    k = known.dropna(subset=["poverty_rate"])
    high = k["poverty_rate"] >= POVERTY_AREA
    hi_d, lo_d = day_totals(k[high], k.loc[high, "failed"]), day_totals(k[~high], k.loc[~high, "failed"])
    out = {"high_poverty": {**boot_pct(hi_d), "arrivals": int(high.sum()), "stops": int(k.loc[high, "stop_id"].nunique())},
           "lower_poverty": {**boot_pct(lo_d), "arrivals": int((~high).sum()), "stops": int(k.loc[~high, "stop_id"].nunique())},
           "high_minus_lower": boot_diff(lo_d, hi_d)}
    q = k.dropna(subset=["income_quarter"])
    out["by_income_quarter"] = []
    for name in INCOME_QUARTERS:
        g = q[q["income_quarter"] == name]
        if len(g):
            out["by_income_quarter"].append({"group": name, "arrivals": int(len(g)),
                                             **boot_pct(day_totals(g, g["failed"]))})
    return out


def model(known):
    """Logistic regression: is a bus in a high-poverty tract more likely to fail
    once we compare stops on the same route, at the same commute and half hour?
    Standard errors are clustered by school day (same reason as the bootstrap)."""
    import statsmodels.formula.api as smf
    k = known.dropna(subset=["poverty_rate"]).assign(
        y=lambda x: x["failed"].astype(int),
        high_poverty=lambda x: (x["poverty_rate"] >= POVERTY_AREA).astype(int))
    fit = smf.logit("y ~ high_poverty + C(route_name) + C(window) + C(half_hour)", data=k).fit(
        disp=0, maxiter=200, cov_type="cluster", cov_kwds={"groups": pd.factorize(k["service_date"])[0]})
    or_, (lo, hi) = np.exp(fit.params["high_poverty"]), np.exp(fit.conf_int().loc["high_poverty"])
    return {"odds_ratio": round(float(or_), 2), "lo": round(float(lo), 2), "hi": round(float(hi), 2),
            "p_value": float(fit.pvalues["high_poverty"]), "arrivals": int(len(k)),
            "display": f"{or_:.2f} (95% CI {lo:.2f} to {hi:.2f})"}


def draw_strength(rows_by_view, folder):
    """'How sure are we': each headline percentage with its 95% interval."""
    items = [(label, s) for label, s in rows_by_view if s]
    fig, ax = plt.subplots(figsize=(10, 3))
    for i, (label, ci) in enumerate(items[::-1]):
        ax.plot([ci["lo"], ci["hi"]], [i, i], color=BLACK, linewidth=3, solid_capstyle="butt")
        ax.plot(ci["pct"], i, "o", color=RED, markersize=11, markeredgecolor=BLACK)
        ax.text(ci["hi"] + 1.2, i, f"{ci['pct']:.0f}%  ({ci['lo']:.0f} to {ci['hi']:.0f})", va="center", fontsize=10.5)
    ax.set_yticks(range(len(items)), [l for l, _ in items[::-1]])
    ax.set_xlim(0, 100)
    ax.axvspan(0, 100, ymin=0, ymax=1, color=WHITE, zorder=-2)
    ax.set_xlabel("% of buses canceled or 7+ minutes late (dot) with 95% confidence interval (bar)")
    style(ax)
    ax.set_title("How sure are we? Even the low end of every range is far from reliable",
                 fontsize=13, fontweight="bold", loc="left", color=BLACK)
    plt.tight_layout()
    save(fig, folder / "project_c_strength.png")


def draw_neighborhoods(nb_am, nb_pm, folder):
    """Failure rate by neighborhood income quarter, morning and afternoon, with 95% intervals."""
    fig, ax = plt.subplots(figsize=(10, 5))
    groups = [g["group"] for g in nb_am["by_income_quarter"]]
    x = np.arange(len(groups))
    for off, nb, color, label in [(-0.2, nb_am, RED, "Morning"), (0.2, nb_pm, BLACK, "Afternoon")]:
        v = nb["by_income_quarter"]
        pct = np.array([g["pct"] for g in v])
        err = np.array([[g["pct"] - g["lo"] for g in v], [g["hi"] - g["pct"] for g in v]])
        ax.bar(x + off, pct, width=0.4, color=color, label=label, yerr=err, capsize=4,
               error_kw={"ecolor": GOLD if color == BLACK else BLACK, "elinewidth": 2})
        for xi, p in zip(x + off, pct):
            ax.text(xi, 2, f"{p:.0f}%", ha="center", va="bottom", color=WHITE, fontweight="bold")
    ax.set_xticks(x, [g.replace(" (", "\n(") for g in groups])
    ax.set_ylim(0, 70)
    ax.set_ylabel("% canceled or 7+ min late")
    style(ax)
    ax.legend(frameon=False, loc="upper left", bbox_to_anchor=(1.0, 1.0))
    ax.set_title("Stops in poorer and wealthier Baltimore neighborhoods", fontsize=13, fontweight="bold",
                 loc="left", color=BLACK)
    fig.text(0.01, 0.01, "Neighborhood = census tract of the stop. Income: ACS 2019-2023 median household income. "
             "Bars: 95% confidence intervals (resampling school days).", fontsize=8.5, color="#555555")
    plt.tight_layout(rect=(0, 0.05, 1, 1))
    save(fig, folder / "project_c_neighborhoods.png")


def tract_stats(rows, min_arrivals=100):
    """Reliability for each city census tract, for the hover map on the web page.
    Tracts with fewer than min_arrivals known arrivals are marked as too little data."""
    out = {}
    for view, sub in [("all", rows), ("am", rows[rows["window"] == "am"]), ("pm", rows[rows["window"] == "pm"])]:
        k = known_rows(sub).dropna(subset=["tract_geoid"])
        measured = k[k["status"] != "Canceled"]
        g = k.groupby("tract_geoid")
        table = pd.DataFrame({
            "arrivals": g.size(),
            "stops": g["stop_id"].nunique(),
            "pct_failed": g["failed"].mean() * 100,
            "pct_on_time": g["status"].apply(lambda x: (x == "On time").mean() * 100),
            "pct_canceled": g["status"].apply(lambda x: (x == "Canceled").mean() * 100),
            # Service time: how far from schedule buses that ran actually were, on average.
            "avg_delay_min": measured.groupby("tract_geoid")["delay_min"].mean(),
            "median_delay_min": measured.groupby("tract_geoid")["delay_min"].median(),
        }).round(1)
        for geoid, r in table.iterrows():
            out.setdefault(geoid, {})[view] = {**{c: (None if pd.isna(v) else float(v)) for c, v in r.items()},
                                               "enough_data": bool(r["arrivals"] >= min_arrivals)}
            out[geoid][view]["arrivals"] = int(r["arrivals"])
            out[geoid][view]["stops"] = int(r["stops"])
    return {"min_arrivals": min_arrivals, "tracts": out}


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
        "strength": strength(known, window),
    }
    if "poverty_rate" in known.columns:
        stats["neighborhoods"] = neighborhoods(known)
        if window == "all":
            stats["neighborhoods"]["model"] = model(known)
    return stats, table


def main(out):
    folder = out.parent
    rows = clean(load_raw())
    stops = load_stops()

    # Keep only stops inside Baltimore City (Colab Step 10).
    areas = load_stop_areas()
    scope = {"city_only": False}
    if areas is not None:
        rows["stop_id"] = rows["stop_id"].astype(str)
        before_stops, before_known = rows["stop_id"].nunique(), len(known_rows(rows))
        rows = rows.merge(areas[["stop_id", "in_baltimore_city", "tract_geoid", "median_household_income",
                                 "poverty_rate", "income_quarter"]], on="stop_id", how="left")
        rows = rows[rows["in_baltimore_city"].fillna(False).astype(bool)].copy()
        if stops is not None:
            stops = stops[stops["stop_id"].astype(str).isin(rows["stop_id"])]
        scope = {"city_only": True, "stops_kept": int(rows["stop_id"].nunique()), "stops_before": int(before_stops),
                 "arrivals_kept": int(len(known_rows(rows))), "arrivals_before": int(before_known),
                 "income_cuts": [round(c) for c in areas.attrs["income_cuts"]]}

    stats, am_table = measure(rows[rows["window"] == "am"], "am", stops, folder)
    # Morning extras: the hour before school (8:00 to 9:00, pooled) and 6:00.
    bell = stats["strength"].get("bell_on_time_ci")
    if bell:
        stats["pct_on_time_8_to_9"] = bell["pct"]
        stats["display"]["on_time_8_to_9"] = f"{bell['pct']:.0f}%"
    if "6:00" in am_table.index:
        stats["display"]["on_time_6"] = f"{am_table.loc['6:00', 'On time']:.0f}%"

    stats["afternoon"] = None
    pm_rows = rows[rows["window"] == "pm"]
    if len(known_rows(pm_rows)):
        pm, pm_table = measure(pm_rows, "pm", stops, folder)
        bell = pm["strength"].get("bell_on_time_ci")
        if bell:
            pm["pct_on_time_3_to_4"] = bell["pct"]
            pm["display"]["on_time_3_to_4"] = f"{bell['pct']:.0f}%"
        if "2:00" in pm_table.index:
            pm["display"]["on_time_2"] = f"{pm_table.loc['2:00', 'On time']:.0f}%"
        stats["afternoon"] = pm
        stats["overall"], _ = measure(rows, "all", stops, folder)
        draw_strength([("Overall", stats["overall"]["strength"]["failed_ci"]),
                       ("Morning", stats["strength"]["failed_ci"]),
                       ("Afternoon", pm["strength"]["failed_ci"])], folder)
        if "neighborhoods" in stats:
            draw_neighborhoods(stats["neighborhoods"], pm["neighborhoods"], folder)

    stats["scope"] = scope
    if scope["city_only"]:  # per-tract numbers for the hover map
        (folder / "tract_stats.json").write_text(json.dumps(tract_stats(rows)) + "\n")
    stats["school_days"] = int(known_rows(rows)["service_date"].nunique())
    out.with_suffix(".json").write_text(json.dumps(stats, indent=2) + "\n")
    print(f"Morning {stats['display']['canceled_or_late']} canceled or 7+ late; "
          f"afternoon {stats['afternoon']['display']['canceled_or_late'] if stats['afternoon'] else '-'}")


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--out", type=Path, default=DEFAULT_OUT)
    main(p.parse_args().out)
