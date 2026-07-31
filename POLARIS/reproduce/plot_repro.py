"""
Reproduction plot for POLARIS SEAMS 2025 paper.
Generates 5-panel black/white figure matching Figure in the paper:
  1. requests/s
  2. servers (solid=active, dashed=allocated)
  3. dimmer
  4. response time with SLA threshold
  5. cumulative utility

Usage:
    python reproduce/plot_repro.py

Output: reproduce/repro1_5panel.pdf  (and .png)
"""

import sys
import os
import sqlite3
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.gridspec import GridSpec

# ── paths ──────────────────────────────────────────────────────────────────
RESULTS_DIR = os.path.join(
    os.path.dirname(__file__),
    "..", "polaris_poc", "results_swim", "results",
    "SWIM_agentic_flash25_repro1",
)
SCA = os.path.join(RESULTS_DIR, "sim-0.sca")
VEC = os.path.join(RESULTS_DIR, "sim-0.vec")
OUT_PREFIX = os.path.join(os.path.dirname(__file__), "repro1_5panel")

# ── helpers (borrowed from plot.py) ────────────────────────────────────────

def read_vector(conn, vector_name, module_name=None):
    q = f"""SELECT simtimeRaw/1e12 as x, CAST(value as REAL) as y
            FROM vector NATURAL JOIN vectorData
            WHERE vectorName='{vector_name}'"""
    if module_name:
        q += f" AND moduleName='{module_name}'"
    return pd.read_sql_query(q, conn)


def periodic_average(df, period):
    start = np.floor(df["x"].min() / period) * period
    end   = np.ceil(df["x"].max()  / period) * period
    intervals = np.arange(start + period, end + period, period)
    idx = np.searchsorted(intervals, df["x"], side="right")
    result = df.groupby(idx)["y"].mean().reset_index(drop=True)
    return pd.DataFrame({"x": intervals[: len(result)], "y": result.values})


def time_weighted_average(df, period):
    start = np.floor(df["x"].min() / period) * period
    end   = np.ceil(df["x"].max()  / period) * period
    if df["x"].max() == end:
        end += period
    intervals = np.arange(start, end + period, period)

    missing = intervals[~np.isin(intervals, df["x"].values)]
    if len(missing):
        rows = []
        for t in missing:
            mask = df["x"] < t
            if mask.any():
                rows.append({"x": t, "y": df.loc[mask, "y"].iloc[-1]})
        if rows:
            df = pd.concat([df, pd.DataFrame(rows)], ignore_index=True)

    df = df.sort_values("x").reset_index(drop=True)
    iidx = np.searchsorted(intervals, df["x"].values, side="right") - 1
    end_of = intervals[iidx] + period

    if len(df) > 1:
        next_x  = df["x"].shift(-1)
        weights = np.minimum(next_x[:-1], end_of[:-1]) - df["x"][:-1]
        exp = df[:-1].copy()
        exp["weight"]   = weights.values
        exp["interval"] = iidx[:-1]
        wm = (exp.groupby("interval")
                  .apply(lambda x: np.average(x["y"], weights=x["weight"]))
                  .values)
        return pd.DataFrame({"x": intervals[:-1][: len(wm)], "y": wm})
    return pd.DataFrame({"x": [], "y": []})


def period_utility(max_servers, max_service_rate, arrival_rate,
                   dimmer, period, rt_thresh, avg_rt, avg_srv):
    basic, opt, cost = 1.0, 1.5, 10.0
    eps = 1e-5
    Ur    = arrival_rate * ((1 - dimmer) * basic + dimmer * opt)
    Uc    = cost * (max_servers - avg_srv)
    UrOpt = arrival_rate * opt
    if avg_rt <= rt_thresh and Ur >= UrOpt - eps:
        return Ur + Uc
    elif avg_rt <= rt_thresh:
        return Ur
    else:
        return min(0.0, arrival_rate - max_servers * max_service_rate) * opt


# ── load data ───────────────────────────────────────────────────────────────

sdb = sqlite3.connect(SCA)
scalars = pd.read_sql_query("SELECT * FROM scalar", sdb)
sdb.close()

def scalar(name):
    return scalars[scalars["scalarName"] == name]["scalarValue"].iloc[0]

eval_period  = scalar("evaluationPeriod")
rt_thresh    = scalar("responseTimeThreshold")
max_servers  = scalar("maxServers")
max_svc_rate = scalar("maxServiceRate")

vdb = sqlite3.connect(VEC)

servers_raw   = read_vector(vdb, "serverCost:vector")
active_srv    = read_vector(vdb, "activeServers:vector")
brownout_raw  = read_vector(vdb, "brownoutFactor:vector")
dimmer_raw    = brownout_raw.copy(); dimmer_raw["y"] = 1 - dimmer_raw["y"]
responses     = read_vector(vdb, "lifeTime:vector")
interarrival  = read_vector(vdb, "interArrival:vector")

