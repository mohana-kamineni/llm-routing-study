"""
Thesis Figures Generation Script
================================
Generates publication-quality figures for the LLM routing empirical study:
- Figure 1: Cost vs. Pass Rate Pareto Frontier (Sweep, Baselines, Uncertainty Bands, Oracle)
- Figure 2: Category-by-Category Model Performance Comparison with 95% Wilson CIs & Significance
- Figure 3: Four-Cell Paired Contingency Matrix and Domain Breakdown

Figures are saved to `figures/` and copied to the brain artifact directory for thesis embedding.
"""

import json
import shutil
from pathlib import Path
import matplotlib.pyplot as plt
import matplotlib.ticker as ticker
import numpy as np

# Paths
PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_PATH = PROJECT_ROOT / "data" / "phase4_statistical_results.json"
FIG_DIR = PROJECT_ROOT / "figures"
BRAIN_DIR = Path(r"C:\Users\mohan\.gemini\antigravity\brain\218793b8-4ecd-44eb-a117-fb69482b430f")

FIG_DIR.mkdir(parents=True, exist_ok=True)
if BRAIN_DIR.parent.exists():
    BRAIN_DIR.mkdir(parents=True, exist_ok=True)

# Set high-quality styling
plt.rcParams.update({
    "font.family": "serif",
    "font.size": 11,
    "axes.titlesize": 13,
    "axes.labelsize": 12,
    "xtick.labelsize": 10,
    "ytick.labelsize": 10,
    "legend.fontsize": 10,
    "figure.titlesize": 14,
    "figure.dpi": 300,
    "savefig.dpi": 300,
    "axes.grid": True,
    "grid.alpha": 0.4,
    "grid.linestyle": "--"
})

def load_data():
    with open(DATA_PATH, "r", encoding="utf-8") as f:
        return json.load(f)

