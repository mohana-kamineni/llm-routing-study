"""
Phase 4 Statistical Analysis & Routing Evaluation Suite
======================================================
Comprehensive pre-registered confirmatory and exploratory analysis:
1. 2x2 Paired Matrix & Four-Cell Classification (study-wide and per category)
2. Paired McNemar's exact tests & Fisher's exact tests with BH-FDR correction
3. Router Threshold Sweep (theta in [0.0, 1.0] in 0.05 increments; 21 thresholds)
   - Resolvable Task Pass Rate: routed-model PASS count among A+B+C, divided by 403
   - Oracle Cost-Target Agreement: prompts where router selected cost-minimal passing model, divided by 403
4. Baseline Comparisons:
   - Always-120B (theta = 0.0)
   - Always-20B (theta = 1.0)
   - Random 50/50 (with exact algorithmic randomization interval and prompt-bootstrap interval)
   - Oracle (hindsight-only, non-deployable theoretical upper bound)
5. 1,000-iteration Non-Parametric Bootstrap Pareto Frontier Analysis (paired within each replicate)
6. Summarization Split Sensitivity Analysis (50 Independent vs 75 Assisted)

All outputs are saved to data/phase4_statistical_results.json and formatted reports.
"""

import json
import math
from pathlib import Path
from collections import Counter, defaultdict
import numpy as np
from scipy.stats import binom, binomtest, fisher_exact

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"
EVALS_DIR = DATA_DIR / "evaluations"
RESPONSES_DIR = DATA_DIR / "responses"

# Published rates per 1M tokens
RATES = {
    "openai_gpt-oss-20b": {"prompt": 0.075 / 1e6, "completion": 0.300 / 1e6},
    "openai_gpt-oss-120b": {"prompt": 0.150 / 1e6, "completion": 0.600 / 1e6}
}

def wilson_score_ci(k: int, n: int, confidence: float = 0.95):
    """Computes Wilson score confidence interval for a binomial proportion."""
    if n == 0:
        return (0.0, 0.0)
    z = 1.959963984540054  # 95% confidence z-score
    p = k / n
    denominator = 1 + z**2 / n
    centre_adjusted_probability = p + z**2 / (2 * n)
    adjusted_sd = math.sqrt((p * (1 - p) + z**2 / (4 * n)) / n)
    lower_bound = (centre_adjusted_probability - z * adjusted_sd) / denominator
    upper_bound = (centre_adjusted_probability + z * adjusted_sd) / denominator
    return (max(0.0, lower_bound), min(1.0, upper_bound))

def compute_token_cost(prompt_tokens: int, completion_tokens: int, model_slug: str) -> float:
    rates = RATES[model_slug]
    return prompt_tokens * rates["prompt"] + completion_tokens * rates["completion"]

def benjamini_hochberg(p_values: list):
    """Computes Benjamini-Hochberg FDR-adjusted q-values for a list of p-values."""
    n = len(p_values)
    if n == 0:
        return []
    sorted_indices = np.argsort(p_values)
    sorted_p = np.array(p_values)[sorted_indices]
    q_values = np.zeros(n)
    q_values[-1] = sorted_p[-1]
    for i in range(n - 2, -1, -1):
        q = min(1.0, sorted_p[i] * n / (i + 1))
        q_values[i] = min(q, q_values[i + 1])
    orig_q = np.zeros(n)
    orig_q[sorted_indices] = q_values
    return orig_q.tolist()

