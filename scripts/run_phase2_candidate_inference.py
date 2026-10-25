"""
Project 2 — Phase 2: Candidate Model Inference (500 Prompts x 2 Models)
========================================================================

Runs all 500 prompts through:
  1. Small model: openai/gpt-oss-20b
  2. Large model: openai/gpt-oss-120b

Configuration:
  - temperature = 0.0
  - max_tokens = 4096
  - tools = None

Features:
  - Strict SHA-256 provenance check on data/prompts.json
  - Robust checkpoint/resume (skips valid completed responses)
  - TPD-aware quota detection: parses retry-after from Groq 429 errors,
    does not repeatedly retry when token-per-day quota is exhausted
  - Processes models independently to maximize each model's daily quota
  - Invalid/incomplete responses (empty response_text) are identified
    and regenerated; original files are overwritten on retry
  - Comprehensive token metadata for published cost accounting
  - Crash-resilient atomic file writes (.tmp -> .replace)
"""

import os
import sys
import re
import time
import json
import hashlib
import winreg
from pathlib import Path
from datetime import datetime, timezone, timedelta

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
RESPONSES_DIR = DATA_DIR / "responses"
SUMMARY_FILE = DATA_DIR / "candidate_inference_summary.json"

FROZEN_PROMPTS_SHA256 = "a9214823cb8fdc0586f5fb2fb88ac29eeebbdf7d7b70da318be495eae8b8ce03"

# ── Frozen candidate-generation configuration ────────────────────────
MODELS = [
    ("openai/gpt-oss-20b", "openai_gpt-oss-20b", 0.075 / 1e6, 0.300 / 1e6),
    ("openai/gpt-oss-120b", "openai_gpt-oss-120b", 0.150 / 1e6, 0.600 / 1e6),
]

TEMPERATURE = 0.0
MAX_TOKENS = 4096
RPM_DELAY = 2.2  # Pacing between requests (seconds)
MAX_RETRIES = 5  # For non-TPD transient errors only
INITIAL_BACKOFF = 3.0


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
        raise RuntimeError("GROQ_API_KEY not found in environment or Windows registry.")
    return OpenAI(api_key=api_key, base_url="https://api.groq.com/openai/v1", timeout=60.0)


# ── Provenance ───────────────────────────────────────────────────────

def verify_prompts_file():
    if not PROMPTS_FILE.exists():
        raise FileNotFoundError(f"{PROMPTS_FILE} not found.")
    with open(PROMPTS_FILE, "rb") as f:
        actual_sha = hashlib.sha256(f.read()).hexdigest()
    if actual_sha != FROZEN_PROMPTS_SHA256:
        raise ValueError(f"PROMPTS_FILE SHA-256 mismatch! Expected {FROZEN_PROMPTS_SHA256}, got {actual_sha}")
    print(f"[OK] data/prompts.json verified (SHA-256: {actual_sha[:12]}...)")


# ── Response classification ──────────────────────────────────────────

def is_response_valid(file_path):
    """A response is valid only if status='success' AND response_text is non-empty.

    Files with status='success' but empty response_text are treated as
    invalid/incomplete: the API reported success and counted tokens, but
    no candidate answer was returned. These require regeneration because
    there is no candidate text available for evaluation.
    """
    if not file_path.exists():
        return False
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return (data.get("status") == "success" and
                data.get("response_text") is not None and
                len(data.get("response_text", "")) > 0)
    except Exception:
        return False


def classify_response_file(file_path):
    """Classify an existing response file for reporting.

    Returns one of:
      'valid'          – status=success, non-empty response_text
      'empty_success'  – status=success, but response_text is empty
                         (observed condition: API reported success with
                          completion_tokens>0 but returned no text)
      'error_429'      – status=error, 429/rate-limit error
      'error_other'    – status=error, non-429 error
      'corrupt'        – file exists but is not valid JSON
      'missing'        – file does not exist
    """
    if not file_path.exists():
        return "missing"
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        status = data.get("status", "")
        resp_text = data.get("response_text", "")
        error_msg = data.get("error", "") or ""

        if status == "success" and resp_text and len(resp_text) > 0:
            return "valid"
        elif status == "success" and (not resp_text or len(resp_text) == 0):
            return "empty_success"
        elif status == "error":
            if "rate_limit" in error_msg.lower() or "429" in error_msg:
                return "error_429"
            return "error_other"
        else:
            return "error_other"
    except Exception:
        return "corrupt"

