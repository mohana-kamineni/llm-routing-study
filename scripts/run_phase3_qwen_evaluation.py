"""
Project 2 — Phase 3: Qwen Evaluator Scoring
=============================================

Evaluates all 500×2 candidate responses using qwen/qwen3.8-27b with
predefined category-specific PASS/FAIL rubrics.

- 460 paired usable responses: both 20B and 120B evaluated by Qwen
- 38 empty-text terminal 20B cases: auto-FAIL for 20B, Qwen evaluates 120B
- 2 tool-use terminal 20B cases: auto-FAIL for 20B, Qwen evaluates 120B

Outputs:
  data/evaluations/{prompt_id}_{model_slug}_eval.json  — per-response verdict
  data/evaluation_summary.json                          — aggregated results
  data/human_validation_set.json                        — 32-prompt blinded set
"""

import os
import sys
import json
import time
import hashlib
import random
import re
import winreg
from pathlib import Path
from datetime import datetime, timezone
from openai import OpenAI

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# ── Paths ────────────────────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"
PROMPTS_FILE = DATA_DIR / "prompts.json"
REFS_FILE = DATA_DIR / "references.json"
RESPONSES_DIR = DATA_DIR / "responses"
EVALS_DIR = DATA_DIR / "evaluations"
SUMMARY_FILE = DATA_DIR / "evaluation_summary.json"
VALIDATION_FILE = DATA_DIR / "human_validation_set.json"

FROZEN_PROMPTS_SHA256 = "a9214823cb8fdc0586f5fb2fb88ac29eeebbdf7d7b70da318be495eae8b8ce03"

# ── Configuration ────────────────────────────────────────────────────
QWEN_MODEL = "qwen/qwen3.8-27b"
QWEN_TEMP = 0.0
QWEN_MAX_TOKENS = 1024
RPM_DELAY = 2.2  # seconds between requests
MAX_RETRIES = 5

MODELS = [
    ("openai/gpt-oss-20b", "openai_gpt-oss-20b"),
    ("openai/gpt-oss-120b", "openai_gpt-oss-120b"),
]

VALIDATION_SEED = 42


# ── Groq client ──────────────────────────────────────────────────────

def get_groq_client():
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        try:
            k = winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment")
            api_key, _ = winreg.QueryValueEx(k, "GROQ_API_KEY")
        except Exception:
            pass
    if not api_key:
        raise RuntimeError("GROQ_API_KEY not found")
    return OpenAI(api_key=api_key, base_url="https://api.groq.com/openai/v1", timeout=60.0)


def verify_prompts():
    actual = hashlib.sha256(open(PROMPTS_FILE, "rb").read()).hexdigest()
    if actual != FROZEN_PROMPTS_SHA256:
        raise ValueError(f"Prompts SHA mismatch: {actual}")
    print(f"[OK] prompts.json verified (SHA-256: {actual[:12]}...)")


# ── Terminal failure detection ───────────────────────────────────────

def classify_20b_response(fpath):
    """Returns: 'valid', 'terminal_empty', 'terminal_tool_use', or 'missing'."""
    if not fpath.exists():
        return "missing"
    try:
        with open(fpath, "r", encoding="utf-8") as f:
            d = json.load(f)
        status = d.get("status", "")
        rt = d.get("response_text", "")
        err = d.get("error", "") or ""
        if status == "success" and rt and len(rt) > 0:
            return "valid"
        elif status == "success" and (not rt or len(rt) == 0):
            return "terminal_empty"
        elif status == "error" and "tool choice is none" in err.lower():
            return "terminal_tool_use"
        return "other_error"
    except:
        return "corrupt"


# ── Category-specific evaluation prompts ─────────────────────────────