def load_data():
    """Loads and joins prompts, responses, references, and evaluations for all 500 prompts."""
    with open(DATA_DIR / "prompts.json", "r", encoding="utf-8") as f:
        prompts = json.load(f)["prompts"]
        
    with open(DATA_DIR / "references.json", "r", encoding="utf-8") as f:
        references = {r["prompt_id"]: r for r in json.load(f)["references"]}
        
    dataset = []
    for p in prompts:
        pid = p["prompt_id"]
        cat = p["category"]
        score = p["heuristic_scores"]["difficulty_score"]
        ref = references[pid]
        
        # Load 20B evaluation & response
        eval_20b_path = EVALS_DIR / f"{pid}_openai_gpt-oss-20b_eval.json"
        with open(eval_20b_path, "r", encoding="utf-8") as f:
            eval_20b = json.load(f)
            
        resp_20b_path = RESPONSES_DIR / f"{pid}_openai_gpt-oss-20b.json"
        with open(resp_20b_path, "r", encoding="utf-8") as f:
            resp_20b = json.load(f)
            
        # Load 120B evaluation & response
        eval_120b_path = EVALS_DIR / f"{pid}_openai_gpt-oss-120b_eval.json"
        with open(eval_120b_path, "r", encoding="utf-8") as f:
            eval_120b = json.load(f)
            
        resp_120b_path = RESPONSES_DIR / f"{pid}_openai_gpt-oss-120b.json"
        with open(resp_120b_path, "r", encoding="utf-8") as f:
            resp_120b = json.load(f)
            
        # Token metrics
        pt_20b = resp_20b.get("prompt_tokens", 0)
        ct_20b = resp_20b.get("completion_tokens", 0)
        cost_20b = compute_token_cost(pt_20b, ct_20b, "openai_gpt-oss-20b")
        
        pt_120b = resp_120b.get("prompt_tokens", 0)
        ct_120b = resp_120b.get("completion_tokens", 0)
        cost_120b = compute_token_cost(pt_120b, ct_120b, "openai_gpt-oss-120b")
        
        # Verdicts
        v_20b = eval_20b["verdict"]
        v_120b = eval_120b["verdict"]
        
        # 4-Cell classification
        # Cell A: 20B PASS, 120B PASS (Both succeed; small saves cost)
        # Cell B: 20B FAIL, 120B PASS (Large model superiority)
        # Cell C: 20B PASS, 120B FAIL (Small model inversion)
        # Cell D: 20B FAIL, 120B FAIL (Both fail; unresolvable)
        if v_20b == "PASS" and v_120b == "PASS":
            cell = "Cell_A"
            semantic_cell = "PASS_PASS"
        elif v_20b == "FAIL" and v_120b == "PASS":
            cell = "Cell_B"
            semantic_cell = "FAIL_PASS"
        elif v_20b == "PASS" and v_120b == "FAIL":
            cell = "Cell_C"
            semantic_cell = "PASS_FAIL"
        else:
            cell = "Cell_D"
            semantic_cell = "FAIL_FAIL"
            
        dataset.append({
            "prompt_id": pid,
            "category": cat,
            "difficulty_score": score,
            "word_count": p.get("word_count", len(p["prompt_text"].split())),
            "reference_type": ref.get("reference_type", ""),
            "is_assisted_summarization": len(ref.get("key_aspects", [])) > 0 if cat == "summarization" else False,
            "verdict_20b": v_20b,
            "verdict_120b": v_120b,
            "terminal_20b": eval_20b.get("terminal_type", None),
            "terminal_120b": eval_120b.get("terminal_type", None),
            "tokens_20b": {"prompt": pt_20b, "completion": ct_20b, "total": pt_20b + ct_20b},
            "tokens_120b": {"prompt": pt_120b, "completion": ct_120b, "total": pt_120b + ct_120b},
            "cost_20b": cost_20b,
            "cost_120b": cost_120b,
            "cell": cell,
            "semantic_cell": semantic_cell
        })
        
    return dataset