# ── Terminal failure classification ──────────────────────────────────

def is_terminal_failure(file_path):
    """Check if a response file represents a terminal (non-retryable) outcome.

    The candidate-generation study measures single-shot model behavior under
    the frozen configuration (T=0, max_tokens=4096, tools=None).  Retrying
    already-observed failures would give the model additional opportunities
    beyond a single generation attempt.

    Terminal outcomes:
      1. Empty-text generation condition — observed condition where the API
         reported status='success' with completion_tokens>0 but returned
         empty response_text.  No usable candidate content exists.
      2. Prompt-format-induced API rejection — the prompt contains explicit
         ReAct/tool-use instructions, and the model attempted a structured
         tool call under tools=None, producing a deterministic 400 error.

    Returns True if the file exists and matches either terminal condition.
    """
    if not file_path.exists():
        return False
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        status = data.get("status", "")
        resp_text = data.get("response_text", "")
        error_msg = data.get("error", "") or ""

        # Empty-text generation condition
        if (status == "success" and
                (not resp_text or len(resp_text) == 0) and
                data.get("completion_tokens", 0) > 0):
            return True

        # Prompt-format-induced API rejection (tool-use 400)
        if (status == "error" and
                "tool choice is none" in error_msg.lower()):
            return True

        return False
    except Exception:
        return False


# ── TPD-aware quota detection ────────────────────────────────────────

def parse_retry_after_seconds(error_str):
    """Parse retry-after duration from a Groq 429 error message.

    Looks for patterns like "Please try again in 19m35.472s" or "in 1h2m3.4s".
    Returns seconds as float, or None if not parseable.
    """
    match = re.search(
        r'try again in\s+(?:(\d+)h)?(?:(\d+)m)?(?:([\d.]+)s)?',
        error_str, re.IGNORECASE
    )
    if not match:
        return None
    hours = int(match.group(1) or 0)
    minutes = int(match.group(2) or 0)
    seconds = float(match.group(3) or 0)
    total = hours * 3600 + minutes * 60 + seconds
    return total if total > 0 else None


def is_tpd_exhaustion(error_str):
    """Detect whether a 429 error indicates tokens-per-day quota exhaustion.

    Groq TPD errors contain identifying phrases such as
    "tokens per day (TPD)" and/or "Limit 200000".
    """
    lower = error_str.lower()
    return ('tokens per day' in lower or 'limit 200000' in lower)


# ── API call with TPD-aware retry ────────────────────────────────────

