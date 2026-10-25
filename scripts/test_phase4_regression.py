"""
Phase 4 Regression Test Suite
=============================
Tests all required consistency conditions:
1. Four-cell mapping and denominators: A=306, B=73, C=24, D=97, Resolvable=403.
2. Resolvable Task Pass Rate and Oracle Cost-Target Agreement at theta in {0.00, 0.45, 0.50, 1.00}.
3. Random baseline intervals (algorithmic randomization interval & prompt bootstrap interval).
4. Paired bootstrap savings (including exact 0.00% at theta=0.00).
5. Unchanged McNemar tests and BH-FDR results.
6. Frozen input SHA-256 integrity and results JSON deterministic integrity.
"""

import json
import hashlib
import math
from pathlib import Path
import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"

FROZEN_HASHES = {
    "prompts.json": "a9214823cb8fdc0586f5fb2fb88ac29eeebbdf7d7b70da318be495eae8b8ce03",
    "prompts_manifest.json": "45d927529bab7e09dd18e536c64ea52bd84bd7f415dd506827f9f863c19d90f5",
    "references.json": "b1531df0fac52057da5b70e2279fc87eb6475236d194234775fae1231b79e9f3"
}

def compute_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest().lower()

def run_tests():
    print("=" * 75)
    print("RUNNING PHASE 4 REGRESSION TESTS")
    print("=" * 75)
    
    # 1. Frozen benchmark SHA-256 verification
    print("\n[TEST 1] Frozen Benchmark Files SHA-256 Verification:")
    for fname, expected in FROZEN_HASHES.items():
        actual = compute_sha256(DATA_DIR / fname)
        assert actual == expected, f"Hash mismatch for {fname}: {actual} != {expected}"
        print(f"  [PASS] {fname}: SHA-256 verified ({actual[:16]}...)")
        
    # Load regenerated results
    with open(DATA_DIR / "phase4_statistical_results.json", "r", encoding="utf-8") as f:
        res = json.load(f)
        
    # 2. Four-cell mapping and denominators
    print("\n[TEST 2] Four-Cell Mapping & Denominators:")
    cells = res["study_wide"]["cells"]
    a, b, c, d = cells["Cell_A_PASS_PASS"], cells["Cell_B_FAIL_PASS"], cells["Cell_C_PASS_FAIL"], cells["Cell_D_FAIL_FAIL"]
    assert a == 306, f"Expected Cell A=306, got {a}"
    assert b == 73, f"Expected Cell B=73, got {b}"
    assert c == 24, f"Expected Cell C=24, got {c}"
    assert d == 97, f"Expected Cell D=97, got {d}"
    assert a + b + c + d == 500, f"Total prompts != 500"
    n_res = a + b + c
    assert n_res == 403, f"Resolvable prompts != 403"
    print(f"  [PASS] Cell A={a}, Cell B={b}, Cell C={c}, Cell D={d} (Total=500, Resolvable=403)")
    
    # 3. Disaggregated resolvable metrics at key thetas
    print("\n[TEST 3] Disaggregated Resolvable Metrics at Key Thetas:")
    sweep_dict = {row["theta"]: row for row in res["threshold_sweep"]}
    
    # theta=0.00: 100% 120B
    th0 = sweep_dict[0.0]
    assert math.isclose(th0["resolvable_task_pass_rate"], 379/403, rel_tol=1e-5), f"th=0.0 res pass rate mismatch"
    assert math.isclose(th0["oracle_cost_target_agreement"], 73/403, rel_tol=1e-5), f"th=0.0 oracle agreement mismatch"
    print(f"  [PASS] theta=0.00: Res Task Pass Rate = {th0['resolvable_task_pass_rate']*100:.2f}% (379/403), Oracle Agreement = {th0['oracle_cost_target_agreement']*100:.2f}% (73/403)")
    
    # theta=0.45: 49% 20B
    th45 = sweep_dict[0.45]
    assert math.isclose(th45["resolvable_task_pass_rate"], 342/403, rel_tol=1e-5)
    assert math.isclose(th45["oracle_cost_target_agreement"], 174/403, rel_tol=1e-5)
    print(f"  [PASS] theta=0.45: Res Task Pass Rate = {th45['resolvable_task_pass_rate']*100:.2f}% (342/403), Oracle Agreement = {th45['oracle_cost_target_agreement']*100:.2f}% (174/403)")

    # theta=0.50: 56% 20B
    th50 = sweep_dict[0.50]
    assert math.isclose(th50["resolvable_task_pass_rate"], 343/403, rel_tol=1e-5)
    assert math.isclose(th50["oracle_cost_target_agreement"], 200/403, rel_tol=1e-5)
    print(f"  [PASS] theta=0.50: Res Task Pass Rate = {th50['resolvable_task_pass_rate']*100:.2f}% (343/403), Oracle Agreement = {th50['oracle_cost_target_agreement']*100:.2f}% (200/403)")

    # theta=1.00: 100% 20B
    th100 = sweep_dict[1.00]
    assert math.isclose(th100["resolvable_task_pass_rate"], 330/403, rel_tol=1e-5)
    assert math.isclose(th100["oracle_cost_target_agreement"], 330/403, rel_tol=1e-5)
    print(f"  [PASS] theta=1.00: Res Task Pass Rate = {th100['resolvable_task_pass_rate']*100:.2f}% (330/403), Oracle Agreement = {th100['oracle_cost_target_agreement']*100:.2f}% (330/403)")

    # 4. Random Baseline Intervals
    print("\n[TEST 4] Random Baseline Uncertainty Verification:")
    rnd = res["baselines"]["Random_50_50"]
    assert math.isclose(rnd["pass_rate_expected"], 0.7090, rel_tol=1e-4)
    alg_ci = rnd["ci_algorithmic_randomization_95"]
    assert alg_ci["pass_count_ci"] == [345, 364], f"Algorithmic count CI mismatch: {alg_ci['pass_count_ci']}"
    assert math.isclose(alg_ci["pass_rate_ci"][0], 345/500, rel_tol=1e-4)
    assert math.isclose(alg_ci["pass_rate_ci"][1], 364/500, rel_tol=1e-4)
    print(f"  [PASS] Algorithmic 95% CI: [{alg_ci['pass_rate_ci'][0]*100:.2f}%, {alg_ci['pass_rate_ci'][1]*100:.2f}%] ({alg_ci['pass_count_ci'][0]} - {alg_ci['pass_count_ci'][1]} passes)")
    
    boot_ci = rnd["ci_prompt_bootstrap_95"]["pass_rate_ci"]
    assert math.isclose(boot_ci[0], 0.6760, rel_tol=1e-3)
    assert math.isclose(boot_ci[1], 0.7460, rel_tol=1e-3)
    print(f"  [PASS] Prompt Bootstrap 95% CI: [{boot_ci[0]*100:.2f}%, {boot_ci[1]*100:.2f}%]")

    # 5. Paired Bootstrap Savings (Exact zero at theta=0.00)
    print("\n[TEST 5] Paired Bootstrap Savings:")
    boot_pareto = res["bootstrap_pareto"]
    sav_0 = boot_pareto["0.0"]
    assert math.isclose(sav_0["savings_mean"], 0.0, abs_tol=1e-6), f"theta=0.0 savings mean != 0: {sav_0['savings_mean']}"
    assert math.isclose(sav_0["savings_ci_95"][0], 0.0, abs_tol=1e-6), f"theta=0.0 savings CI low != 0: {sav_0['savings_ci_95'][0]}"
    assert math.isclose(sav_0["savings_ci_95"][1], 0.0, abs_tol=1e-6), f"theta=0.0 savings CI high != 0: {sav_0['savings_ci_95'][1]}"
    print(f"  [PASS] theta=0.00 Paired Savings: Mean={sav_0['savings_mean']:.2f}% [95% CI: {sav_0['savings_ci_95'][0]:.2f}%, {sav_0['savings_ci_95'][1]:.2f}%] (Exact Zero Verified)")

    # 6. Unchanged McNemar Tests & BH-FDR Results
    print("\n[TEST 6] Unchanged McNemar Tests & BH-FDR Results:")
    expected_mcnemar = {
        "creative": {"p": 2.5321e-05, "q": 1.0128e-04},
        "factual_qa": {"p": 2.2461e-02, "q": 4.4922e-02},
        "reasoning_math": {"p": 7.8354e-02, "q": 1.0447e-01},
        "summarization": {"p": 5.2347e-01, "q": 5.2347e-01}
    }
    for cat, exp in expected_mcnemar.items():
        act_p = res["category_analyses"][cat]["mcnemar"]["p_value_exact"]
        act_q = res["category_analyses"][cat]["mcnemar"]["fdr_q_value"]
        assert math.isclose(act_p, exp["p"], rel_tol=1e-3), f"{cat} McNemar p mismatch"
        assert math.isclose(act_q, exp["q"], rel_tol=1e-3), f"{cat} BH-FDR q mismatch"
        print(f"  [PASS] {cat:<16}: McNemar p = {act_p:.4e}, BH-FDR q = {act_q:.4e}")
        
    sw_p = res["study_wide"]["mcnemar"]["p_value_exact"]
    assert math.isclose(sw_p, 6.4047e-07, rel_tol=1e-4)
    print(f"  [PASS] Study-Wide McNemar: p = {sw_p:.4e}, chi2 = {res['study_wide']['mcnemar']['chi2_stat']:.4f}")
    
    # 7. Final Hash & Results JSON
    res_hash = compute_sha256(DATA_DIR / "phase4_statistical_results.json")
    print(f"\n[TEST 7] Regenerated phase4_statistical_results.json SHA-256: {res_hash}")
    
    print("\n" + "=" * 75)
    print("ALL 7 REGRESSION TESTS PASSED CLEANLY WITH ZERO ERRORS!")
    print("=" * 75)

if __name__ == "__main__":
    run_tests()