def build_eval_prompt(category, prompt_text, response_text, reference):
    """Build the Qwen evaluation prompt based on category rubric.

    Format requirement: The evaluator MUST emit the machine-readable verdict
    on the very first line ('VERDICT: PASS' or 'VERDICT: FAIL'), followed by
    a concise rationale. This ensures evaluations are truncation-resistant.
    """

    if category == "factual_qa":
        return f"""You are an expert evaluator. Evaluate whether the following response correctly answers the factual question.

QUESTION:
\"\"\"{prompt_text}\"\"\"

RESPONSE TO EVALUATE:
\"\"\"{response_text}\"\"\"

EVALUATION CRITERIA:
{reference['criteria']}

Evaluate the response for factual accuracy. Does the response provide the correct factual answer without false contradictions?

You MUST format your evaluation as follows:
On the very first line, state exactly your verdict:
VERDICT: PASS
or
VERDICT: FAIL

Following the verdict line, provide a concise rationale explaining your judgment."""

    elif category == "reasoning_math":
        return f"""You are an expert evaluator. Evaluate whether the following response correctly solves the reasoning/math problem.

PROBLEM:
\"\"\"{prompt_text}\"\"\"

RESPONSE TO EVALUATE:
\"\"\"{response_text}\"\"\"

EVALUATION CRITERIA:
{reference['criteria']}

Check if the response reaches the correct final answer AND contains no substantive reasoning errors in its solution process.

You MUST format your evaluation as follows:
On the very first line, state exactly your verdict:
VERDICT: PASS
or
VERDICT: FAIL

Following the verdict line, provide a concise rationale explaining your judgment."""

    elif category == "summarization":
        aspects_text = ""
        if reference.get("key_aspects") and len(reference["key_aspects"]) > 0:
            aspects = "\n".join(f"  {i+1}. {a}" for i, a in enumerate(reference["key_aspects"]))
            aspects_text = f"\nKEY ASPECTS THAT MUST BE COVERED:\n{aspects}\n"

        return f"""You are an expert evaluator. Evaluate whether the following response adequately summarizes the content.

SOURCE TEXT / PROMPT:
\"\"\"{prompt_text}\"\"\"

RESPONSE TO EVALUATE:
\"\"\"{response_text}\"\"\"

EVALUATION CRITERIA:
{reference['criteria']}
{aspects_text}
Evaluate whether the summary covers the essential factual aspects of the source material. The summary should be accurate and not omit critical information.

You MUST format your evaluation as follows:
On the very first line, state exactly your verdict:
VERDICT: PASS
or
VERDICT: FAIL

Following the verdict line, provide a concise rationale explaining your judgment."""

    elif category == "creative":
        dims = "\n".join(f"  - {d}" for d in reference.get("rubric_dimensions", []))
        return f"""You are an expert evaluator. Evaluate the following creative/open-ended response.

PROMPT:
\"\"\"{prompt_text}\"\"\"

RESPONSE TO EVALUATE:
\"\"\"{response_text}\"\"\"

EVALUATION DIMENSIONS:
{dims}

Evaluate the response across ALL four dimensions above. The response PASSES only if it satisfactorily addresses all four dimensions. It FAILS if it is deficient in any dimension (e.g., off-topic, incoherent, truncated/incomplete, or violates explicit constraints in the prompt).

You MUST format your evaluation as follows:
On the very first line, state exactly your verdict:
VERDICT: PASS
or
VERDICT: FAIL

Following the verdict line, provide a concise rationale explaining your judgment."""

    raise ValueError(f"Unknown category: {category}")


def parse_verdict(qwen_output):
    """Parse PASS/FAIL from Qwen output. Returns 'PASS', 'FAIL', or 'UNPARSEABLE'."""
    if not qwen_output:
        return "UNPARSEABLE"
    lines = [l.strip() for l in qwen_output.strip().splitlines() if l.strip()]
    if lines:
        first_line = lines[0].upper()
        m_first = re.search(r'(?:VERDICT:\s*)?\b(PASS|FAIL)\b', first_line)
        if m_first:
            return m_first.group(1)
    # Fallback: search across full output for VERDICT line
    matches = re.findall(r"VERDICT:\s*(PASS|FAIL)", qwen_output, re.IGNORECASE)
    if matches:
        return matches[0].upper()
    return "UNPARSEABLE"


