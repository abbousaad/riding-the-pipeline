"""Publication-size distributions from the frozen historical reanalysis."""

import os
from pathlib import Path
import json

os.environ.setdefault("MPLCONFIGDIR", "/tmp/riding-pipeline-matplotlib")
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

HERE = Path(__file__).resolve().parent
OUT = HERE / "results" / "historical_reanalysis"


def main():
    report = json.loads((OUT / "analysis.json").read_text())
    plt.rcParams.update({"font.size": 8.5, "font.family": "DejaVu Sans", "svg.fonttype": "none",
                         "axes.spines.top": False, "axes.spines.right": False})
    fig, axes = plt.subplots(1, 3, figsize=(7.2, 4.1), sharey=True)
    colors = {"routine": "#69737c", "attack": "#b8323c", "benign_override": "#17669d",
              "benign_target": "#17669d", "targetless": "#27805e"}
    rng = np.random.default_rng(20260924)
    for ax, phase, label in zip(axes, ("test", "build", "deploy"), ("Test", "Build", "Deploy")):
        groups = [("routine", "Routine\n(n=30)", report["baseline"][phase]["scores"]),
                  ("attack", "Attack\n(n=12)", report["arms"]["attack"][phase]["scores"])]
        benign_arm = "benign_override" if phase == "test" else "benign_target"
        if phase != "build":
            groups.extend([(benign_arm, "Benign\nanomaly\n(n=12)", report["arms"][benign_arm][phase]["scores"]),
                           ("targetless", "Verdict\nprobe\n(n=12)", report["arms"]["targetless"][phase]["scores"])])
        for x, (arm, _, values) in enumerate(groups):
            ax.scatter(x + rng.uniform(-0.13, 0.13, len(values)), values, s=17,
                       color=colors[arm], alpha=0.82, edgecolors="white", linewidths=0.35, zorder=3)
            ax.plot([x - 0.22, x + 0.22], [np.mean(values)] * 2, color=colors[arm], linewidth=1.8, zorder=4)
        threshold = report["baseline"][phase]["threshold"]
        ax.axhline(threshold, color="#333333", linewidth=0.85, linestyle="--", zorder=2)
        ax.set_xticks(range(len(groups)), [g[1] for g in groups])
        ax.set_xlim(-0.5, len(groups) - 0.5)
        ax.set_ylim(0, 0.53)
        ax.set_title(label, fontweight="bold", pad=34)
        ax.grid(axis="y", color="#e4e7eb", linewidth=0.6, zorder=0)
        if phase != "build":
            auc = report["direct_attack_vs_benign"][phase]["auc_attack_vs_benign_anomaly"]
            ax.text(0.5, 1.015, f"Attack vs benign anomaly\nAUC = {auc:.3f}",
                    transform=ax.transAxes, ha="center", fontsize=8)
        else:
            ax.text(0.5, 1.015, "Intermediate-phase\ncomparison", transform=ax.transAxes, ha="center", fontsize=8)
    axes[0].set_ylabel("Explanation cosine distance to routine reference")
    fig.subplots_adjust(left=0.09, right=0.975, bottom=0.29, top=0.78, wspace=0.20)
    fig.text(0.09, 0.12, "Dots: observations. Bars: means. Dashed: routine 95th-percentile calibration thresholds.", fontsize=8)
    fig.text(0.09, 0.075, "Routine scores use leave-one-out centroids; other scores use the full routine centroid.", fontsize=8, color="#454545")
    fig.text(0.09, 0.03, "Historical prompts. Verdict probe: targetless payload. Not v2 execution results.", fontsize=8, color="#454545")
    for suffix in ("svg", "png"):
        fig.savefig(OUT / f"figure3_revised.{suffix}", dpi=300, facecolor="white")
    plt.close(fig)
    print("Saved figure3_revised.svg and figure3_revised.png (300 dpi).")


if __name__ == "__main__":
    main()