# ==============================================================================
# FIGURE 1: Pareto Frontier (Cost vs. Pass Rate)
# ==============================================================================
def plot_figure_1_pareto(data):
    fig, ax = plt.subplots(figsize=(9, 6.5))
    
    # Extract threshold sweep
    sweep = data["threshold_sweep"]
    thetas = [r["theta"] for r in sweep]
    costs = [r["total_cost"] for r in sweep]
    pass_rates = [r["pass_rate"] * 100 for r in sweep]
    
    # Extract bootstrap intervals for sweep if available
    boot = data["bootstrap_pareto"]
    boot_thetas = [float(k) for k in boot.keys()]
    boot_pass_mean = [boot[k]["pass_rate_mean"] * 100 for k in boot.keys()]
    boot_pass_low = [boot[k]["pass_rate_ci_95"][0] * 100 for k in boot.keys()]
    boot_pass_high = [boot[k]["pass_rate_ci_95"][1] * 100 for k in boot.keys()]
    boot_cost_mean = [boot[k]["cost_mean"] for k in boot.keys()]
    
    # Plot bootstrap confidence band
    ax.fill_betweenx(
        y=pass_rates,
        x1=[boot[f"{t:.1f}"]["cost_ci_95"][0] if f"{t:.1f}" in boot else c*0.95 for t, c in zip(thetas, costs)],
        x2=[boot[f"{t:.1f}"]["cost_ci_95"][1] if f"{t:.1f}" in boot else c*1.05 for t, c in zip(thetas, costs)],
        color="#2b5c8f", alpha=0.12, label="Heuristic Router 95% Bootstrap Region"
    )
    
    # Plot heuristic curve
    ax.plot(costs, pass_rates, color="#1f4e79", lw=2.4, marker="o", markersize=4.5, 
            label=r"Heuristic Router ($\theta \in [0.0, 1.0]$ sweep)", zorder=3)
    
    # Annotate key thetas along curve
    key_thetas = [0.0, 0.20, 0.35, 0.45, 0.50, 0.65, 1.0]
    for r in sweep:
        t = r["theta"]
        if t in key_thetas:
            c = r["total_cost"]
            p = r["pass_rate"] * 100
            offset = (8, -6)
            if t == 0.0:
                offset = (-55, -12)
            elif t == 0.45:
                offset = (-65, -14)
            elif t == 0.50:
                offset = (8, 4)
            elif t == 1.0:
                offset = (8, -10)
            elif t == 0.35:
                offset = (-45, 8)
            ax.annotate(f"$\\theta={t:.2f}$", (c, p), textcoords="offset points", 
                        xytext=offset, fontsize=9, fontweight="bold",
                        color="#123456",
                        arrowprops=dict(arrowstyle="->", color="#123456", lw=0.8, alpha=0.7))

    # Baselines
    bl = data["baselines"]
    
    # Always-120B
    c_120 = bl["Always_120B"]["cost"]
    p_120 = bl["Always_120B"]["pass_rate"] * 100
    ci_120 = [x * 100 for x in bl["Always_120B"]["pass_ci"]]
    ax.errorbar(c_120, p_120, yerr=[[p_120 - ci_120[0]], [ci_120[1] - p_120]],
                fmt="s", color="#7030a0", markersize=8, capsize=4, elinewidth=1.5,
                label="Always-120B Baseline (75.8%, $0.267)", zorder=4)

    # Always-20B
    c_20 = bl["Always_20B"]["cost"]
    p_20 = bl["Always_20B"]["pass_rate"] * 100
    ci_20 = [x * 100 for x in bl["Always_20B"]["pass_ci"]]
    ax.errorbar(c_20, p_20, yerr=[[p_20 - ci_20[0]], [ci_20[1] - p_20]],
                fmt="^", color="#c00000", markersize=8, capsize=4, elinewidth=1.5,
                label="Always-20B Baseline (66.0%, $0.185)", zorder=4)

    # Random 50/50 Baseline
    rnd = bl["Random_50_50"]
    c_rnd = rnd["cost"]
    p_rnd = rnd["pass_rate_expected"] * 100
    alg_ci = [x * 100 for x in rnd["ci_algorithmic_randomization_95"]["pass_rate_ci"]]
    boot_ci = [x * 100 for x in rnd["ci_prompt_bootstrap_95"]["pass_rate_ci"]]
    
    # Plot prompt bootstrap CI (outer cap)
    ax.errorbar(c_rnd, p_rnd, yerr=[[p_rnd - boot_ci[0]], [boot_ci[1] - p_rnd]],
                fmt="D", color="#385723", markersize=7, capsize=6, elinewidth=1.2,
                label="Random 50/50: Prompt Bootstrap 95% CI [67.6%, 74.6%]", zorder=4)
    # Plot algorithmic CI (inner heavy cap)
    ax.errorbar(c_rnd, p_rnd, yerr=[[p_rnd - alg_ci[0]], [alg_ci[1] - p_rnd]],
                fmt="none", ecolor="#70ad47", elinewidth=2.8, capsize=3,
                label="Random 50/50: Algorithmic Randomization 95% CI [69.0%, 72.8%]", zorder=5)

    # Oracle Benchmark
    orc = bl["Oracle"]
    c_orc = orc["cost"]
    p_orc = orc["pass_rate"] * 100
    ci_orc = [x * 100 for x in orc["pass_ci"]]
    ax.errorbar(c_orc, p_orc, yerr=[[p_orc - ci_orc[0]], [ci_orc[1] - p_orc]],
                fmt="*", color="#ffc000", markeredgecolor="#b28900", markersize=13, capsize=4, elinewidth=1.5,
                label="Oracle Ceiling (Hindsight Upper Bound: 80.6%, $0.178)", zorder=6)
    
    # Horizontal guideline for Oracle
    ax.axhline(p_orc, color="#ffc000", linestyle=":", lw=1.2, alpha=0.7)
    
    # Inversion Annotation at theta=0.45
    r45 = [r for r in sweep if r["theta"] == 0.45][0]
    ax.annotate(
        "Heuristic Inversion Deficit:\nLower Quality & Higher Cost\nthan Random 50/50 Baseline",
        xy=(r45["total_cost"], r45["pass_rate"] * 100),
        xytext=(0.200, 72.5),
        arrowprops=dict(facecolor="#d9534f", edgecolor="#d9534f", shrink=0.08, width=1.5, headwidth=6),
        bbox=dict(boxstyle="round,pad=0.4", facecolor="#fff2f2", edgecolor="#d9534f", lw=1.2),
        fontsize=9, color="#900"
    )

    ax.set_title("Figure 1: Cost vs. Pass Rate Pareto Frontier across Routing Policies", pad=12, fontweight="bold")
    ax.set_xlabel("Published Candidate Token Cost (USD for 500 Prompts)")
    ax.set_ylabel("Empirical Benchmark PASS Rate (%)")
    ax.set_xlim(0.170, 0.278)
    ax.set_ylim(63.0, 84.0)
    ax.xaxis.set_major_formatter(ticker.FormatStrFormatter("$%.3f"))
    ax.yaxis.set_major_formatter(ticker.FormatStrFormatter("%.1f%%"))
    
    ax.legend(loc="lower right", framealpha=0.95, facecolor="#ffffff", edgecolor="#cccccc", fontsize=8.5)
    
    plt.tight_layout()
    fig1_path = FIG_DIR / "figure1_pareto_frontier.png"
    plt.savefig(fig1_path, dpi=300)
    plt.close()
    print(f"Saved: {fig1_path}")
    
    # Copy to brain artifact directory if present
    if BRAIN_DIR.exists():
        shutil.copy(fig1_path, BRAIN_DIR / "figure1_pareto_frontier.png")