# ── TPD-aware Qwen call ─────────────────────────────────────────────

def parse_retry_after(error_str):
    m = re.search(r'try again in\s+(?:(\d+)h)?(?:(\d+)m)?(?:([\d.]+)s)?', str(error_str))
    if not m:
        return None
    h = int(m.group(1) or 0)
    mi = int(m.group(2) or 0)
    s = float(m.group(3) or 0)
    return h * 3600 + mi * 60 + s

def is_tpd_exhaustion(error):
    """Detect genuine daily-token quota exhaustion (TPD).

    Must NOT match transient per-minute limits (TPM, OTPM, RPM).
    Genuine TPD errors from Groq contain explicit daily phrases such as:
    'tokens per day', 'limit 200000', or '(tpd)'.
    """
    msg = str(error).lower()
    if "per minute" in msg or "otpm" in msg or "tpm" in msg:
        return False
    return ("tokens per day" in msg or "limit 200000" in msg or "(tpd)" in msg)


def call_qwen_eval(client, eval_prompt):
    """Call Qwen with TPD-aware retry. Returns dict with raw output or quota signal."""
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            resp = client.chat.completions.create(
                model=QWEN_MODEL,
                messages=[{"role": "user", "content": eval_prompt}],
                temperature=QWEN_TEMP,
                max_tokens=QWEN_MAX_TOKENS,
            )
            choice = resp.choices[0] if resp.choices else None
            content = choice.message.content if choice and choice.message else ""
            finish_reason = choice.finish_reason if choice else "unknown"
            return {
                "status": "success",
                "raw_output": content,
                "finish_reason": finish_reason,
                "prompt_tokens": getattr(resp.usage, "prompt_tokens", 0),
                "completion_tokens": getattr(resp.usage, "completion_tokens", 0),
                "total_tokens": getattr(resp.usage, "total_tokens", 0),
            }
        except Exception as e:
            error_str = str(e)
            if is_tpd_exhaustion(e):
                retry_after = parse_retry_after(error_str)
                print(f"    [QUOTA] Genuine TPD exhaustion detected for {QWEN_MODEL}.")
                if retry_after:
                    print(f"    [QUOTA] Retry after: {retry_after:.0f}s ({retry_after/60:.1f}m)")
                return {
                    "status": "quota_exhausted",
                    "retry_after_seconds": retry_after,
                }

            # Check for permanent request size limits that cannot succeed with retries (e.g. HTTP 413 or ITPM > 7000)
            if "413" in error_str or "itpm" in error_str.lower() or "reduce your message size" in error_str.lower():
                print(f"    [PERMANENT_ERROR] Request exceeds API message size limits: {error_str[:120]}")
                return {"status": "permanent_error", "error": error_str[:500]}

            retry_after = parse_retry_after(error_str)
            if "otpm" in error_str.lower() and not retry_after:
                wait_s = 60.0
            else:
                wait_s = (retry_after + 1.0) if retry_after else max(2.0, float(2 ** attempt))
            print(f"    [TRANSIENT] Attempt {attempt}/{MAX_RETRIES} rate-limited/failed: {error_str[:120]}... Waiting {wait_s:.1f}s")
            if attempt < MAX_RETRIES:
                time.sleep(wait_s)

    return {"status": "error", "error": error_str[:500]}


# ── Checkpoint logic ─────────────────────────────────────────────────

def is_eval_complete(eval_path):
    """Check if an evaluation file exists and has a final terminal verdict."""
    if not eval_path.exists():
        return False
    try:
        with open(eval_path, "r", encoding="utf-8") as f:
            d = json.load(f)
        # Final terminal verdicts are PASS, FAIL, terminal EVALUATOR_UNPARSEABLE, or terminal EVALUATOR_ERROR
        # Temporary 'ERROR' records return False so they receive their normal retry attempts on resume
        return d.get("verdict") in ("PASS", "FAIL", "EVALUATOR_UNPARSEABLE", "EVALUATOR_ERROR")
    except:
        return False


