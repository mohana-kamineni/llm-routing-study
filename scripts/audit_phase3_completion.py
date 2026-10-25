"""
Phase 3 Full Integrity & Completeness Audit
===========================================
Audits all 1,000 evaluation records across both models:
- 500 openai/gpt-oss-20b
- 500 openai/gpt-oss-120b

Verifies:
1. Frozen benchmark files SHA-256 integrity (prompts, references, manifest).
2. Candidate response files presence and integrity (1,000 files).
3. Evaluation files count, naming, validity, and JSON parseability.
4. Category completeness: exactly 125 per category per model, 250 study-wide.
5. All 500 prompts accounted for with 1-to-1 matching across both models.
6. Terminal failure accounting:
   - 20B: 38 empty_text, 2 tool_use, 8 candidate_degenerate
   - 120B: 1 candidate_degenerate
7. Zero unresolved evaluator errors or unparseables (PASS + FAIL = 500 per model).
8. Token usage telemetry across evaluated records.
"""

import json
import hashlib
from pathlib import Path
from collections import Counter, defaultdict

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"
EVALS_DIR = DATA_DIR / "evaluations"
RESPONSES_DIR = DATA_DIR / "responses"

FROZEN_HASHES = {
    "prompts.json": "a9214823cb8fdc0586f5fb2fb88ac29eeebbdf7d7b70da318be495eae8b8ce03",
    "prompts_manifest.json": "45d927529bab7e09dd18e536c64ea52bd84bd7f415dd506827f9f863c19d90f5",
    "references.json": "b1531df0fac52057da5b70e2279fc87eb6475236d194234775fae1231b79e9f3"
}

EXPECTED_CATEGORIES = ["factual_qa", "reasoning_math", "summarization", "creative"]
MODELS = ["openai_gpt-oss-20b", "openai_gpt-oss-120b"]

def compute_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest().lower()