def call_groq_with_retry(client, model_id, prompt_text):
    """Call the Groq API with TPD-aware retry logic.

    - On TPD exhaustion (429 with tokens-per-day signal): returns
      immediately with status='quota_exhausted'. Does NOT retry.
    - On transient errors (timeout, 5xx, non-TPD 429): retries up to
      MAX_RETRIES times with exponential backoff.
    """
    backoff = INITIAL_BACKOFF
    retries = 0
    start_time = time.time()

    for attempt in range(MAX_RETRIES):
        try:
            t0 = time.time()
            response = client.chat.completions.create(
                model=model_id,
                messages=[{"role": "user", "content": prompt_text}],
                temperature=TEMPERATURE,
                max_tokens=MAX_TOKENS,
            )
            latency_ms = int((time.time() - t0) * 1000)
            choice = response.choices[0]
            usage = response.usage

            p_tok = usage.prompt_tokens if usage else 0
            c_tok = usage.completion_tokens if usage else 0
            tot_tok = usage.total_tokens if usage else (p_tok + c_tok)

            return {
                "status": "success",
                "response_text": choice.message.content or "",
                "finish_reason": choice.finish_reason,
                "prompt_tokens": p_tok,
                "completion_tokens": c_tok,
                "total_tokens": tot_tok,
                "latency_ms": latency_ms,
                "retries": retries,
                "error": None,
                "quota_exhausted": False,
                "retry_after_seconds": None,
            }
        except Exception as e:
            err_str = str(e)

            # ── TPD exhaustion: do NOT retry ──
            if is_tpd_exhaustion(err_str):
                retry_after = parse_retry_after_seconds(err_str)
                print(f"    [QUOTA] TPD exhaustion detected for {model_id}.")
                if retry_after:
                    print(f"    [QUOTA] Retry after: {retry_after:.0f}s "
                          f"({retry_after / 60:.1f}m)")
                return {
                    "status": "quota_exhausted",
                    "response_text": "",
                    "finish_reason": "quota_exhausted",
                    "prompt_tokens": 0,
                    "completion_tokens": 0,
                    "total_tokens": 0,
                    "latency_ms": int((time.time() - start_time) * 1000),
                    "retries": retries,
                    "error": err_str,
                    "quota_exhausted": True,
                    "retry_after_seconds": retry_after,
                }

            # ── Transient error: retry with backoff ──
            retries += 1
            print(f"    [WARN] Attempt {attempt+1}/{MAX_RETRIES} failed "
                  f"for {model_id}: {err_str[:120]}")
            if attempt == MAX_RETRIES - 1:
                return {
                    "status": "error",
                    "response_text": "",
                    "finish_reason": "error",
                    "prompt_tokens": 0,
                    "completion_tokens": 0,
                    "total_tokens": 0,
                    "latency_ms": int((time.time() - start_time) * 1000),
                    "retries": retries,
                    "error": err_str,
                    "quota_exhausted": False,
                    "retry_after_seconds": None,
                }
            time.sleep(backoff)
            backoff *= 2.0


# ── Startup resume report ────────────────────────────────────────────

def print_startup_report(prompts):
    """Print detailed resume report at startup."""
    print(f"\n{'=' * 60}")
    print("STARTUP RESUME REPORT")
    print(f"{'=' * 60}")

    all_pids = [p["prompt_id"] for p in prompts]
    total_remaining = 0

    for _, slug, _, _ in MODELS:
        counts = {
            "valid": 0, "empty_success": 0,
            "error_429": 0, "error_other": 0,
            "corrupt": 0, "missing": 0,
        }
        terminal_empty = 0
        terminal_tool_use = 0
        for pid in all_pids:
            fpath = RESPONSES_DIR / f"{pid}_{slug}.json"
            cls = classify_response_file(fpath)
            counts[cls] += 1
            # Count terminal sub-types
            if cls == "empty_success" and is_terminal_failure(fpath):
                terminal_empty += 1
            elif cls == "error_other" and is_terminal_failure(fpath):
                terminal_tool_use += 1

        # Terminal failures are NOT remaining tasks
        terminal_total = terminal_empty + terminal_tool_use
        remaining = (counts["empty_success"] - terminal_empty +
                     counts["error_429"] +
                     counts["error_other"] - terminal_tool_use +
                     counts["corrupt"] +
                     counts["missing"])
        total_remaining += remaining

        print(f"\n  {slug}:")
        print(f"    Valid successful responses:            {counts['valid']}  (skipped)")
        if terminal_empty > 0:
            print(f"    Terminal: empty-text generation:       "
                  f"{terminal_empty}  (skipped, not retried)")
        if terminal_tool_use > 0:
            print(f"    Terminal: tool-use API rejection:      "
                  f"{terminal_tool_use}  (skipped, not retried)")
        non_terminal_empty = counts["empty_success"] - terminal_empty
        if non_terminal_empty > 0:
            print(f"    Invalid/incomplete (empty response):   {non_terminal_empty}")
        if counts["error_429"] > 0:
            print(f"    Error responses (429/rate-limit):      {counts['error_429']}")
        non_terminal_error = counts["error_other"] - terminal_tool_use
        if non_terminal_error > 0:
            print(f"    Error responses (other):               {non_terminal_error}")
        if counts["corrupt"] > 0:
            print(f"    Corrupt files:                         {counts['corrupt']}")
        print(f"    Missing (eligible for generation):     {counts['missing']}")
        print(f"    ── Remaining tasks:                    {remaining}")

    print(f"\n  Total remaining tasks (all models):        {total_remaining}")
    print(f"{'=' * 60}\n")