def run_paired_tests(items, label=""):
    """Runs McNemar exact test and contingency analysis for a set of prompt items."""
    n = len(items)
    n_20b_pass = sum(1 for x in items if x["verdict_20b"] == "PASS")
    n_120b_pass = sum(1 for x in items if x["verdict_120b"] == "PASS")
    
    a = sum(1 for x in items if x["verdict_20b"] == "PASS" and x["verdict_120b"] == "PASS")
    b = sum(1 for x in items if x["verdict_20b"] == "FAIL" and x["verdict_120b"] == "PASS")
    c = sum(1 for x in items if x["verdict_20b"] == "PASS" and x["verdict_120b"] == "FAIL")
    d = sum(1 for x in items if x["verdict_20b"] == "FAIL" and x["verdict_120b"] == "FAIL")
    
    discordant = b + c
    if discordant == 0:
        mcnemar_stat = 0.0
        mcnemar_p = 1.0
        odds_ratio = 1.0
    else:
        mcnemar_stat = (abs(b - c) - 1.0)**2 / (b + c)
        res = binomtest(min(b, c), b + c, p=0.5, alternative="two-sided")
        mcnemar_p = res.pvalue
        odds_ratio = b / c if c > 0 else float("inf")
        
    table_marginals = [[n_20b_pass, n - n_20b_pass], [n_120b_pass, n - n_120b_pass]]
    fisher_odds, fisher_p = fisher_exact(table_marginals)
    
    p_20b = n_20b_pass / n
    p_120b = n_120b_pass / n
    ci_20b = wilson_score_ci(n_20b_pass, n)
    ci_120b = wilson_score_ci(n_120b_pass, n)
    
    return {
        "label": label,
        "n": n,
        "n_20b_pass": n_20b_pass,
        "p_20b": p_20b,
        "ci_20b": ci_20b,
        "n_120b_pass": n_120b_pass,
        "p_120b": p_120b,
        "ci_120b": ci_120b,
        "delta_pass_rate": p_120b - p_20b,
        "cells": {
            "Cell_A_PASS_PASS": a,
            "Cell_B_FAIL_PASS": b,
            "Cell_C_PASS_FAIL": c,
            "Cell_D_FAIL_FAIL": d
        },
        "mcnemar": {
            "discordant_total": discordant,
            "b_120b_superior": b,
            "c_20b_inversion": c,
            "chi2_stat": mcnemar_stat,
            "p_value_exact": mcnemar_p,
            "odds_ratio": odds_ratio
        },
        "fisher": {
            "p_value": fisher_p,
            "odds_ratio": fisher_odds
        }
    }

def run_threshold_sweep(dataset, thresholds=None):
    """Sweeps routing threshold theta in [0.0, 1.0] and computes routing performance."""
    if thresholds is None:
        thresholds = [round(x, 2) for x in np.linspace(0.0, 1.0, 21)]
        
    n = len(dataset)
    resolvable_items = [x for x in dataset if x["cell"] in ["Cell_A", "Cell_B", "Cell_C"]]
    n_resolvable = len(resolvable_items)
    
    sweep_results = []
    for theta in thresholds:
        routed_pass = 0
        routed_cost = 0.0
        routed_to_20b = 0
        routed_to_120b = 0
        
        cat_pass = defaultdict(int)
        cat_total = defaultdict(int)
        
        correct_decision_resolvable = 0
        correct_decision_all = 0
        
        for item in dataset:
            cat = item["category"]
            cat_total[cat] += 1
            s = item["difficulty_score"]
            cell = item["cell"]
            
            # Routing decision: Small (20B) if s <= theta else Large (120B)
            if s <= theta:
                routed_to_20b += 1
                verdict = item["verdict_20b"]
                cost = item["cost_20b"]
                decision = "20B"
            else:
                routed_to_120b += 1
                verdict = item["verdict_120b"]
                cost = item["cost_120b"]
                decision = "120B"
                
            if verdict == "PASS":
                routed_pass += 1
                cat_pass[cat] += 1
            routed_cost += cost
            
            # Oracle decision target:
            # Cell A (both pass): optimal is 20B (quality satisfied, token cost minimized)
            # Cell B (20B fail, 120B pass): optimal is 120B (large model required for pass)
            # Cell C (20B pass, 120B fail): optimal is 20B (pass satisfied & cost minimized)
            # Cell D (both fail): optimal is 20B (loss minimization: cheaper failure)
            if cell == "Cell_A":
                target_optimal = "20B"
            elif cell == "Cell_B":
                target_optimal = "120B"
            elif cell == "Cell_C":
                target_optimal = "20B"
            else:
                target_optimal = "20B"
                
            if decision == target_optimal:
                correct_decision_all += 1
                if cell in ["Cell_A", "Cell_B", "Cell_C"]:
                    correct_decision_resolvable += 1
                    
        p_routed = routed_pass / n
        ci_routed = wilson_score_ci(routed_pass, n)
        
        # Disaggregated resolvable metrics:
        # 1. Resolvable Task Pass Rate: fraction of resolvable prompts where routed model produces a PASS
        pass_rate_resolvable = routed_pass / n_resolvable if n_resolvable > 0 else 0.0
        # 2. Oracle Cost-Target Agreement: fraction of resolvable prompts where router picked cost-minimal passing model
        oracle_cost_target_agreement = correct_decision_resolvable / n_resolvable if n_resolvable > 0 else 0.0
        acc_all = correct_decision_all / n
        
        sweep_results.append({
            "theta": theta,
            "routed_to_20b": routed_to_20b,
            "routed_to_120b": routed_to_120b,
            "pct_to_20b": routed_to_20b / n,
            "routed_pass": routed_pass,
            "pass_rate": p_routed,
            "pass_rate_ci": ci_routed,
            "total_cost": routed_cost,
            "resolvable_task_pass_rate": pass_rate_resolvable,
            "oracle_cost_target_agreement": oracle_cost_target_agreement,
            "routing_accuracy_resolvable": oracle_cost_target_agreement,  # backward compatibility alias
            "routing_accuracy_all": acc_all,
            "category_pass_rates": {cat: cat_pass[cat] / cat_total[cat] for cat in cat_total}
        })
        
    return sweep_results