def main():
    print("=" * 70)
    print("PHASE 3 COMPLETENESS & INTEGRITY AUDIT")
    print("=" * 70)
    
    # 1. Verify frozen benchmark files
    print("\n--- 1. Frozen Benchmark Files SHA-256 Integrity ---")
    benchmark_ok = True
    for fname, expected_hash in FROZEN_HASHES.items():
        fpath = DATA_DIR / fname
        if not fpath.exists():
            print(f"[FAIL] Missing {fname}")
            benchmark_ok = False
            continue
        actual_hash = compute_sha256(fpath)
        if actual_hash == expected_hash:
            print(f"[OK] {fname}: SHA-256 verified ({actual_hash[:16]}...)")
        else:
            print(f"[FAIL] {fname}: HASH MISMATCH! Expected {expected_hash}, got {actual_hash}")
            benchmark_ok = False
    assert benchmark_ok, "Benchmark integrity check failed!"
            
    # Load prompts
    with open(DATA_DIR / "prompts.json", "r", encoding="utf-8") as f:
        prompts = json.load(f)["prompts"]
    print(f"\nTotal prompts loaded: {len(prompts)}")
    prompt_ids = {p["prompt_id"] for p in prompts}
    prompt_cat = {p["prompt_id"]: p["category"] for p in prompts}
    assert len(prompt_ids) == 500, f"Expected 500 prompts, got {len(prompt_ids)}"
    
    cat_counts = Counter(p["category"] for p in prompts)
    for cat in EXPECTED_CATEGORIES:
        print(f"  Category '{cat}': {cat_counts[cat]} prompts")
        assert cat_counts[cat] == 125, f"Expected 125 in {cat}, got {cat_counts[cat]}"

    # Load references
    with open(DATA_DIR / "references.json", "r", encoding="utf-8") as f:
        refs = json.load(f)["references"]
    print(f"Total references loaded: {len(refs)}")
    assert len(refs) == 500, f"Expected 500 references, got {len(refs)}"
    ref_ids = {r["prompt_id"] for r in refs}
    assert ref_ids == prompt_ids, "References prompt_ids do not match prompts.json!"

    # 2. Candidate responses integrity
    print("\n--- 2. Candidate Responses Accounting ---")
    resp_files = list(RESPONSES_DIR.glob("*.json"))
    print(f"Total candidate response files: {len(resp_files)}")
    assert len(resp_files) == 1000, f"Expected 1,000 response files, got {len(resp_files)}"
    
    resp_by_model = defaultdict(list)
    for rf in resp_files:
        for m in MODELS:
            if rf.name.endswith(f"_{m}.json"):
                resp_by_model[m].append(rf)
                break
    for m in MODELS:
        print(f"  {m}: {len(resp_by_model[m])} response files")
        assert len(resp_by_model[m]) == 500, f"Expected 500 responses for {m}"

    # 3. Evaluations Accounting
    print("\n--- 3. Evaluations Ledger Accounting ---")
    eval_files = list(EVALS_DIR.glob("*.json"))
    print(f"Total evaluation files: {len(eval_files)}")
    assert len(eval_files) == 1000, f"Expected 1,000 evaluation files, got {len(eval_files)}"
    
    eval_records = {m: {} for m in MODELS}
    corrupt_files = []
    
    for ef in eval_files:
        try:
            with open(ef, "r", encoding="utf-8") as f:
                d = json.load(f)
        except Exception as e:
            corrupt_files.append((ef.name, str(e)))
            continue
            
        m_slug = d.get("model_slug")
        pid = d.get("prompt_id")
        if m_slug in eval_records:
            eval_records[m_slug][pid] = d
            
    print(f"Corrupt JSON files: {len(corrupt_files)}")
    assert len(corrupt_files) == 0, f"Found corrupt files: {corrupt_files}"
    
    for m in MODELS:
        print(f"  {m}: {len(eval_records[m])} valid records")
        assert len(eval_records[m]) == 500, f"Expected 500 records for {m}, got {len(eval_records[m])}"
        # Verify 1-to-1 prompt correspondence
        missing_pids = prompt_ids - set(eval_records[m].keys())
        assert len(missing_pids) == 0, f"Missing prompt IDs for {m}: {missing_pids}"

    # 4. Verdicts and Terminal Subtypes Breakdown
    print("\n--- 4. Verdicts and Terminal Subtype Reconciliations ---")
    audit_results = {}
    for m in MODELS:
        records = list(eval_records[m].values())
        verdict_counts = Counter(r.get("verdict") for r in records)
        evaluator_counts = Counter(r.get("evaluator") for r in records)
        terminal_counts = Counter(r.get("terminal_type") for r in records if "terminal_type" in r)
        
        # Category breakdown
        cat_verdicts = defaultdict(Counter)
        for r in records:
            cat = r.get("category", prompt_cat[r["prompt_id"]])
            cat_verdicts[cat][r.get("verdict")] += 1
            
        # Token usage
        prompt_tokens = sum(r.get("prompt_tokens", 0) for r in records)
        comp_tokens = sum(r.get("completion_tokens", 0) for r in records)
        total_tokens = sum(r.get("total_tokens", 0) for r in records)
        
        print(f"\nModel: {m}")
        print(f"  Total records: {len(records)}")
        print(f"  Verdicts: {dict(verdict_counts)}")
        assert verdict_counts["ERROR"] == 0, f"Unresolved ERROR records in {m}"
        assert verdict_counts["EVALUATOR_ERROR"] == 0, f"Unresolved EVALUATOR_ERROR records in {m}"
        assert verdict_counts["UNPARSEABLE"] == 0, f"Unresolved UNPARSEABLE records in {m}"
        assert verdict_counts["EVALUATOR_UNPARSEABLE"] == 0, f"Unresolved EVALUATOR_UNPARSEABLE records in {m}"
        assert verdict_counts["PASS"] + verdict_counts["FAIL"] == 500, f"PASS + FAIL != 500 for {m}"
        
        print(f"  Terminal failures: {dict(terminal_counts)}")
        print(f"  Evaluators: {dict(evaluator_counts)}")
        print(f"  Category breakdown:")
        for cat in EXPECTED_CATEGORIES:
            cv = cat_verdicts[cat]
            print(f"    {cat:<15}: PASS={cv['PASS']:3d}, FAIL={cv['FAIL']:3d}, Total={cv['PASS'] + cv['FAIL']}")
            assert cv['PASS'] + cv['FAIL'] == 125, f"Category total != 125 for {cat} in {m}"
            
        print(f"  Token telemetry: prompt={prompt_tokens:,}, completion={comp_tokens:,}, total={total_tokens:,}")
        
        audit_results[m] = {
            "total": len(records),
            "verdicts": dict(verdict_counts),
            "terminal_types": dict(terminal_counts),
            "category_verdicts": {c: dict(v) for c, v in cat_verdicts.items()},
            "tokens": {"prompt": prompt_tokens, "completion": comp_tokens, "total": total_tokens}
        }

    # 5. Verify specific predetermined terminal failures
    print("\n--- 5. Predetermined Terminal Case Verification ---")
    # 20B terminal failures
    r20 = eval_records["openai_gpt-oss-20b"]
    t20 = audit_results["openai_gpt-oss-20b"]["terminal_types"]
    assert t20.get("empty_text_generation") == 38, f"Expected 38 empty_text, got {t20.get('empty_text_generation')}"
    assert t20.get("tool_use_api_rejection") == 2, f"Expected 2 tool_use, got {t20.get('tool_use_api_rejection')}"
    assert t20.get("CANDIDATE_DEGENERATE") == 8, f"Expected 8 candidate_degenerate, got {t20.get('CANDIDATE_DEGENERATE')}"
    print(f"[OK] 20B terminal failures exactly verified: 38 empty + 2 tool_use + 8 degenerate = 48 total candidate-side failures.")
    
    # 120B terminal failures
    r120 = eval_records["openai_gpt-oss-120b"]
    t120 = audit_results["openai_gpt-oss-120b"]["terminal_types"]
    assert t120.get("CANDIDATE_DEGENERATE") == 1, f"Expected 1 degenerate for 120B, got {t120.get('CANDIDATE_DEGENERATE')}"
    assert "empty_text_generation" not in t120, "Unexpected empty_text in 120B"
    assert "tool_use_api_rejection" not in t120, "Unexpected tool_use in 120B"
    
    # Specifically verify 97ec5b5740b24a758692253107de2b86
    deg_pid = "97ec5b5740b24a758692253107de2b86"
    assert deg_pid in r120, f"Missing 120B degenerate record for {deg_pid}"
    assert r120[deg_pid]["verdict"] == "FAIL"
    assert r120[deg_pid].get("terminal_type") == "CANDIDATE_DEGENERATE"
    print(f"[OK] 120B degenerate failure {deg_pid} verified: verdict=FAIL, terminal_type=CANDIDATE_DEGENERATE.")

    # 6. Study-wide totals
    print("\n--- 6. Study-Wide Totals ---")
    total_evals = sum(audit_results[m]["total"] for m in MODELS)
    total_pass = sum(audit_results[m]["verdicts"]["PASS"] for m in MODELS)
    total_fail = sum(audit_results[m]["verdicts"]["FAIL"] for m in MODELS)
    print(f"Total Evaluations: {total_evals:,} / 1,000")
    print(f"Total PASS:        {total_pass} ({total_pass/total_evals*100:.1f}%)")
    print(f"Total FAIL:        {total_fail} ({total_fail/total_evals*100:.1f}%)")
    print(f"Unresolved Errors: 0")
    print(f"Unparseables:      0")

    # Save audit report JSON
    audit_report_path = DATA_DIR / "phase3_final_audit_report.json"
    with open(audit_report_path, "w", encoding="utf-8") as f:
        json.dump({
            "status": "PASSED",
            "benchmark_integrity": benchmark_ok,
            "models": audit_results,
            "study_wide": {
                "total_evaluations": total_evals,
                "total_pass": total_pass,
                "total_fail": total_fail,
                "unresolved_errors": 0,
                "unparseable": 0
            }
        }, f, indent=2)
    print(f"\n[OK] Phase 3 final audit report saved to: {audit_report_path}")
    print("=" * 70)
    print("ALL INTEGRITY CHECKS PASSED PERFECTLY!")
    print("=" * 70)

if __name__ == "__main__":
    main()
