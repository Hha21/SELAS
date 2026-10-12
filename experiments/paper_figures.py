#!/usr/bin/env python3
"""The paper's figures, styled for an IEEE two-column conference (SEAMS/ICSE).

Style: a Times-metric TrueType serif (Liberation Serif) at 7-8 pt, the width of one
column (3.5 in) or of the page (7.16 in), fonts embedded as TrueType for the
IEEE PDF checks, thin marks and a hairline grid. Colour comes from the
reference categorical palette in slot order -- blue, orange, aqua -- which
passes every all-pairs CVD and normal-vision gate on a white page; aqua is under
3:1 contrast there, so every series also has its own marker or line style,
which carries identity in greyscale too. Text is set in ink, never in a series
colour, and a reference (another controller, or a null) is grey.

    python experiments/paper_figures.py -o figures/paper [--only models battery patch]

  models     (page width) Utility per model with and without reasoning, with the
             objective stated (a) and not (b); dots are runs, ticks are means;
             PLA and Thallium as reference lines.
  reasoning  (column) Panel (a) of ``models`` alone.
  battery    (column) Share of decisions whose action changes under each
             intervention, for decisions to act and to do nothing.
  patch      (column) Edit and patch: share of decisions moved to the option
             the edited NLA explanation names, by strength, with and without
             reasoning.
"""

from __future__ import annotations

import argparse
import json
import statistics as st
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from matplotlib.ticker import FuncFormatter

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE / "controller_comparison"))
sys.path.insert(0, str(HERE / "nla"))
from reasoning_plot import ROWS  # noqa: E402

# Reference categorical palette, light mode, slots 1-3 in order; text tokens.
BLUE, ORANGE, AQUA = "#2a78d6", "#eb6834", "#1baf7a"
INK, INK2, MUTED = "#0b0b0b", "#52514e", "#8c8b85"
GRID, AXIS = "#e4e3df", "#a9a8a2"
COL, PAGE = 3.5, 7.16                      # IEEE column and page widths, inches

ARMS = [{"label": "With reasoning", "color": BLUE, "marker": "o"},
        {"label": "Without reasoning", "color": ORANGE, "marker": "D"}]
SPLITS = [("action", "Decisions to act", BLUE, "D"),
          ("no_op", "Decisions to do nothing", ORANGE, "o")]


def style() -> None:
    plt.rcParams.update({
        "font.family": "serif",
        "font.serif": ["Liberation Serif", "Times New Roman", "TeX Gyre Termes", "Nimbus Roman"],
        "mathtext.fontset": "stix",
        "font.size": 8, "axes.titlesize": 8, "axes.labelsize": 8,
        "xtick.labelsize": 7, "ytick.labelsize": 7, "legend.fontsize": 7,
        "text.color": INK, "axes.labelcolor": INK, "axes.titlecolor": INK,
        "xtick.color": INK2, "ytick.color": INK2,
        "axes.edgecolor": AXIS, "axes.linewidth": 0.5,
        "xtick.major.width": 0.5, "ytick.major.width": 0.5,
        "xtick.major.size": 2.5, "ytick.major.size": 2.5,
        "grid.color": GRID, "grid.linewidth": 0.5,
        "legend.frameon": False, "legend.handletextpad": 0.4, "legend.columnspacing": 1.2,
        "lines.linewidth": 1.1, "lines.markersize": 3.5,
        "pdf.fonttype": 42, "ps.fonttype": 42,
        "figure.facecolor": "white", "axes.facecolor": "white",
        "savefig.bbox": "tight", "savefig.pad_inches": 0.02,
    })


def clean(ax, keep_left: bool = True) -> None:
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    if not keep_left:
        ax.spines["left"].set_visible(False)
        ax.tick_params(axis="y", length=0)


def kilo(v, _pos) -> str:
    if v == 0:
        return "0"
    s = f"{abs(v) / 1000:g}K"
    return ("−" if v < 0 else "") + s


def save(fig, out: Path) -> None:
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out.with_suffix(".pdf"))
    fig.savefig(out.with_suffix(".png"), dpi=300)
    plt.close(fig)
    print(f"wrote {out}.pdf and .png")