# ==============================================================================
# FIGURE 2: Category Performance Comparison
# ==============================================================================
def plot_figure_2_categories(data):
    fig, ax = plt.subplots(figsize=(9, 5.5))
    
    categories = ["creative", "factual_qa", "reasoning_math", "summarization"]
    labels = ["Creative\n(Constrained)", "Factual QA\n(Ground Truth)", "Reasoning / Math\n(Verified Steps)", "Summarization\n(125 Tasks)"]
    
    p_20b = []
    err_20b_low = []
    err_20b_high = []
    
    p_120b = []
    err_120b_low = []
    err_120b_high = []
    
    p_values = []
    deltas = []
    
    for cat in categories:
        info = data["category_analyses"][cat]
        p20 = info["p_20b"] * 100
        p120 = info["p_120b"] * 100
        ci20 = [x * 100 for x in info["ci_20b"]]
        ci120 = [x * 100 for x in info["ci_120b"]]
        
        p_20b.append(p20)
        err_20b_low.append(p20 - ci20[0])
        err_20b_high.append(ci20[1] - p20)
        
        p_120b.append(p120)
        err_120b_low.append(p120 - ci120[0])
        err_120b_high.append(ci120[1] - p120)
        
        p_values.append(info["mcnemar"]["p_value_exact"])
        deltas.append(p120 - p20)

    # Add Study-Wide
    sw = data["study_wide"]
    labels.append("Study-Wide\n(N=500 Total)")
    p20_sw = sw["p_20b"] * 100
    p120_sw = sw["p_120b"] * 100
    ci20_sw = [x * 100 for x in sw["ci_20b"]]
    ci120_sw = [x * 100 for x in sw["ci_120b"]]
    
    p_20b.append(p20_sw)
    err_20b_low.append(p20_sw - ci20_sw[0])
    err_20b_high.append(ci20_sw[1] - p20_sw)
    
    p_120b.append(p120_sw)
    err_120b_low.append(p120_sw - ci120_sw[0])
    err_120b_high.append(ci120_sw[1] - p120_sw)
    p_values.append(sw["mcnemar"]["p_value_exact"])
    deltas.append(p120_sw - p20_sw)

    x = np.arange(len(labels))
    width = 0.35
    
    rects1 = ax.bar(x - width/2, p_20b, width, yerr=[err_20b_low, err_20b_high],
                    label="openai/gpt-oss-20b (Small)", color="#4682b4", edgecolor="#2b5c8f",
                    capsize=4, error_kw=dict(lw=1.2, capthick=1.2))
    rects2 = ax.bar(x + width/2, p_120b, width, yerr=[err_120b_low, err_120b_high],
                    label="openai/gpt-oss-120b (Large)", color="#2e4057", edgecolor="#1a2533",
                    capsize=4, error_kw=dict(lw=1.2, capthick=1.2))

    # Add values on bars
    for i in range(len(labels)):
        ax.text(x[i] - width/2, p_20b[i] / 2, f"{p_20b[i]:.1f}%", ha="center", va="center", color="white", fontweight="bold", fontsize=9)
        ax.text(x[i] + width/2, p_120b[i] / 2, f"{p_120b[i]:.1f}%", ha="center", va="center", color="white", fontweight="bold", fontsize=9)
        
        # Delta & significance annotation above bars
        top_y = max(p_20b[i] + err_20b_high[i], p_120b[i] + err_120b_high[i])
        sig = "n.s."
        p_val = p_values[i]
        if p_val < 0.001:
            sig = "*** (p<0.001)"
        elif p_val < 0.01:
            sig = "** (p<0.01)"
        elif p_val < 0.05:
            sig = "* (p<0.05)"
            
        ax.text(x[i], top_y + 3.0, f"Δ = +{deltas[i]:.1f}%\n{sig}", ha="center", va="bottom", fontsize=8.5, fontweight="bold",
                color="#b22222" if p_val < 0.05 else "#555555")

    # Visual separator for study-wide
    ax.axvline(3.5, color="#888888", linestyle="--", lw=1.0, alpha=0.7)

    ax.set_title("Figure 2: Empirical PASS Rate by Task Domain with 95% Wilson CIs", pad=12, fontweight="bold")
    ax.set_ylabel("PASS Rate (%)")
    ax.set_xticks(x)
    ax.set_xticklabels(labels)
    ax.set_ylim(0, 100)
    ax.yaxis.set_major_formatter(ticker.FormatStrFormatter("%.0f%%"))
    ax.legend(loc="upper left", framealpha=0.95, facecolor="#ffffff", edgecolor="#cccccc")

    plt.tight_layout()
    fig2_path = FIG_DIR / "figure2_category_performance.png"
    plt.savefig(fig2_path, dpi=300)
    plt.close()
    print(f"Saved: {fig2_path}")
    if BRAIN_DIR.exists():
        shutil.copy(fig2_path, BRAIN_DIR / "figure2_category_performance.png")