def run_bootstrap_analysis(dataset, n_iterations=1000, seed=42):
    """
    Performs non-parametric bootstrap resampling (1,000 resamples) for Pareto confidence bands.
    Pairs cost savings within each bootstrap replicate relative to that replicate's 120B baseline cost.
    """
    rng = np.random.default_rng(seed)
    n = len(dataset)
    indices = np.arange(n)
    thresholds = [round(x, 2) for x in np.linspace(0.0, 1.0, 21)]
    
    boot_stats = {theta: {"pass_rates": [], "costs": [], "savings": []} for theta in thresholds}
    boot_random_prs = []
    
    for _ in range(n_iterations):
        sample_idx = rng.choice(indices, size=n, replace=True)
        sample = [dataset[i] for i in sample_idx]
        
        # Replicate-specific 120B baseline cost
        c120_sample_base = sum(x["cost_120b"] for x in sample)
        
        # Also track random 50/50 mixture pass rate for prompt-sampling uncertainty
        p20_s = sum(1 for x in sample if x["verdict_20b"] == "PASS") / n
        p120_s = sum(1 for x in sample if x["verdict_120b"] == "PASS") / n
        boot_random_prs.append(0.5 * p20_s + 0.5 * p120_s)
        
        for theta in thresholds:
            p_cnt = 0
            cost = 0.0
            for item in sample:
                if item["difficulty_score"] <= theta:
                    if item["verdict_20b"] == "PASS":
                        p_cnt += 1
                    cost += item["cost_20b"]
                else:
                    if item["verdict_120b"] == "PASS":
                        p_cnt += 1
                    cost += item["cost_120b"]
            boot_stats[theta]["pass_rates"].append(p_cnt / n)
            boot_stats[theta]["costs"].append(cost)
            
            # Paired savings relative to this replicate's 120B cost
            rep_savings = (c120_sample_base - cost) / c120_sample_base * 100.0 if c120_sample_base > 0 else 0.0
            boot_stats[theta]["savings"].append(rep_savings)
            
    summary = {}
    for theta in thresholds:
        prs = np.array(boot_stats[theta]["pass_rates"])
        costs = np.array(boot_stats[theta]["costs"])
        savings = np.array(boot_stats[theta]["savings"])
        
        summary[str(theta)] = {
            "pass_rate_mean": float(np.mean(prs)),
            "pass_rate_ci_95": [float(np.percentile(prs, 2.5)), float(np.percentile(prs, 97.5))],
            "cost_mean": float(np.mean(costs)),
            "cost_ci_95": [float(np.percentile(costs, 2.5)), float(np.percentile(costs, 97.5))],
            "savings_mean": float(np.mean(savings)),
            "savings_ci_95": [float(np.percentile(savings, 2.5)), float(np.percentile(savings, 97.5))]
        }
        
    random_prompt_ci = [float(np.percentile(boot_random_prs, 2.5)), float(np.percentile(boot_random_prs, 97.5))]
    return summary, random_prompt_ci