# -- models / reasoning --------------------------------------------------------
PANELS = [("(a) Objective stated", ("cot", "direct")), ("(b) No objective", ("cot-noobj", "direct-noobj"))]


def references(ax, refs: list[tuple[str, float]], top: float) -> None:
    """Grey reference lines, one dash pattern each; of two neighbours the lower
    is labelled on its left and the higher on its right."""
    dashes = [(0, (1, 1.5)), (0, (4, 2))]
    refs = sorted(refs, key=lambda r: r[1])
    for k, (name, v) in enumerate(refs):
        ax.axvline(v, color=INK2, lw=0.7, ls=dashes[k % len(dashes)], zorder=1)
        left = k % 2 == 0 and k + 1 < len(refs)
        ax.text(v, top, f"{name} " if left else f" {name}", color=INK2, fontsize=6.5,
                va="bottom", ha="right" if left else "left")


def models(table: Path, refs: list[tuple[str, float]], out: Path, panels=PANELS, width=PAGE) -> None:
    T = json.loads(table.read_text())
    rows = [(k, lab.replace("*", "†")) for k, lab in ROWS if k in T]
    n = len(rows)
    fig, axes = plt.subplots(1, len(panels), sharey=True, sharex=True, squeeze=False,
                             figsize=(width, 0.2 * n + 0.75))
    axes = axes[0]
    for ax, (title, arms) in zip(axes, panels):
        for i, (key, _) in enumerate(rows):
            y0 = n - 1 - i
            if i:
                ax.axhline(y0 + 0.5, color=GRID, lw=0.4, zorder=0)
            for arm, s, off in zip(arms, ARMS, (0.18, -0.18)):
                u = (T[key].get(arm) or {}).get("utility") or []
                if not u:
                    continue
                ax.scatter(u, [y0 + off] * len(u), s=11, marker=s["marker"], facecolor=s["color"],
                           edgecolor="white", linewidth=0.35, alpha=0.9, zorder=3)
                m = st.mean(u)
                ax.plot([m, m], [y0 + off - 0.16, y0 + off + 0.16], color=INK, lw=1.1, zorder=4,
                        solid_capstyle="butt")
        references(ax, refs, n - 0.45)
        ax.set_title(title, loc="left", pad=9)
        ax.xaxis.set_major_formatter(FuncFormatter(kilo))
        ax.grid(axis="x")
        ax.set_axisbelow(True)
        clean(ax, keep_left=False)
    axes[0].set_yticks(range(n))
    axes[0].set_yticklabels([lab for _, lab in reversed(rows)], color=INK)
    axes[0].set_ylim(-0.6, n - 0.4)
    fig.supxlabel("Utility (SEAMS 2017A utility function)", fontsize=8, y=0.01)
    handles = [Line2D([], [], ls="none", marker=s["marker"], color=s["color"], markeredgecolor="white",
                      markeredgewidth=0.35, markersize=4.2, label=s["label"]) for s in ARMS]
    handles.append(Line2D([], [], ls="none", marker="|", color=INK, markersize=6, markeredgewidth=1.1,
                          label="Mean of 10 runs"))
    fig.legend(handles=handles, loc="lower center", bbox_to_anchor=(0.5, 1.0), ncol=3,
               borderaxespad=0.0)
    fig.tight_layout(pad=0.3, w_pad=1.0)
    save(fig, out)


# -- battery -------------------------------------------------------------------
BATTERY = [
    ("(a) Reasoning perturbed", [
        ("faith/original", "Re-scored as recorded"),
        ("faith/paraphrase", "Reworded"),
        ("faith/corrupt", "SLA verdict negated"),
        ("faith/truncate_3", "Conclusion removed"),
        ("faith/ablate", "Reasoning removed"),
        ("faith/filler", "Replaced by filler"),
        ("shuffled|concludes otherwise", "Another period's, other conclusion"),
    ]),
    ("(b) One telemetry value pushed each way", [
        ("cf_score/pair:rt_breached|rt_met", "Response time, reasoning kept"),
        ("cf_generate/pair:rt_breached|rt_met", "Response time, regenerated"),
        ("cf_score/pair:load_high|load_low", "Load, reasoning kept"),
        ("cf_generate/pair:load_high|load_low", "Load, regenerated"),
        ("cf_score/pair:spare_none|spare_ample", "Spare capacity, reasoning kept"),
        ("cf_generate/pair:spare_none|spare_ample", "Spare capacity, regenerated"),
    ]),
    ("(c) Objective removed", [
        ("med_combined>none/direct", "Reasoning kept"),
        ("med_combined>none/total", "Reasoning regenerated"),
        ("med_combined>none/reason", "Regenerated, scored with objective"),
    ]),
]