# ==============================================================================
# FIGURE 3: Four-Cell Paired Contingency & Domain Breakdown
# ==============================================================================
def plot_figure_3_contingency(data):
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12, 5.5), gridspec_kw={"width_ratios": [1, 1.3]})
    
    # Left: 2x2 Confusion / Paired Matrix (Study-wide)
    sw_cells = data["study_wide"]["cells"]
    matrix = np.array([
        [sw_cells["Cell_A_PASS_PASS"], sw_cells["Cell_C_PASS_FAIL"]],
        [sw_cells["Cell_B_FAIL_PASS"], sw_cells["Cell_D_FAIL_FAIL"]]
    ])
    
    im = ax1.imshow(matrix, cmap="Blues", vmin=0, vmax=350)
    
    # Annotations in cells
    cell_names = [
        ["Cell A: 306 (61.2%)\nPASS / PASS\n[Small Sufficient]", "Cell C: 24 (4.8%)\nPASS / FAIL\n[Small Inversion]"],
        ["Cell B: 73 (14.6%)\nFAIL / PASS\n[Large Advantage]", "Cell D: 97 (19.4%)\nFAIL / FAIL\n[Unresolved by Either]"]
    ]
    
    for r in range(2):
        for c in range(2):
            val = matrix[r, c]
            color = "white" if val > 150 else "black"
            ax1.text(c, r, cell_names[r][c], ha="center", va="center", color=color,
                     fontweight="bold", fontsize=9.5)
            
    ax1.set_xticks([0, 1])
    ax1.set_yticks([0, 1])
    ax1.set_xticklabels(["120B PASS", "120B FAIL"], fontweight="bold")
    ax1.set_yticklabels(["20B PASS", "20B FAIL"], fontweight="bold")
    ax1.set_title("(A) Study-Wide Paired Matrix (N=500)", pad=10, fontweight="bold")
    
    # Annotate discordance ratio below ax1
    ax1.text(0.5, -0.22, "Resolvable (A+B+C) = 403 (80.6%)\nDiscordant Ratio B/C = 73 / 24 = 3.042 (p = 6.40e-7)",
             transform=ax1.transAxes, ha="center", va="top", fontsize=9,
             bbox=dict(boxstyle="round,pad=0.4", facecolor="#f8f9fa", edgecolor="#dddddd"))

    # Right: Domain-by-Domain Cell Proportions (Stacked Bar)
    cats = ["creative", "factual_qa", "reasoning_math", "summarization"]
    cat_names = ["Creative", "Factual QA", "Reasoning / Math", "Summarization"]
    
    cell_A_counts = [data["category_analyses"][c]["cells"]["Cell_A_PASS_PASS"] for c in cats]
    cell_B_counts = [data["category_analyses"][c]["cells"]["Cell_B_FAIL_PASS"] for c in cats]
    cell_C_counts = [data["category_analyses"][c]["cells"]["Cell_C_PASS_FAIL"] for c in cats]
    cell_D_counts = [data["category_analyses"][c]["cells"]["Cell_D_FAIL_FAIL"] for c in cats]
    
    y = np.arange(len(cat_names))
    height = 0.55
    
    pA = ax2.barh(y, cell_A_counts, height, label="Cell A (PASS/PASS, 20B Sufficient)", color="#2ca02c")
    pB = ax2.barh(y, cell_B_counts, height, left=cell_A_counts, label="Cell B (FAIL/PASS, 120B Wins)", color="#1f77b4")
    pC = ax2.barh(y, cell_C_counts, height, left=np.array(cell_A_counts) + np.array(cell_B_counts), label="Cell C (PASS/FAIL, 20B Wins)", color="#ff7f0e")
    pD = ax2.barh(y, cell_D_counts, height, left=np.array(cell_A_counts) + np.array(cell_B_counts) + np.array(cell_C_counts), label="Cell D (FAIL/FAIL, Unresolved)", color="#7f7f7f")
    
    # Add count text in bars
    for i in range(len(cat_names)):
        # Cell A
        if cell_A_counts[i] > 10:
            ax2.text(cell_A_counts[i] / 2, y[i], f"{cell_A_counts[i]}", ha="center", va="center", color="white", fontweight="bold", fontsize=9)
        # Cell B
        if cell_B_counts[i] > 8:
            ax2.text(cell_A_counts[i] + cell_B_counts[i] / 2, y[i], f"{cell_B_counts[i]}", ha="center", va="center", color="white", fontweight="bold", fontsize=9)
        # Cell C
        if cell_C_counts[i] >= 5:
            ax2.text(cell_A_counts[i] + cell_B_counts[i] + cell_C_counts[i] / 2, y[i], f"{cell_C_counts[i]}", ha="center", va="center", color="white", fontweight="bold", fontsize=8.5)
        # Cell D
        if cell_D_counts[i] > 10:
            ax2.text(cell_A_counts[i] + cell_B_counts[i] + cell_C_counts[i] + cell_D_counts[i] / 2, y[i], f"{cell_D_counts[i]}", ha="center", va="center", color="white", fontweight="bold", fontsize=9)

    ax2.set_yticks(y)
    ax2.set_yticklabels(cat_names, fontweight="bold")
    ax2.set_xlabel("Number of Prompts (125 Per Domain)")
    ax2.set_xlim(0, 125)
    ax2.set_title("(B) Four-Cell Distribution by Task Domain", pad=10, fontweight="bold")
    ax2.legend(loc="lower center", bbox_to_anchor=(0.5, -0.32), ncol=2, framealpha=0.95, facecolor="#ffffff", edgecolor="#cccccc", fontsize=8.5)

    plt.tight_layout()
    fig3_path = FIG_DIR / "figure3_contingency_and_domains.png"
    plt.savefig(fig3_path, dpi=300)
    plt.close()
    print(f"Saved: {fig3_path}")
    if BRAIN_DIR.exists():
        shutil.copy(fig3_path, BRAIN_DIR / "figure3_contingency_and_domains.png")

if __name__ == "__main__":
    d = load_data()
    plot_figure_1_pareto(d)
    plot_figure_2_categories(d)
    plot_figure_3_contingency(d)
    print("All 3 figures successfully generated and copied to artifact directory!")