# ── Main ─────────────────────────────────────────────────────────────

def main():
    print("=" * 70)
    print("PROJECT 2 — PHASE 3: QWEN EVALUATOR SCORING")
    print("=" * 70)

    verify_prompts()
    client = get_groq_client()
    EVALS_DIR.mkdir(parents=True, exist_ok=True)

    # Load data
    with open(PROMPTS_FILE, "r", encoding="utf-8") as f:
        prompts = json.load(f)["prompts"]
    with open(REFS_FILE, "r", encoding="utf-8") as f:
        refs_data = json.load(f)
    ref_by_id = {r["prompt_id"]: r for r in refs_data["references"]}

    total_prompts = len(prompts)
    print(f"Loaded {total_prompts} prompts and {len(ref_by_id)} references.")

    # ── Build evaluation task list ──
    # Round-robin across categories for even quota distribution
    CATEGORIES = ["factual_qa", "summarization", "reasoning_math", "creative"]
    by_cat = {c: [] for c in CATEGORIES}
    for p in prompts:
        by_cat[p["category"]].append(p)

    rr_prompts = []
    for i in range(125):
        for cat in CATEGORIES:
            rr_prompts.append(by_cat[cat][i])

    # ── Generate 32-prompt human validation set ──
    rng = random.Random(VALIDATION_SEED)
    validation_pids = set()
    for cat in CATEGORIES:
        usable = [p["prompt_id"] for p in prompts
                  if p["category"] == cat
                  and classify_20b_response(
                      RESPONSES_DIR / f"{p['prompt_id']}_openai_gpt-oss-20b.json"
                  ) == "valid"]
        selected = rng.sample(usable, 8)
        validation_pids.update(selected)

    # Save validation set (without verdicts — blinded)
    if not VALIDATION_FILE.exists():
        val_records = []
        for pid in validation_pids:
            p = next(pp for pp in prompts if pp["prompt_id"] == pid)
            val_records.append({
                "prompt_id": pid,
                "category": p["category"],
                "prompt_text": p["prompt_text"],
                # Blinded: no Qwen verdicts included
            })
        with open(VALIDATION_FILE, "w", encoding="utf-8") as f:
            json.dump({
                "metadata": {
                    "purpose": "32-prompt blinded human validation set",
                    "count": len(val_records),
                    "seed": VALIDATION_SEED,
                    "per_category": 8,
                    "created_at": datetime.now(timezone.utc).isoformat(),
                },
                "validation_prompts": val_records
            }, f, indent=2, ensure_ascii=False)
        print(f"[OK] Saved {len(val_records)}-prompt blinded validation set.")
    else:
        print(f"[OK] Validation set already exists ({VALIDATION_FILE.name}).")

    # ── Startup report ──
    print(f"\n{'=' * 60}")
    print("STARTUP RESUME REPORT")
    print(f"{'=' * 60}")

    total_tasks = 0
    total_complete = 0
    for model_name, model_slug in MODELS:
        complete = 0
        terminal_auto = 0
        remaining = 0
        for p in prompts:
            pid = p["prompt_id"]
            eval_path = EVALS_DIR / f"{pid}_{model_slug}_eval.json"
            if is_eval_complete(eval_path):
                complete += 1
            elif model_slug == "openai_gpt-oss-20b":
                cls = classify_20b_response(RESPONSES_DIR / f"{pid}_{model_slug}.json")
                if cls in ("terminal_empty", "terminal_tool_use"):
                    # These need auto-FAIL eval files
                    if not is_eval_complete(eval_path):
                        remaining += 1
                    else:
                        complete += 1
                elif cls == "valid":
                    remaining += 1
            else:
                remaining += 1
            total_tasks += 1

        total_complete += complete
        print(f"\n  {model_slug}:")
        print(f"    Evaluations complete:     {complete}")
        print(f"    Remaining:                {remaining}")

    total_remaining = total_tasks - total_complete
    print(f"\n  Total tasks:       {total_tasks}")
    print(f"  Complete:          {total_complete}")
    print(f"  Remaining:         {total_remaining}")
    print(f"{'=' * 60}\n")

    # ── Process evaluations ──
    t_start = time.time()
    results = {
        "qwen_calls": 0,
        "auto_fail_empty": 0,
        "auto_fail_tool_use": 0,
        "skipped": 0,
        "errors": 0,
        "quota_exhausted": False,
        "tokens": {"prompt": 0, "completion": 0, "total": 0},
    }

    quota_exhausted = False

    target_models = MODELS
    if "--model" in sys.argv:
        m_idx = sys.argv.index("--model") + 1
        if m_idx < len(sys.argv):
            target_slug = sys.argv[m_idx]
            target_models = [m for m in MODELS if target_slug == m[1] or m[1].endswith(f"-{target_slug}") or m[1].endswith(f"_{target_slug}")]
            print(f"Targeting specific model(s): {[m[1] for m in target_models]}")

    for model_name, model_slug in target_models:
        print(f"\n{'=' * 60}")
        print(f"Evaluating model: {model_name}")
        print(f"{'=' * 60}")

        generated_this_run = 0

        for idx, p in enumerate(rr_prompts, start=1):
            pid = p["prompt_id"]
            cat = p["category"]
            eval_path = EVALS_DIR / f"{pid}_{model_slug}_eval.json"

            # Skip if already evaluated
            if is_eval_complete(eval_path):
                results["skipped"] += 1
                continue

            # ── Handle terminal 20B failures ──
            if model_slug == "openai_gpt-oss-20b":
                cls = classify_20b_response(RESPONSES_DIR / f"{pid}_{model_slug}.json")

                if cls == "terminal_empty":
                    record = {
                        "prompt_id": pid,
                        "category": cat,
                        "model": model_name,
                        "model_slug": model_slug,
                        "evaluator": "auto_terminal_failure",
                        "terminal_type": "empty_text_generation",
                        "terminal_description": (
                            "Observed empty-response generation condition: "
                            "status=success, finish_reason=length, "
                            "completion_tokens=4096, response_text empty. "
                            "No usable candidate content for evaluation."
                        ),
                        "verdict": "FAIL",
                        "raw_output": None,
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    }
                    with open(eval_path, "w", encoding="utf-8") as f:
                        json.dump(record, f, indent=2, ensure_ascii=False)
                    results["auto_fail_empty"] += 1
                    generated_this_run += 1
                    continue

                elif cls == "terminal_tool_use":
                    record = {
                        "prompt_id": pid,
                        "category": cat,
                        "model": model_name,
                        "model_slug": model_slug,
                        "evaluator": "auto_terminal_failure",
                        "terminal_type": "tool_use_api_rejection",
                        "terminal_description": (
                            "Prompt-format-induced API rejection: prompt "
                            "contains explicit ReAct/Python-REPL instructions "
                            "and model attempted structured tool call under "
                            "tools=None configuration, producing deterministic "
                            "400 error."
                        ),
                        "verdict": "FAIL",
                        "raw_output": None,
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    }
                    with open(eval_path, "w", encoding="utf-8") as f:
                        json.dump(record, f, indent=2, ensure_ascii=False)
                    results["auto_fail_tool_use"] += 1
                    generated_this_run += 1
                    continue

            # ── Skip if quota exhausted ──
            if quota_exhausted:
                continue

            # ── Load candidate response ──
            resp_path = RESPONSES_DIR / f"{pid}_{model_slug}.json"
            with open(resp_path, "r", encoding="utf-8") as f:
                resp_data = json.load(f)
            response_text = resp_data.get("response_text", "")

            if not response_text:
                continue  # shouldn't happen for evaluable responses

            # Check if an unparseable record previously existed for this prompt
            prior_unparseable_record = None
            if eval_path.exists():
                try:
                    with open(eval_path, "r", encoding="utf-8") as f_prev:
                        prev_d = json.load(f_prev)
                    if prev_d.get("verdict") == "UNPARSEABLE":
                        prior_unparseable_record = prev_d
                        # Archive pristine original to data/audit/
                        audit_dir = DATA_DIR / "audit"
                        audit_dir.mkdir(parents=True, exist_ok=True)
                        audit_file = audit_dir / f"{pid}_{model_slug}_original_unparseable.json"
                        if not audit_file.exists():
                            with open(audit_file, "w", encoding="utf-8") as f_audit:
                                json.dump(prev_d, f_audit, indent=2, ensure_ascii=False)
                except Exception:
                    pass

            # ── Build evaluation prompt ──
            reference = ref_by_id[pid]
            eval_prompt = build_eval_prompt(cat, p["prompt_text"],
                                            response_text, reference)

            # ── Call Qwen ──
            qwen_result = call_qwen_eval(client, eval_prompt)

            if qwen_result["status"] == "quota_exhausted":
                quota_exhausted = True
                results["quota_exhausted"] = True
                retry_s = qwen_result.get("retry_after_seconds")
                print(f"\n[QUOTA] {QWEN_MODEL}: Genuine TPD quota exhausted "
                      f"at eval {idx}/{total_prompts} for {model_slug}.")
                if retry_s:
                    print(f"[QUOTA] Retry after: {retry_s:.0f}s ({retry_s/60:.1f}m)")
                print(f"[QUOTA] Generated {generated_this_run} evaluations "
                      f"this run for {model_slug}.")
                continue

            if qwen_result["status"] in ("error", "permanent_error"):
                results["errors"] += 1
                # Check if this prompt already had an ERROR record from a prior run
                prior_error_exists = False
                if eval_path.exists():
                    try:
                        with open(eval_path, "r", encoding="utf-8") as f_prev:
                            prev_v = json.load(f_prev).get("verdict")
                            if prev_v in ("ERROR", "EVALUATOR_ERROR"):
                                prior_error_exists = True
                    except Exception:
                        pass

                is_permanent = (qwen_result["status"] == "permanent_error") or prior_error_exists
                verdict = "EVALUATOR_ERROR" if is_permanent else "ERROR"

                record = {
                    "prompt_id": pid,
                    "category": cat,
                    "model": model_name,
                    "model_slug": model_slug,
                    "evaluator": QWEN_MODEL,
                    "verdict": verdict,
                    "error": qwen_result.get("error", ""),
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }
                with open(eval_path, "w", encoding="utf-8") as f:
                    json.dump(record, f, indent=2, ensure_ascii=False)
                if is_permanent:
                    print(f"    [TERMINAL] Prompt {pid[:12]}_{model_slug} classified as terminal EVALUATOR_ERROR: {qwen_result.get('error', '')[:80]}")
                continue

            # ── Parse verdict ──
            raw_output = qwen_result["raw_output"]
            verdict = parse_verdict(raw_output)

            # One controlled retry policy for UNPARSEABLE outcomes
            if verdict == "UNPARSEABLE":
                print(f"    [WARN] Unparseable output for {pid[:12]}_{model_slug}. Executing 1 controlled retry...")
                time.sleep(RPM_DELAY + 1.0)
                retry_result = call_qwen_eval(client, eval_prompt)
                if retry_result.get("status") == "success":
                    raw_output = retry_result["raw_output"]
                    verdict = parse_verdict(raw_output)
                    qwen_result = retry_result

            # If still unparseable after controlled retry, classify as terminal EVALUATOR_UNPARSEABLE
            if verdict == "UNPARSEABLE":
                verdict = "EVALUATOR_UNPARSEABLE"
                print(f"    [TERMINAL] Prompt {pid[:12]}_{model_slug} remains unparseable. Classified as EVALUATOR_UNPARSEABLE.")

            record = {
                "prompt_id": pid,
                "category": cat,
                "model": model_name,
                "model_slug": model_slug,
                "evaluator": QWEN_MODEL,
                "verdict": verdict,
                "raw_output": raw_output,
                "finish_reason": qwen_result.get("finish_reason", "unknown"),
                "prompt_tokens": qwen_result.get("prompt_tokens", 0),
                "completion_tokens": qwen_result.get("completion_tokens", 0),
                "total_tokens": qwen_result.get("total_tokens", 0),
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
            if prior_unparseable_record:
                record["controlled_retry_applied"] = True
                record["prior_unparseable_audit"] = {
                    "raw_output": prior_unparseable_record.get("raw_output"),
                    "finish_reason": prior_unparseable_record.get("finish_reason"),
                    "tokens": {
                        "prompt": prior_unparseable_record.get("prompt_tokens"),
                        "completion": prior_unparseable_record.get("completion_tokens"),
                        "total": prior_unparseable_record.get("total_tokens"),
                    },
                    "timestamp": prior_unparseable_record.get("timestamp"),
                }

            # Atomic write
            temp = eval_path.with_suffix(".tmp")
            with open(temp, "w", encoding="utf-8") as f:
                json.dump(record, f, indent=2, ensure_ascii=False)
            temp.replace(eval_path)

            results["qwen_calls"] += 1
            results["tokens"]["prompt"] += qwen_result.get("prompt_tokens", 0)
            results["tokens"]["completion"] += qwen_result.get("completion_tokens", 0)
            results["tokens"]["total"] += qwen_result.get("total_tokens", 0)
            generated_this_run += 1

            if generated_this_run % 10 == 0:
                elapsed = time.time() - t_start
                print(f"  [{model_slug}] Evaluated {generated_this_run} | "
                      f"Elapsed: {elapsed/60:.1f}m")

            time.sleep(RPM_DELAY)

        if not quota_exhausted:
            print(f"\n[DONE] {model_slug}: All evaluations processed. "
                  f"Generated {generated_this_run} this run.")

    # ── Final summary ──
    elapsed_total = time.time() - t_start

    # Recount from disk
    final = {"PASS": 0, "FAIL": 0, "ERROR": 0, "EVALUATOR_ERROR": 0, "EVALUATOR_UNPARSEABLE": 0, "UNPARSEABLE": 0, "missing": 0}
    by_model = {}
    by_cat_model = {}

    for model_name, model_slug in MODELS:
        mc = {"PASS": 0, "FAIL": 0, "ERROR": 0, "EVALUATOR_ERROR": 0, "EVALUATOR_UNPARSEABLE": 0, "UNPARSEABLE": 0,
              "auto_fail_empty": 0, "auto_fail_tool_use": 0, "candidate_degenerate": 0, "missing": 0}
        for p in prompts:
            pid = p["prompt_id"]
            cat = p["category"]
            eval_path = EVALS_DIR / f"{pid}_{model_slug}_eval.json"
            key = (cat, model_slug)
            if key not in by_cat_model:
                by_cat_model[key] = {"PASS": 0, "FAIL": 0, "ERROR": 0, "EVALUATOR_ERROR": 0,
                                      "EVALUATOR_UNPARSEABLE": 0, "UNPARSEABLE": 0, "missing": 0}

            if not eval_path.exists():
                mc["missing"] += 1
                final["missing"] += 1
                by_cat_model[key]["missing"] += 1
                continue

            with open(eval_path, "r", encoding="utf-8") as f:
                ed = json.load(f)
            v = ed.get("verdict", "missing")
            if ed.get("evaluator") in ("auto_terminal_failure", "candidate_degeneracy_audit") or ed.get("terminal_type"):
                tt = ed.get("terminal_type", "")
                if "empty" in tt:
                    mc["auto_fail_empty"] += 1
                elif "tool" in tt:
                    mc["auto_fail_tool_use"] += 1
                elif "DEGENERATE" in tt or "degenerate" in tt:
                    mc["candidate_degenerate"] += 1
                mc["FAIL"] += 1
                final["FAIL"] += 1
                by_cat_model[key]["FAIL"] += 1
            elif v in ("PASS", "FAIL"):
                mc[v] += 1
                final[v] += 1
                by_cat_model[key][v] += 1
            elif v == "EVALUATOR_UNPARSEABLE":
                mc["EVALUATOR_UNPARSEABLE"] += 1
                final["EVALUATOR_UNPARSEABLE"] += 1
                by_cat_model[key]["EVALUATOR_UNPARSEABLE"] += 1
            elif v == "EVALUATOR_ERROR":
                mc["EVALUATOR_ERROR"] += 1
                final["EVALUATOR_ERROR"] += 1
                by_cat_model[key]["EVALUATOR_ERROR"] += 1
            elif v == "ERROR":
                mc["ERROR"] += 1
                final["ERROR"] += 1
                by_cat_model[key]["ERROR"] += 1
            else:
                mc["UNPARSEABLE"] += 1
                final["UNPARSEABLE"] += 1
                by_cat_model[key]["UNPARSEABLE"] += 1

        by_model[model_slug] = mc

    # Save summary
    summary = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "evaluator": QWEN_MODEL,
        "temperature": QWEN_TEMP,
        "total_prompts": total_prompts,
        "elapsed_seconds": round(elapsed_total, 1),
        "qwen_calls_this_run": results["qwen_calls"],
        "auto_fail_empty": results["auto_fail_empty"],
        "auto_fail_tool_use": results["auto_fail_tool_use"],
        "skipped_from_cache": results["skipped"],
        "errors": results["errors"],
        "quota_exhausted": results["quota_exhausted"],
        "tokens": results["tokens"],
        "models": {},
    }
    for model_name, model_slug in MODELS:
        summary["models"][model_slug] = by_model[model_slug]

    with open(SUMMARY_FILE, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)

    # ── Print report ──
    print(f"\n{'=' * 70}")
    print("EVALUATION RUN COMPLETE")
    print(f"{'=' * 70}")

    for model_name, model_slug in MODELS:
        mc = by_model[model_slug]
        print(f"\n  {model_slug}:")
        print(f"    PASS:                   {mc['PASS']}")
        print(f"    FAIL:                   {mc['FAIL']}")
        if mc["auto_fail_empty"] > 0:
            print(f"      (auto-FAIL empty-text: {mc['auto_fail_empty']})")
        if mc["auto_fail_tool_use"] > 0:
            print(f"      (auto-FAIL tool-use:   {mc['auto_fail_tool_use']})")
        if mc.get("candidate_degenerate", 0) > 0:
            print(f"      (candidate-degenerate: {mc['candidate_degenerate']})")
        if mc.get("EVALUATOR_UNPARSEABLE", 0) > 0:
            print(f"    EVALUATOR_UNPARSEABLE:  {mc['EVALUATOR_UNPARSEABLE']}")
        if mc.get("EVALUATOR_ERROR", 0) > 0:
            print(f"    EVALUATOR_ERROR:        {mc['EVALUATOR_ERROR']}")
        if mc["ERROR"] > 0:
            print(f"    ERROR:                  {mc['ERROR']}")
        if mc["UNPARSEABLE"] > 0:
            print(f"    UNPARSEABLE:            {mc['UNPARSEABLE']}")
        print(f"    Missing:                {mc['missing']}")

    print(f"\n  Qwen API calls this run: {results['qwen_calls']}")
    print(f"  Auto-FAIL (empty-text):  {results['auto_fail_empty']}")
    print(f"  Auto-FAIL (tool-use):    {results['auto_fail_tool_use']}")
    print(f"  Skipped (cached):        {results['skipped']}")
    print(f"  Errors:                  {results['errors']}")
    print(f"  Tokens (p/c/t):          "
          f"{results['tokens']['prompt']} / "
          f"{results['tokens']['completion']} / "
          f"{results['tokens']['total']}")
    print(f"  Elapsed:                 {elapsed_total/60:.1f}m")
    print(f"\n  Summary saved to {SUMMARY_FILE}")


if __name__ == "__main__":
    main()