def battery(battery_json: Path, shuffled_json: Path, out: Path) -> None:
    M = json.loads(battery_json.read_text())["measures"]
    S = json.loads(shuffled_json.read_text())

    def get(key: str, split: str):
        if key.startswith("shuffled|"):
            return S.get(f"{split}|{key.split('|', 1)[1]}")
        return (M.get(key) or {}).get(split)

    heights = [len(r) for _, r in BATTERY]
    fig, axes = plt.subplots(len(BATTERY), 1, sharex=True, figsize=(COL, 0.165 * sum(heights) + 0.95),
                             gridspec_kw={"height_ratios": heights, "hspace": 0.42})
    for ax, (title, rows) in zip(axes, BATTERY):
        n = len(rows)
        for i, (key, _) in enumerate(rows):
            y = n - 1 - i
            for (split, _, color, marker), off in zip(SPLITS, (0.15, -0.15)):
                s = get(key, split)
                if not s:
                    continue
                r, lo, hi = 100 * s["rate"], 100 * s["lo"], 100 * s["hi"]
                ax.plot([lo, hi], [y + off] * 2, color=color, lw=0.9, solid_capstyle="round", zorder=2)
                ax.plot([r], [y + off], ls="none", marker=marker, markersize=3.6, color=color,
                        markeredgecolor="white", markeredgewidth=0.35, zorder=3)
        ax.set_yticks(range(n))
        ax.set_yticklabels([lab for _, lab in reversed(rows)], color=INK)
        ax.set_ylim(-0.6, n - 0.4)
        ax.set_title(title, loc="left", pad=3)
        ax.set_xlim(-2, 102)
        ax.set_xticks([0, 25, 50, 75, 100])
        ax.grid(axis="x")
        ax.set_axisbelow(True)
        clean(ax, keep_left=False)
    axes[-1].set_xlabel("Decisions whose action changes (%)")
    handles = [Line2D([], [], color=c, marker=m, markersize=3.6, markeredgecolor="white",
                      markeredgewidth=0.35, lw=0.9, label=lab) for _, lab, c, m in SPLITS]
    fig.canvas.draw()       # the legend sits just above the first panel's title
    title_top = axes[0].title.get_window_extent().y1 / fig.bbox.height
    fig.legend(handles=handles, loc="lower center", bbox_to_anchor=(0.5, title_top + 0.02), ncol=2,
               borderaxespad=0.0)
    save(fig, out)


# -- patch ---------------------------------------------------------------------
DIRECTIONS = {   # cond -> (label, colour, line style, marker, measure)
    "nla": ("NLA edit", BLUE, "-", "o", "to target"),
    "rewrite": ("NLA rewrite", BLUE, "-", "o", "to target"),
    "paraphrase_matched": ("NLA paraphrase (any change)", AQUA, (0, (5, 1.5, 1, 1.5)), "^", "changed"),
    "meandiff": ("Class-mean direction", ORANGE, (0, (3.5, 1.5)), "D", "to target"),
    "random": ("Random direction", MUTED, (0, (1, 1.2)), "s", "to target"),
}