# ── Main ─────────────────────────────────────────────────────────────

def main():
    print("=" * 70)
    print("PROJECT 2 — PHASE 2: CANDIDATE MODEL INFERENCE")
    print("=" * 70)

    verify_prompts_file()
    client = get_groq_client()
    RESPONSES_DIR.mkdir(parents=True, exist_ok=True)

    with open(PROMPTS_FILE, "r", encoding="utf-8") as f:
        payload = json.load(f)
    prompts = payload["prompts"]
    total_prompts = len(prompts)
    print(f"Loaded {total_prompts} prompts.")

    # ── Deterministic round-robin execution order ──
    # Interleave categories so that each quota window processes
    # prompts evenly across all four categories, rather than
    # exhausting quota on early categories and starving later ones.
    # Within each category, the original file order is preserved.
    # This changes ONLY the API-call iteration order, not the
    # prompt contents, IDs, categories, router scores, or any
    # frozen experimental artifact.
    ROUND_ROBIN_CATEGORIES = [
        "factual_qa", "summarization", "reasoning_math", "creative"
    ]
    by_cat = {c: [] for c in ROUND_ROBIN_CATEGORIES}
    for p in prompts:
        by_cat[p["category"]].append(p)
    rr_prompts = []
    prompts_per_cat = 125
    for i in range(prompts_per_cat):
        for cat in ROUND_ROBIN_CATEGORIES:
            rr_prompts.append(by_cat[cat][i])
    assert len(rr_prompts) == total_prompts, (
        f"Round-robin prompt count mismatch: {len(rr_prompts)} != {total_prompts}"
    )
    assert set(p["prompt_id"] for p in rr_prompts) == set(
        p["prompt_id"] for p in prompts
    ), "Round-robin prompt IDs do not match original set"
    print(f"[OK] Round-robin ordering built: {len(rr_prompts)} prompts, "
          f"{len(ROUND_ROBIN_CATEGORIES)} categories interleaved.")

    print_startup_report(prompts)

    # ── Per-model tracking ──
    results = {}
    for _, slug, _, _ in MODELS:
        results[slug] = {
            "completed": 0,
            "skipped": 0,
            "terminal_skipped": 0,
            "errors_429": 0,
            "errors_other": 0,
            "quota_exhausted": False,
            "quota_exhausted_at_prompt_idx": None,
            "retry_after_seconds": None,
            "tokens": {"prompt": 0, "completion": 0, "total": 0},
        }

    t_start = time.time()

    # ── Process models independently ──
    # Each model has an independent 200K TPD budget.
    # Processing one model at a time allows the other model's budget
    # to be used in full even if one exhausts mid-run.
    # Prompts are iterated in deterministic round-robin order across
    # the four categories to distribute quota evenly.
    for model_id, model_slug, p_rate, c_rate in MODELS:
        print(f"\n{'=' * 60}")
        print(f"Processing model: {model_id}")
        print(f"{'=' * 60}")

        generated_this_run = 0

        for idx, p in enumerate(rr_prompts, start=1):
            qid = p["prompt_id"]
            cat = p["category"]
            text = p["prompt_text"]
            out_file = RESPONSES_DIR / f"{qid}_{model_slug}.json"

            # ── Checkpoint resume: skip valid responses ──
            if is_response_valid(out_file):
                with open(out_file, "r", encoding="utf-8") as f:
                    cached = json.load(f)
                results[model_slug]["skipped"] += 1
                results[model_slug]["completed"] += 1
                results[model_slug]["tokens"]["prompt"] += cached.get("prompt_tokens", 0)
                results[model_slug]["tokens"]["completion"] += cached.get("completion_tokens", 0)
                results[model_slug]["tokens"]["total"] += cached.get("total_tokens", 0)
                continue

            # ── Terminal failures: do not retry ──
            # Observed non-usable outcomes under the frozen inference
            # configuration.  Retrying would give the model additional
            # opportunities beyond a single generation attempt.
            if is_terminal_failure(out_file):
                results[model_slug]["terminal_skipped"] += 1
                continue

            # ── If quota already exhausted for this model, skip ──
            if results[model_slug]["quota_exhausted"]:
                continue

            # ── Perform inference ──
            res = call_groq_with_retry(client, model_id, text)

            # ── Handle quota exhaustion ──
            if res.get("quota_exhausted"):
                results[model_slug]["quota_exhausted"] = True
                results[model_slug]["quota_exhausted_at_prompt_idx"] = idx
                results[model_slug]["retry_after_seconds"] = res.get("retry_after_seconds")
                retry_s = res.get("retry_after_seconds")
                print(f"\n[QUOTA] {model_slug}: TPD quota exhausted "
                      f"at prompt {idx}/{total_prompts}.")
                if retry_s:
                    resume_time = datetime.now(timezone.utc) + timedelta(seconds=retry_s)
                    print(f"[QUOTA] Retry after: {retry_s:.0f}s "
                          f"(~{resume_time.strftime('%Y-%m-%d %H:%M UTC')})")
                print(f"[QUOTA] Generated {generated_this_run} new responses "
                      f"this run for {model_slug}.")
                print(f"[QUOTA] Skipping remaining prompts for {model_slug}. "
                      f"Moving to next model.\n")
                continue

            # ── Write response atomically ──
            record = {
                "prompt_id": qid,
                "category": cat,
                "model": model_id,
                "model_slug": model_slug,
                "temperature": TEMPERATURE,
                "max_tokens": MAX_TOKENS,
                "tools": None,
                "prompt_text": text,
                "response_text": res["response_text"],
                "finish_reason": res["finish_reason"],
                "prompt_tokens": res["prompt_tokens"],
                "completion_tokens": res["completion_tokens"],
                "total_tokens": res["total_tokens"],
                "latency_ms": res["latency_ms"],
                "retries": res["retries"],
                "status": res["status"],
                "error": res["error"],
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }

            temp_file = out_file.with_suffix(".tmp")
            with open(temp_file, "w", encoding="utf-8") as f:
                json.dump(record, f, indent=2, ensure_ascii=False)
            temp_file.replace(out_file)

            if res["status"] == "success":
                results[model_slug]["completed"] += 1
                results[model_slug]["tokens"]["prompt"] += res["prompt_tokens"]
                results[model_slug]["tokens"]["completion"] += res["completion_tokens"]
                results[model_slug]["tokens"]["total"] += res["total_tokens"]
                generated_this_run += 1
            else:
                results[model_slug]["errors_other"] += 1

            # ── Progress reporting ──
            if generated_this_run % 10 == 0 and generated_this_run > 0:
                elapsed = time.time() - t_start
                print(f"  [{model_slug}] Generated {generated_this_run} new | "
                      f"Total complete: {results[model_slug]['completed']}"
                      f"/{total_prompts} | Elapsed: {elapsed / 60:.1f}m")

            time.sleep(RPM_DELAY)

        if not results[model_slug]["quota_exhausted"]:
            print(f"\n[DONE] {model_slug}: All prompts processed. "
                  f"Generated {generated_this_run} new responses this run.")

    # ── Final summary ──
    elapsed_total = time.time() - t_start

    # Recount from disk for accurate final tally
    final_counts = {}
    for _, slug, _, _ in MODELS:
        fc = {"valid": 0, "empty_success": 0, "error_429": 0,
              "error_other": 0, "corrupt": 0, "missing": 0}
        for p in prompts:
            fpath = RESPONSES_DIR / f"{p['prompt_id']}_{slug}.json"
            fc[classify_response_file(fpath)] += 1
        final_counts[slug] = fc

    summary = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "total_prompts": total_prompts,
        "prompts_sha256": FROZEN_PROMPTS_SHA256,
        "elapsed_seconds": round(elapsed_total, 1),
        "models": {},
    }

    for model_id, slug, p_rate, c_rate in MODELS:
        cost = (results[slug]["tokens"]["prompt"] * p_rate +
                results[slug]["tokens"]["completion"] * c_rate)

        # Count terminal sub-types from disk
        terminal_empty = 0
        terminal_tool_use = 0
        for p in prompts:
            fpath = RESPONSES_DIR / f"{p['prompt_id']}_{slug}.json"
            cls = classify_response_file(fpath)
            if cls == "empty_success" and is_terminal_failure(fpath):
                terminal_empty += 1
            elif cls == "error_other" and is_terminal_failure(fpath):
                terminal_tool_use += 1

        # Remaining tasks exclude terminal failures
        remaining = (final_counts[slug]["empty_success"] - terminal_empty +
                     final_counts[slug]["error_429"] +
                     final_counts[slug]["error_other"] - terminal_tool_use +
                     final_counts[slug]["corrupt"] +
                     final_counts[slug]["missing"])

        summary["models"][model_id] = {
            "successful_responses": final_counts[slug]["valid"],
            "terminal_empty_text": terminal_empty,
            "terminal_tool_use_400": terminal_tool_use,
            "invalid_incomplete_responses": final_counts[slug]["empty_success"] - terminal_empty,
            "error_429_responses": final_counts[slug]["error_429"],
            "error_other_responses": final_counts[slug]["error_other"] - terminal_tool_use,
            "missing_responses": final_counts[slug]["missing"],
            "remaining_tasks": remaining,
            "skipped_from_cache": results[slug]["skipped"],
            "terminal_skipped_this_run": results[slug]["terminal_skipped"],
            "quota_exhausted": results[slug]["quota_exhausted"],
            "quota_exhausted_at_prompt_idx": results[slug]["quota_exhausted_at_prompt_idx"],
            "retry_after_seconds": results[slug]["retry_after_seconds"],
            "tokens": results[slug]["tokens"],
            "published_accounting_cost_usd": round(cost, 6),
            "actual_marginal_expenditure_usd": 0.0,
        }

    total_cost = sum(
        summary["models"][mid]["published_accounting_cost_usd"]
        for mid, _, _, _ in MODELS
    )
    summary["total_published_accounting_cost_usd"] = round(total_cost, 6)
    summary["total_actual_marginal_expenditure_usd"] = 0.0

    with open(SUMMARY_FILE, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)

    # ── Print final report ──
    print(f"\n{'=' * 70}")
    print("INFERENCE RUN COMPLETE")
    print(f"{'=' * 70}")
    for model_id, slug, _, _ in MODELS:
        ms = summary["models"][model_id]
        print(f"\n  {slug}:")
        print(f"    Successful responses:         {ms['successful_responses']}")
        print(f"    Terminal: empty-text:          {ms['terminal_empty_text']}")
        print(f"    Terminal: tool-use 400:        {ms['terminal_tool_use_400']}")
        print(f"    Terminal skipped this run:     {ms['terminal_skipped_this_run']}")
        if ms["invalid_incomplete_responses"] > 0:
            print(f"    Invalid/incomplete:            {ms['invalid_incomplete_responses']}")
        if ms["error_429_responses"] > 0:
            print(f"    Error (429/rate-limit):        {ms['error_429_responses']}")
        if ms["error_other_responses"] > 0:
            print(f"    Error (other):                 {ms['error_other_responses']}")
        print(f"    Missing:                       {ms['missing_responses']}")
        print(f"    Remaining tasks:               {ms['remaining_tasks']}")
        print(f"    Tokens (prompt/compl/total):   "
              f"{ms['tokens']['prompt']} / {ms['tokens']['completion']} "
              f"/ {ms['tokens']['total']}")
        print(f"    Published accounting cost:     ${ms['published_accounting_cost_usd']:.6f}")
        print(f"    Actual marginal expenditure:   ${ms['actual_marginal_expenditure_usd']:.2f}")
        if ms["quota_exhausted"]:
            print(f"    Quota exhausted at prompt:     #{ms['quota_exhausted_at_prompt_idx']}")

    print(f"\n  Total published accounting cost:   "
          f"${summary['total_published_accounting_cost_usd']:.6f}")
    print(f"  Total actual marginal expenditure: "
          f"${summary['total_actual_marginal_expenditure_usd']:.2f}")
    print(f"  Elapsed time:                      {elapsed_total / 60:.1f}m")
    print(f"\n  Summary saved to {SUMMARY_FILE}")


if __name__ == "__main__":
    main()