vdb.close()

# derived time-series
start = np.floor(servers_raw["x"].min() / eval_period) * eval_period
end   = np.ceil(servers_raw["x"].max()  / eval_period) * eval_period

avg_interarr  = periodic_average(interarrival, eval_period)
avg_arr_rate  = avg_interarr.copy(); avg_arr_rate["y"] = 1 / avg_arr_rate["y"]
avg_response  = periodic_average(responses, eval_period)

dimmer_mean  = time_weighted_average(dimmer_raw, eval_period)
dimmer_mean["x"] += eval_period
servers_mean = time_weighted_average(servers_raw, eval_period)
servers_mean["x"] += eval_period

for df in (avg_arr_rate, dimmer_mean, servers_mean, avg_response):
    df.drop(df[df["x"] > end].index, inplace=True)

utility_vals = [
    period_utility(
        max_servers, max_svc_rate,
        avg_arr_rate["y"].iloc[i],
        dimmer_mean["y"].iloc[i],
        eval_period, rt_thresh,
        avg_response["y"].iloc[i],
        servers_mean["y"].iloc[i],
    )
    for i in range(len(avg_response))
]
utility = pd.DataFrame({"x": avg_response["x"].values, "y": utility_vals})

# ── figure ──────────────────────────────────────────────────────────────────

plt.rcParams.update({
    "font.family":      "sans-serif",
    "font.size":        10,
    "axes.labelsize":   10,
    "xtick.labelsize":   9,
    "ytick.labelsize":   9,
    "axes.spines.top":  False,
    "axes.spines.right":False,
})

fig = plt.figure(figsize=(7, 10))
gs  = GridSpec(5, 1, figure=fig, hspace=0.08)

BLACK  = "black"
GRAY   = "#888888"
LGRAY  = "#dddddd"

# panel 1 – requests/s
ax1 = fig.add_subplot(gs[0])
ax1.plot(avg_arr_rate["x"], avg_arr_rate["y"], color=BLACK, linewidth=1.0)
ax1.set_ylabel("requests/s")
ax1.set_xlim(start, end)
ax1.set_ylim(bottom=0)
ax1.grid(True, color=LGRAY, linestyle="--", linewidth=0.7)
ax1.tick_params(labelbottom=False)

# panel 2 – servers
ax2 = fig.add_subplot(gs[1], sharex=ax1)
ax2.step(servers_raw["x"], servers_raw["y"],
         where="post", color=GRAY, linestyle="--", linewidth=1.2, label="allocated")
ax2.step(active_srv["x"], active_srv["y"],
         where="post", color=BLACK, linestyle="-", linewidth=1.2, label="active")
ax2.set_ylabel("servers")
ax2.set_ylim(0, max_servers + 0.5)
ax2.set_yticks(range(0, int(max_servers) + 1))
ax2.legend(loc="lower right", fontsize=8, frameon=False)
ax2.grid(True, color=LGRAY, linestyle="--", linewidth=0.7)
ax2.tick_params(labelbottom=False)

# panel 3 – dimmer
ax3 = fig.add_subplot(gs[2], sharex=ax1)
ax3.step(dimmer_raw["x"], dimmer_raw["y"],
         where="post", color=BLACK, linewidth=1.0)
ax3.set_ylabel("dimmer")
ax3.set_ylim(-0.05, 1.05)
ax3.grid(True, color=LGRAY, linestyle="--", linewidth=0.7)
ax3.tick_params(labelbottom=False)

# panel 4 – response time
ax4 = fig.add_subplot(gs[3], sharex=ax1)
ax4.plot(avg_response["x"], avg_response["y"], color=BLACK, linewidth=1.0)
ax4.axhline(rt_thresh, color=GRAY, linestyle="--", linewidth=1.0)
ax4.set_ylabel("resp. time (s)")
ax4.set_ylim(bottom=0)
ax4.grid(True, color=LGRAY, linestyle="--", linewidth=0.7)
ax4.tick_params(labelbottom=False)

# panel 5 – cumulative utility
ax5 = fig.add_subplot(gs[4], sharex=ax1)
ax5.plot(utility["x"], np.cumsum(utility["y"]), color=BLACK, linewidth=1.0)
ax5.set_ylabel("cum. utility")
ax5.set_xlabel("time (s)")
ax5.grid(True, color=LGRAY, linestyle="--", linewidth=0.7)

plt.tight_layout()

for ext in ("pdf", "png"):
    out = f"{OUT_PREFIX}.{ext}"
    fig.savefig(out, dpi=300, bbox_inches="tight")
    print(f"Saved: {out}")

# summary stats
total_util = utility["y"].sum()
pct_late   = 100 * (responses["y"] > rt_thresh).sum() / len(responses)
print(f"\nTotal utility : {round(total_util)}")
print(f"% late        : {pct_late:.1f}%")
print(f"Avg servers   : {servers_raw['y'].mean():.2f}")