def main():
    print("=" * 80)
    print("PHASE 4 COMPREHENSIVE STATISTICAL ANALYSIS & ROUTING EVALUATION")
    print("=" * 80)
    
    dataset = load_data()
    n_total = len(dataset)
    print(f"Total matched evaluation records loaded: {n_total}")
    
    # -------------------------------------------------------------
    # 1. 2x2 Paired Matrix & Four-Cell Classification
    # -------------------------------------------------------------
    print("\n--- 1. Study-Wide Paired Matrix & Four-Cell Classification ---")
    overall_test = run_paired_tests(dataset, label="Study-Wide (N=500)")
    
    print(f"Overall 20B PASS:  {overall_test['n_20b_pass']}/500 ({overall_test['p_20b']*100:.1f}%) "
          f"[95% CI: {overall_test['ci_20b'][0]*100:.1f}% - {overall_test['ci_20b'][1]*100:.1f}%]")
    print(f"Overall 120B PASS: {overall_test['n_120b_pass']}/500 ({overall_test['p_120b']*100:.1f}%) "
          f"[95% CI: {overall_test['ci_120b'][0]*100:.1f}% - {overall_test['ci_120b'][1]*100:.1f}%]")
    print(f"Delta (120B - 20B): +{overall_test['delta_pass_rate']*100:.1f} percentage points")
    
    cells = overall_test["cells"]
    a = cells["Cell_A_PASS_PASS"]
    b = cells["Cell_B_FAIL_PASS"]
    c = cells["Cell_C_PASS_FAIL"]
    d_cell = cells["Cell_D_FAIL_FAIL"]
    
    print("\nFour-Cell Classification Table:")
    print(f"  Cell A (20B PASS, 120B PASS): {a} ({a/500*100:.1f}%) [Both succeed; small saves cost]")
    print(f"  Cell B (20B FAIL, 120B PASS): {b} ({b/500*100:.1f}%) [Large model superiority]")
    print(f"  Cell C (20B PASS, 120B FAIL): {c} ({c/500*100:.1f}%) [Small model inversion]")
    print(f"  Cell D (20B FAIL, 120B FAIL): {d_cell} ({d_cell/500*100:.1f}%) [Both fail; unresolvable]")
    
    n_resolvable = a + b + c
    print(f"\nResolvable Prompts (A + B + C): {n_resolvable}/500 ({n_resolvable/500*100:.1f}%)")
    print(f"Unresolvable Prompts (D):         {d_cell}/500 ({d_cell/500*100:.1f}%)")
    
    # -------------------------------------------------------------
    # 2. Category-by-Category Paired Tests & BH-FDR Correction
    # -------------------------------------------------------------
    print("\n--- 2. Category-by-Category Paired McNemar Tests ---")
    categories = ["factual_qa", "reasoning_math", "summarization", "creative"]
    cat_tests = {}
    p_values_mcnemar = []
    
    for cat in categories:
        cat_items = [x for x in dataset if x["category"] == cat]
        t = run_paired_tests(cat_items, label=cat)
        cat_tests[cat] = t
        p_values_mcnemar.append(t["mcnemar"]["p_value_exact"])
        
    q_values_mcnemar = benjamini_hochberg(p_values_mcnemar)
    
    print(f"{'Category':<16} | {'20B PASS':<10} | {'120B PASS':<10} | {'Delta':<7} | {'Cell A':<6} | {'Cell B':<6} | {'Cell C':<6} | {'Cell D':<6} | {'McNemar p':<11} | {'FDR q':<11}")
    print("-" * 105)
    for i, cat in enumerate(categories):
        t = cat_tests[cat]
        cell_dict = t["cells"]
        p_val = t["mcnemar"]["p_value_exact"]
        q_val = q_values_mcnemar[i]
        cat_tests[cat]["mcnemar"]["fdr_q_value"] = q_val
        print(f"{cat:<16} | {t['n_20b_pass']:>3}/125 ({t['p_20b']*100:>4.1f}%) | {t['n_120b_pass']:>3}/125 ({t['p_120b']*100:>4.1f}%) | "
              f"{t['delta_pass_rate']*100:>+5.1f}% | {cell_dict['Cell_A_PASS_PASS']:>6} | {cell_dict['Cell_B_FAIL_PASS']:>6} | {cell_dict['Cell_C_PASS_FAIL']:>6} | {cell_dict['Cell_D_FAIL_FAIL']:>6} | "
              f"{p_val:<11.4e} | {q_val:<11.4e}")
              
    print(f"\nStudy-Wide McNemar's Test: chi2 = {overall_test['mcnemar']['chi2_stat']:.4f}, "
          f"exact two-sided p = {overall_test['mcnemar']['p_value_exact']:.4e}, "
          f"discordant odds ratio (B/C) = {overall_test['mcnemar']['odds_ratio']:.3f}")
          
    # -------------------------------------------------------------
    # 3. Bootstrap Resampling (Pareto Frontier, 1,000 iterations)
    # -------------------------------------------------------------
    print("\n--- 3. Non-Parametric Bootstrap Pareto Analysis (1,000 resamples) ---")
    boot_results, random_prompt_bootstrap_ci = run_bootstrap_analysis(dataset, n_iterations=1000, seed=42)
    print("Bootstrap completed successfully.")
    print("Example Pareto points (Mean & 95% Bootstrap CI):")
    for th in ["0.0", "0.25", "0.35", "0.45", "0.5", "0.65", "0.75", "1.0"]:
        b_res = boot_results[th]
        print(f"  theta={float(th):<4.2f}: Pass Rate = {b_res['pass_rate_mean']*100:.1f}% [{b_res['pass_rate_ci_95'][0]*100:.1f}% - {b_res['pass_rate_ci_95'][1]*100:.1f}%], "
              f"Cost = ${b_res['cost_mean']:.5f} [${b_res['cost_ci_95'][0]:.5f} - ${b_res['cost_ci_95'][1]:.5f}], "
              f"Savings = {b_res['savings_mean']:.1f}% [{b_res['savings_ci_95'][0]:.1f}% - {b_res['savings_ci_95'][1]:.1f}%]")

    # -------------------------------------------------------------
    # 4. Fixed Baselines Accounting
    # -------------------------------------------------------------
    print("\n--- 4. Fixed Baselines Performance & Cost ---")
    cost_20b_all = sum(x["cost_20b"] for x in dataset)
    cost_120b_all = sum(x["cost_120b"] for x in dataset)
    
    cost_random = (cost_20b_all + cost_120b_all) / 2.0
    pass_random = (overall_test["n_20b_pass"] + overall_test["n_120b_pass"]) / 2.0
    p_random = pass_random / 500
    
    # Random baseline uncertainty calculations:
    # 1. Exact Algorithmic Randomization Interval for the fixed 500 prompts:
    # K = 306 + Binomial(97, 0.5)
    disc_pairs = b + c
    var_k = disc_pairs * 0.25
    se_k = math.sqrt(var_k)
    se_p = se_k / 500
    x_low = int(binom.ppf(0.025, disc_pairs, 0.5))
    x_high = int(binom.ppf(0.975, disc_pairs, 0.5))
    ci_algorithmic_count = [a + x_low, a + x_high]
    ci_algorithmic_rate = [(a + x_low) / 500, (a + x_high) / 500]
    
    # Oracle router:
    oracle_pass = 0
    oracle_cost = 0.0
    for item in dataset:
        if item["verdict_20b"] == "PASS":
            oracle_pass += 1
            oracle_cost += item["cost_20b"]
        elif item["verdict_120b"] == "PASS":
            oracle_pass += 1
            oracle_cost += item["cost_120b"]
        else:
            oracle_cost += item["cost_20b"]
    p_oracle = oracle_pass / 500
    
    baselines = {
        "Always_120B": {
            "pass_count": overall_test["n_120b_pass"],
            "pass_rate": overall_test["p_120b"],
            "pass_ci": overall_test["ci_120b"],
            "cost": cost_120b_all,
            "cost_savings_pct": 0.0,
            "quality_retention_pct": 100.0
        },
        "Always_20B": {
            "pass_count": overall_test["n_20b_pass"],
            "pass_rate": overall_test["p_20b"],
            "pass_ci": overall_test["ci_20b"],
            "cost": cost_20b_all,
            "cost_savings_pct": (cost_120b_all - cost_20b_all) / cost_120b_all * 100.0,
            "quality_retention_pct": overall_test["p_20b"] / overall_test["p_120b"] * 100.0
        },
        "Random_50_50": {
            "pass_count_expected": pass_random,
            "pass_rate_expected": p_random,
            "ci_algorithmic_randomization_95": {
                "estimand": "Algorithmic randomization uncertainty across coin flips conditional on fixed 500 prompts",
                "formula": "K = A + Binomial(B + C, 0.5)",
                "concordant_passes_A": a,
                "discordant_pairs_B_plus_C": disc_pairs,
                "se": se_p,
                "pass_count_ci": ci_algorithmic_count,
                "pass_rate_ci": ci_algorithmic_rate
            },
            "ci_prompt_bootstrap_95": {
                "estimand": "Superpopulation prompt-sampling uncertainty across evaluation prompt distribution",
                "method": "non_parametric_prompt_bootstrap_1000",
                "resampling_unit": "prompt_preserving_paired_outcomes",
                "pass_rate_ci": random_prompt_bootstrap_ci
            },
            "cost": cost_random,
            "cost_savings_pct": (cost_120b_all - cost_random) / cost_120b_all * 100.0,
            "quality_retention_pct": p_random / overall_test["p_120b"] * 100.0
        },
        "Oracle": {
            "label": "Oracle (Hindsight Upper Bound, Non-Deployable)",
            "description": "Hindsight-only theoretical ceiling assuming perfect knowledge of both models' outcomes on each prompt; not an operational router.",
            "pass_count": oracle_pass,
            "pass_rate": p_oracle,
            "pass_ci": wilson_score_ci(oracle_pass, 500),
            "cost": oracle_cost,
            "cost_savings_pct": (cost_120b_all - oracle_cost) / cost_120b_all * 100.0,
            "quality_retention_pct": p_oracle / overall_test["p_120b"] * 100.0
        }
    }
    
    print(f"  Always_120B   : Pass = {baselines['Always_120B']['pass_rate']*100:.1f}%, Cost = ${baselines['Always_120B']['cost']:.5f}")
    print(f"  Always_20B    : Pass = {baselines['Always_20B']['pass_rate']*100:.1f}%, Cost = ${baselines['Always_20B']['cost']:.5f}, Savings = {baselines['Always_20B']['cost_savings_pct']:.2f}%")
    print(f"  Random_50_50  : Expected Pass = {p_random*100:.1f}% ({pass_random}/500), Cost = ${cost_random:.5f}, Savings = {baselines['Random_50_50']['cost_savings_pct']:.2f}%")
    print(f"                  Exact Algorithmic 95% CI: [{ci_algorithmic_rate[0]*100:.2f}%, {ci_algorithmic_rate[1]*100:.2f}%] ({ci_algorithmic_count[0]} - {ci_algorithmic_count[1]} passes)")
    print(f"                  Prompt Bootstrap 95% CI:  [{random_prompt_bootstrap_ci[0]*100:.2f}%, {random_prompt_bootstrap_ci[1]*100:.2f}%]")
    print(f"  Oracle (Hindsight Upper Bound, Non-Deployable): Pass = {p_oracle*100:.1f}%, Cost = ${oracle_cost:.5f}, Savings = {baselines['Oracle']['cost_savings_pct']:.2f}%")

    # -------------------------------------------------------------
    # 5. Router Threshold Sweep (21 thresholds: 0.0 to 1.0)
    # -------------------------------------------------------------
    print("\n--- 5. Router Threshold Sweep across theta in [0.0, 1.0] ---")
    sweep = run_threshold_sweep(dataset)
    
    print(f"{'Theta':<6} | {'Route 20B':<9} | {'Route 120B':<10} | {'Pass Rate':<17} | {'Total Cost':<11} | {'Savings %':<10} | {'Res Task Pass':<14} | {'Oracle Target':<14}")
    print("-" * 108)
    for row in sweep:
        theta = row["theta"]
        savings = (cost_120b_all - row["total_cost"]) / cost_120b_all * 100.0
        qual_ret = row["pass_rate"] / overall_test["p_120b"] * 100.0
        row["cost_savings_pct"] = savings
        row["quality_retention_pct"] = qual_ret
        print(f"{theta:<6.2f} | {row['routed_to_20b']:>4} ({row['pct_to_20b']*100:>4.1f}%) | "
              f"{row['routed_to_120b']:>4} ({(1-row['pct_to_20b'])*100:>4.1f}%) | "
              f"{row['pass_rate']*100:>5.1f}% [{row['pass_rate_ci'][0]*100:>4.1f}-{row['pass_rate_ci'][1]*100:>4.1f}%] | "
              f"${row['total_cost']:<9.5f} | {savings:>8.2f}% | "
              f"{row['resolvable_task_pass_rate']*100:>12.2f}% | {row['oracle_cost_target_agreement']*100:>12.2f}%")

    # -------------------------------------------------------------
    # 6. Summarization Split Sensitivity Analysis (50 Independent vs 75 Assisted)
    # -------------------------------------------------------------
    print("\n--- 6. Summarization Split Sensitivity: 50 Independent vs 75 Assisted ---")
    summ_indep = [x for x in dataset if x["category"] == "summarization" and not x["is_assisted_summarization"]]
    summ_assisted = [x for x in dataset if x["category"] == "summarization" and x["is_assisted_summarization"]]
    
    test_indep = run_paired_tests(summ_indep, label="Summarization (Independent, n=50)")
    test_assisted = run_paired_tests(summ_assisted, label="Summarization (Assisted, n=75)")
    
    print(f"Independent (n={len(summ_indep)}): 20B Pass = {test_indep['n_20b_pass']}/{len(summ_indep)} ({test_indep['p_20b']*100:.1f}%), "
          f"120B Pass = {test_indep['n_120b_pass']}/{len(summ_indep)} ({test_indep['p_120b']*100:.1f}%), "
          f"Delta = {test_indep['delta_pass_rate']*100:+.1f}%, McNemar p = {test_indep['mcnemar']['p_value_exact']:.4f}")
    print(f"Assisted    (n={len(summ_assisted)}): 20B Pass = {test_assisted['n_20b_pass']}/{len(summ_assisted)} ({test_assisted['p_20b']*100:.1f}%), "
          f"120B Pass = {test_assisted['n_120b_pass']}/{len(summ_assisted)} ({test_assisted['p_120b']*100:.1f}%), "
          f"Delta = {test_assisted['delta_pass_rate']*100:+.1f}%, McNemar p = {test_assisted['mcnemar']['p_value_exact']:.4f}")
          
    f_20b_odds, f_20b_p = fisher_exact([[test_indep['n_20b_pass'], 50 - test_indep['n_20b_pass']],
                                        [test_assisted['n_20b_pass'], 75 - test_assisted['n_20b_pass']]])
    f_120b_odds, f_120b_p = fisher_exact([[test_indep['n_120b_pass'], 50 - test_indep['n_120b_pass']],
                                          [test_assisted['n_120b_pass'], 75 - test_assisted['n_120b_pass']]])
    print(f"Sub-split Difference Tests (Independent vs Assisted):")
    print(f"  20B Pass Rate Difference Fisher exact p:  {f_20b_p:.4f} (Odds ratio: {f_20b_odds:.3f})")
    print(f"  120B Pass Rate Difference Fisher exact p: {f_120b_p:.4f} (Odds ratio: {f_120b_odds:.3f})")

    # -------------------------------------------------------------
    # 7. Compile Final Results Artifact
    # -------------------------------------------------------------
    output_payload = {
        "metadata": {
            "title": "Phase 4 Statistical Analysis & Routing Evaluation",
            "study_prompts": n_total,
            "categories": categories,
            "prompts_per_category": 125,
            "bootstrap_iterations": 1000,
            "bootstrap_seed": 42
        },
        "study_wide": overall_test,
        "category_analyses": cat_tests,
        "baselines": baselines,
        "threshold_sweep": sweep,
        "bootstrap_pareto": boot_results,
        "summarization_split_sensitivity": {
            "independent_50": test_indep,
            "assisted_75": test_assisted,
            "fisher_20b_indep_vs_assisted": {"p_value": f_20b_p, "odds_ratio": f_20b_odds},
            "fisher_120b_indep_vs_assisted": {"p_value": f_120b_p, "odds_ratio": f_120b_odds}
        }
    }
    
    out_path = DATA_DIR / "phase4_statistical_results.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(output_payload, f, indent=2)
    print(f"\n[OK] Corrected Phase 4 results saved to: {out_path}")
    print("=" * 80)

if __name__ == "__main__":
    main()