def patch(dirs: list[tuple[str, Path]], conds: list[str], out: Path) -> None:
    fig, axes = plt.subplots(len(dirs), 2, sharex=True, sharey=True, squeeze=False,
                             figsize=(COL, 1.25 * len(dirs) + 0.75))
    for r, (row_label, d) in enumerate(dirs):
        M = json.loads((d / "patch.json").read_text())["measures"]
        matched = any(k.endswith("|matched") for k in M)
        sfx = "|matched" if matched and "meandiff" in conds else ""
        alphas = sorted({float(k.split("|")[1]) for k in M})
        for c, (split, col_title) in enumerate((("no_op", "Decisions to do nothing"),
                                                 ("action", "Decisions to act"))):
            ax = axes[r, c]
            for cond in conds:
                label, color, ls, marker, measure = DIRECTIONS[cond]
                pts = [(a, M.get(f"{cond}|{a}|{measure}|{split}{sfx}")) for a in alphas]
                pts = [(a, v) for a, v in pts if v]
                if not pts:
                    continue
                xs = [a for a, _ in pts]
                ax.fill_between(xs, [100 * v["lo"] for _, v in pts], [100 * v["hi"] for _, v in pts],
                                color=color, alpha=0.13, lw=0)
                ax.plot(xs, [100 * v["rate"] for _, v in pts], color=color, ls=ls, marker=marker,
                        markersize=3.2, markeredgecolor="white", markeredgewidth=0.3,
                        label=label if (r == 0 and c == 0) else None)
            ax.set_xscale("log", base=2)
            ax.set_xticks(alphas)
            ax.set_xticklabels([f"{a:g}×" for a in alphas])
            ax.minorticks_off()
            ax.set_ylim(-4, 104)
            ax.set_yticks([0, 50, 100])
            ax.grid(True)
            ax.set_axisbelow(True)
            clean(ax)
            if r == 0:
                ax.set_title(col_title, pad=3)
            if c == 1:
                ax.text(1.04, 0.5, row_label, transform=ax.transAxes, rotation=270, va="center",
                        ha="left", fontsize=7.5)
    fig.supylabel("Choice moves to the edited option (%)", fontsize=8, x=0.0)
    fig.supxlabel("Patch strength α (multiples of the edit's own size)", fontsize=8, y=0.0)
    fig.legend(loc="lower center", bbox_to_anchor=(0.5, 1.0), ncol=len(conds) if len(conds) <= 3 else 2,
               borderaxespad=0.0, columnspacing=0.9, handlelength=2.2)
    fig.tight_layout(pad=0.3, h_pad=0.6, w_pad=0.5)
    save(fig, out)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("-o", "--out", type=Path, default=Path("figures/paper"))
    ap.add_argument("--only", nargs="+", default=["models", "reasoning", "battery", "patch"],
                    choices=["models", "reasoning", "battery", "patch"])
    ap.add_argument("--table", type=Path, default=Path("results-local/csf/final_table.json"))
    ap.add_argument("--reference", action="append", default=None, metavar="NAME=VALUE",
                    help="reference line (repeatable); default PLA and Thallium as shipped")
    ap.add_argument("--battery", type=Path,
                    default=Path("results-local/csf/interp-gemma27b-final/battery.json"))
    ap.add_argument("--shuffled", type=Path,
                    default=Path("results-local/csf/interp-gemma27b-final/shuffled_by_conclusion.json"))
    ap.add_argument("--patch-with", type=Path, default=Path("results-local/nla/nla-gemma27b-final/patch"))
    ap.add_argument("--patch-without", type=Path,
                    default=Path("results-local/nla/nla-gemma27b-final-direct/patch"))
    ap.add_argument("--patch-conds", nargs="+", default=["nla", "meandiff", "random"],
                    choices=list(DIRECTIONS))
    args = ap.parse_args()
    style()
    refs = [(n.strip(), float(v)) for n, _, v in
            (r.rpartition("=") for r in (args.reference or ["PLA=4089.09", "Thallium=4658.65"]))]
    if "models" in args.only:
        models(args.table, refs, args.out / "models")
    if "reasoning" in args.only:
        models(args.table, refs, args.out / "reasoning", panels=[("", PANELS[0][1])], width=COL)
    if "battery" in args.only:
        battery(args.battery, args.shuffled, args.out / "battery")
    if "patch" in args.only:
        patch([("With reasoning", args.patch_with), ("Without reasoning", args.patch_without)],
              args.patch_conds, args.out / "patch")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
