"""
Project 2 — Pilot Phase 2: Dual-Model Inference
================================================

Runs the researcher-reviewed 40-prompt selection through both candidate
models, saves structured results with caching/resume support, and
generates a concise pilot report.

This is a feasibility/capability-gap pilot, NOT a statistically
representative experiment. No quality claims are made.

Models:
  Small: openai/gpt-oss-20b via Groq
  Large: openai/gpt-oss-120b via Groq

Prerequisites:
  1. prompts.json exists with exactly 40 prompts (10 per category).
  2. GROQ_API_KEY environment variable is configured.

Deterministic settings:
  temperature: 0.0
  max_tokens:  4096
"""

import json
import os
import sys
import time

# Ensure UTF-8 output on Windows consoles
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

import winreg
from pathlib import Path
from datetime import datetime, timezone
from collections import Counter
from openai import OpenAI

# ---------------------------------------------------------------------------
# CONFIGURATION
# ---------------------------------------------------------------------------

PROJECT_DIR = Path(__file__).parent
DATA_DIR = PROJECT_DIR / "pilot_data"
RESPONSES_DIR = DATA_DIR / "responses"
PROMPTS_FILE = DATA_DIR / "prompts.json"
REPORT_FILE = DATA_DIR / "pilot_report.md"
SUMMARY_FILE = DATA_DIR / "pilot_run_summary.json"

SMALL_MODEL = "openai/gpt-oss-20b"
SMALL_PROVIDER = "groq"
SMALL_BASE_URL = "https://api.groq.com/openai/v1"

LARGE_MODEL = "openai/gpt-oss-120b"
LARGE_PROVIDER = "groq"
LARGE_BASE_URL = "https://api.groq.com/openai/v1"

CATEGORIES = ["factual_qa", "summarization", "reasoning_math", "creative"]

MAX_RESPONSE_TOKENS = 4096
TEMPERATURE = 0.0
RPM_DELAY_GROQ = 2.5        # seconds between Groq calls
RPM_DELAY_LARGE = 2.5       # seconds between large model Groq calls
MAX_RETRIES = 3
INITIAL_RETRY_BACKOFF = 4.0


# ---------------------------------------------------------------------------
# ENVIRONMENT VERIFICATION
# ---------------------------------------------------------------------------

def get_env_var(name: str):
    """Retrieve environment variable from os.environ or Windows user registry."""
    val = os.environ.get(name)
    if val:
        return val
    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Environment")
        val, _ = winreg.QueryValueEx(key, name)
        winreg.CloseKey(key)
        return val
    except Exception:
        return None


def verify_environment():
    """Check required environment variables without exposing values."""
    required = {
        "GROQ_API_KEY": "Groq API access (both models: openai/gpt-oss-20b and openai/gpt-oss-120b)",
    }
    missing = []
    keys = {}
    for var, purpose in required.items():
        val = get_env_var(var)
        if not val:
            missing.append(f"  {var} - needed for: {purpose}")
        else:
            keys[var] = val

    if missing:
        print("ERROR: Missing required environment variables:")
        for m in missing:
            print(m)
        print('\nSet them with: setx VARIABLE_NAME "your-key"')
        print("Then restart your terminal and re-run.")
        sys.exit(1)

    print("[OK] All required environment variables are set and verified.")
    return {
        "groq_key": keys["GROQ_API_KEY"],
    }


# ---------------------------------------------------------------------------
# PRE-FLIGHT CHECK: LOAD & VALIDATE PROMPTS
# ---------------------------------------------------------------------------

def load_and_validate_prompts():
    """
    Load prompts.json and verify:
    - exactly 40 prompts total
    - exactly 10 prompts per category across all 4 categories
    - required fields present
    If not, STOP and report the problem.
    """
    if not PROMPTS_FILE.exists():
        print(f"ERROR: {PROMPTS_FILE} not found. STOPPING.")
        sys.exit(1)

    with open(PROMPTS_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)

    if isinstance(data, dict) and "prompts" in data:
        prompts = data["prompts"]
    elif isinstance(data, list):
        prompts = data
    else:
        print("ERROR: Unexpected prompts.json format. STOPPING.")
        sys.exit(1)

    # Verify total count
    if len(prompts) != 40:
        print(f"ERROR: prompts.json contains {len(prompts)} prompts, expected exactly 40. STOPPING.")
        sys.exit(1)

    # Verify category counts
    cat_counts = Counter(p.get("category") for p in prompts)
    for cat in CATEGORIES:
        count = cat_counts.get(cat, 0)
        if count != 10:
            print(f"ERROR: Category '{cat}' has {count} prompts, expected exactly 10. STOPPING.")
            sys.exit(1)

    # Verify required fields
    for p in prompts:
        if "prompt_id" not in p or "category" not in p or "prompt_text" not in p:
            print(f"ERROR: Prompt missing required fields (prompt_id/category/prompt_text): {p.get('prompt_id', '?')}. STOPPING.")
            sys.exit(1)

    print(f"[OK] Pre-flight verification passed: exactly 40 prompts, 10 per category across {CATEGORIES}.")
    return prompts


# ---------------------------------------------------------------------------
# INFERENCE HELPERS
# ---------------------------------------------------------------------------

def response_cache_path(prompt_id: str, model: str) -> Path:
    """Path to cached response file."""
    safe_model = model.replace("/", "_").replace(":", "_")
    return RESPONSES_DIR / f"{prompt_id}_{safe_model}.json"


def run_inference_single(client: OpenAI, model: str, provider: str, prompt_text: str,
                         prompt_id: str, category: str, delay: float):
    """
    Run a single prompt through a model, with retry logic and caching/resume.
    Returns: (result_dict, was_cached)
    """
    cache_path = response_cache_path(prompt_id, model)

    # Check cache: only accept if cached entry was successful (no error)
    if cache_path.exists():
        try:
            with open(cache_path, "r", encoding="utf-8") as f:
                cached = json.load(f)
            if not cached.get("error") and cached.get("raw_response") is not None:
                return cached, True
        except Exception:
            pass  # Re-run if cache corrupted

    time.sleep(delay)
    
    error_msg = None
    response_text = ""
    reasoning_text = None
    input_tokens = 0
    output_tokens = 0
    total_tokens = 0
    reasoning_tokens = 0
    model_returned = ""
    elapsed = 0.0
    retries_done = 0

    for attempt in range(MAX_RETRIES):
        start_time = time.time()
        try:
            response = client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": prompt_text}],
                temperature=TEMPERATURE,
                max_tokens=MAX_RESPONSE_TOKENS,
            )
            elapsed = time.time() - start_time
            choice = response.choices[0]
            response_text = choice.message.content or ""
            reasoning_text = getattr(choice.message, "reasoning", None)
            model_returned = response.model or model
            
            usage = response.usage
            if usage:
                input_tokens = getattr(usage, "prompt_tokens", 0) or 0
                output_tokens = getattr(usage, "completion_tokens", 0) or 0
                total_tokens = getattr(usage, "total_tokens", 0) or (input_tokens + output_tokens)
                details = getattr(usage, "completion_tokens_details", None)
                if details:
                    reasoning_tokens = getattr(details, "reasoning_tokens", 0) or 0

            error_msg = None
            break  # Success
        except Exception as e:
            elapsed = time.time() - start_time
            error_msg = str(e)
            retries_done = attempt + 1
            if attempt < MAX_RETRIES - 1:
                backoff = INITIAL_RETRY_BACKOFF * (attempt + 1)
                print(f"      [Retry {attempt+1}/{MAX_RETRIES-1}] Error: {error_msg[:80]} - Waiting {backoff}s...")
                time.sleep(backoff)

    result = {
        "prompt_id": prompt_id,
        "category": category,
        "prompt_text": prompt_text,
        "model": model,
        "provider": provider,
        "model_returned": model_returned,
        "raw_response": response_text,
        "response_text": response_text,
        "reasoning_text": reasoning_text,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "total_tokens": total_tokens,
        "reasoning_tokens": reasoning_tokens,
        "latency_seconds": round(elapsed, 3),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "temperature": TEMPERATURE,
        "max_tokens": MAX_RESPONSE_TOKENS,
        "retries": retries_done,
        "error": error_msg,
    }

    RESPONSES_DIR.mkdir(parents=True, exist_ok=True)
    with open(cache_path, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)

    return result, False


# ---------------------------------------------------------------------------
# DUAL MODEL INFERENCE ORCHESTRATION
# ---------------------------------------------------------------------------

def run_all_inference(prompts, small_client, large_client):
    """Run all 40 prompts through both candidate models."""
    print(f"\n--- Running inference: {len(prompts)} prompts x 2 models ---")

    models_config = [
        ("small", SMALL_MODEL, SMALL_PROVIDER, small_client, RPM_DELAY_GROQ),
        ("large", LARGE_MODEL, LARGE_PROVIDER, large_client, RPM_DELAY_LARGE),
    ]

    results_by_model = {"small": [], "large": []}
    total = len(prompts)

    for role, model, provider, client, delay in models_config:
        print(f"\n  [{role.upper()}] {model} via {provider}")
        cached = 0
        fresh = 0
        errors = 0

        for i, p in enumerate(prompts):
            result, was_cached = run_inference_single(
                client=client,
                model=model,
                provider=provider,
                prompt_text=p["prompt_text"],
                prompt_id=p["prompt_id"],
                category=p["category"],
                delay=delay,
            )
            result["role"] = role
            results_by_model[role].append(result)

            if was_cached:
                cached += 1
                snippet = result["response_text"][:50].replace("\n", " ").encode('ascii', errors='replace').decode('ascii')
                print(f"    [{i+1:2d}/{total}] (cached) OK ({result['latency_seconds']:.2f}s, {result['output_tokens']} tok) \"{snippet}...\"")
            else:
                fresh += 1
                if result["error"]:
                    errors += 1
                    print(f"    [{i+1:2d}/{total}] ERROR: {result['error'][:100]}")
                else:
                    snippet = result["response_text"][:50].replace("\n", " ").encode('ascii', errors='replace').decode('ascii')
                    print(f"    [{i+1:2d}/{total}] OK ({result['latency_seconds']:.2f}s, {result['output_tokens']} tok) \"{snippet}...\"")

        print(f"  Completed [{role.upper()}]: {fresh} fresh calls, {cached} cached, {errors} errors")

    return results_by_model


# ---------------------------------------------------------------------------
# POST-RUN VERIFICATION & STORAGE
# ---------------------------------------------------------------------------

def post_run_verification_and_storage(prompts, results_by_model):
    """
    Verify:
    - each model has exactly 40 response records
    - all 40 prompt_ids match between small and large models and match prompts.json
    Saves consolidated files in pilot_data/responses/
    """
    print("\n--- Post-run Verification & Storage ---")
    small_results = results_by_model["small"]
    large_results = results_by_model["large"]

    if len(small_results) != 40:
        raise ValueError(f"Small model has {len(small_results)} responses, expected 40.")
    if len(large_results) != 40:
        raise ValueError(f"Large model has {len(large_results)} responses, expected 40.")

    expected_ids = [p["prompt_id"] for p in prompts]
    small_ids = [r["prompt_id"] for r in small_results]
    large_ids = [r["prompt_id"] for r in large_results]

    if small_ids != expected_ids:
        raise ValueError("Small model prompt_ids do not match expected prompts.json order!")
    if large_ids != expected_ids:
        raise ValueError("Large model prompt_ids do not match expected prompts.json order!")
    if small_ids != large_ids:
        raise ValueError("Prompt ID mismatch between small and large model responses!")

    print("[OK] Verification passed: exactly 40 responses per model, prompt_ids 100% matched in exact order.")

    # Save consolidated files
    small_file = RESPONSES_DIR / "groq_gpt_oss_20b.json"
    with open(small_file, "w", encoding="utf-8") as f:
        json.dump(small_results, f, indent=2, ensure_ascii=False)

    large_file = RESPONSES_DIR / "openrouter_nemotron_3_ultra.json"
    with open(large_file, "w", encoding="utf-8") as f:
        json.dump(large_results, f, indent=2, ensure_ascii=False)

    all_file = RESPONSES_DIR / "all_responses.json"
    with open(all_file, "w", encoding="utf-8") as f:
        json.dump(small_results + large_results, f, indent=2, ensure_ascii=False)

    print(f"Saved consolidated responses:")
    print(f"  - Small model: {small_file}")
    print(f"  - Large model: {large_file}")
    print(f"  - Combined:    {all_file}")


# ---------------------------------------------------------------------------
# SUMMARY AND REPORT GENERATION
# ---------------------------------------------------------------------------

def calculate_stats(values):
    """Compute min, median, mean, max for a numeric list."""
    if not values:
        return {"min": 0, "median": 0, "mean": 0, "max": 0}
    vals = sorted(values)
    n = len(vals)
    med = vals[n // 2] if n % 2 else (vals[n // 2 - 1] + vals[n // 2]) / 2.0
    mean = sum(vals) / float(n)
    return {
        "min": round(vals[0], 2),
        "median": round(med, 2),
        "mean": round(mean, 2),
        "max": round(vals[-1], 2),
    }


def generate_pilot_summary_and_report(prompts, results_by_model):
    """
    Produce pilot_run_summary.json and pilot_report.md.
    Compute token totals/averages, latency, response length, category breakdown,
    and document anomalies without performing quality scoring.
    """
    summary_data = {
        "metadata": {
            "title": "Project 2 - 40-Prompt Model-Selection Pilot Run Summary",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "deterministic_settings": {
                "temperature": TEMPERATURE,
                "max_tokens": MAX_RESPONSE_TOKENS,
            },
            "rate_limits": {
                "groq_delay_seconds": RPM_DELAY_GROQ,
                "openrouter_delay_seconds": RPM_DELAY_OPENROUTER,
            },
            "prompt_count": len(prompts),
            "categories": CATEGORIES,
            "verification_status": "All 40 prompt IDs verified identical across both models",
        },
        "models": {},
    }

    report_lines = [
        "# Project 2 - 40-Prompt Model-Selection Pilot Report",
        "",
        f"**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        "",
        "> **Methodological Boundary:** This is a feasibility and capability-gap pilot for 40 researcher-reviewed",
        "> candidate prompts (10 per category). It is NOT a statistically representative sample of LMSYS Chatbot Arena,",
        "> and no quality scoring or routing claims are made.",
        "",
        "## 1. Experimental Configuration",
        f"- **Small Model:** `{SMALL_MODEL}` via `{SMALL_PROVIDER}`",
        f"- **Large Candidate:** `{LARGE_MODEL}` via `{LARGE_PROVIDER}`",
        f"- **Temperature:** `{TEMPERATURE}` (deterministic)",
        f"- **Max Output Tokens:** `{MAX_RESPONSE_TOKENS}`",
        f"- **Rate Delays:** Groq: {RPM_DELAY_GROQ}s/call | OpenRouter: {RPM_DELAY_OPENROUTER}s/call",
        "",
        "## 2. Category Distribution",
        "| Category | Prompt Count |",
        "|---|---|",
    ]

    for cat in CATEGORIES:
        count = sum(1 for p in prompts if p["category"] == cat)
        report_lines.append(f"| `{cat}` | {count} |")

    # Metrics computation
    for role, model_name, provider in [
        ("small", SMALL_MODEL, SMALL_PROVIDER),
        ("large", LARGE_MODEL, LARGE_PROVIDER),
    ]:
        results = results_by_model[role]
        successes = [r for r in results if not r["error"]]
        errors = [r for r in results if r["error"]]
        retries = sum(r["retries"] for r in results)

        latencies = [r["latency_seconds"] for r in successes]
        in_tokens = [r["input_tokens"] for r in successes]
        out_tokens = [r["output_tokens"] for r in successes]
        tot_tokens = [r["total_tokens"] for r in successes]
        char_lens = [len(r["response_text"]) for r in successes]
        reason_tokens = [r["reasoning_tokens"] for r in successes]

        model_summary = {
            "model": model_name,
            "provider": provider,
            "total_prompts": len(results),
            "successful_responses": len(successes),
            "failed_responses": len(errors),
            "total_retries": retries,
            "errors": [
                {"prompt_id": r["prompt_id"], "error": r["error"]} for r in errors
            ],
            "tokens": {
                "input": {
                    "total": sum(in_tokens),
                    **calculate_stats(in_tokens),
                },
                "output": {
                    "total": sum(out_tokens),
                    **calculate_stats(out_tokens),
                },
                "total": {
                    "total": sum(tot_tokens),
                    **calculate_stats(tot_tokens),
                },
                "reasoning": {
                    "total": sum(reason_tokens),
                    **calculate_stats(reason_tokens),
                },
            },
            "latency_seconds": {
                "total": round(sum(latencies), 2),
                **calculate_stats(latencies),
            },
            "response_length_chars": calculate_stats(char_lens),
            "category_breakdown": {},
            "anomalies": [],
        }

        # Category breakdown
        for cat in CATEGORIES:
            cat_successes = [r for r in successes if r["category"] == cat]
            if cat_successes:
                cat_lats = [r["latency_seconds"] for r in cat_successes]
                cat_outs = [r["output_tokens"] for r in cat_successes]
                cat_chars = [len(r["response_text"]) for r in cat_successes]
                model_summary["category_breakdown"][cat] = {
                    "count": len(cat_successes),
                    "avg_latency": round(sum(cat_lats) / len(cat_lats), 2),
                    "avg_output_tokens": round(sum(cat_outs) / len(cat_outs), 1),
                    "avg_chars": round(sum(cat_chars) / len(cat_chars), 1),
                }

        # Anomalies
        returned_slugs = list(set(r.get("model_returned", "") for r in successes if r.get("model_returned")))
        if returned_slugs:
            model_summary["anomalies"].append(f"Model returned by API: {', '.join(returned_slugs)}")

        empty_responses = [r["prompt_id"] for r in successes if not r["response_text"].strip()]
        if empty_responses:
            model_summary["anomalies"].append(f"Empty responses returned on prompt IDs: {empty_responses}")

        if sum(reason_tokens) > 0:
            model_summary["anomalies"].append(
                f"Model generates reasoning tokens (total: {sum(reason_tokens)}, avg: {sum(reason_tokens)/len(successes):.1f})"
            )

        summary_data["models"][role] = model_summary

        # Add to Markdown report
        report_lines.extend([
            f"\n## 3. {role.upper()} Model Performance: `{model_name}` ({provider})",
            f"- **Success Rate:** {len(successes)}/{len(results)} ({len(errors)} errors, {retries} retries)",
            "",
            "### Aggregate Statistics",
            "| Metric | Total | Min | Median | Mean | Max |",
            "|---|---|---|---|---|---|",
            f"| **Latency (s)** | {sum(latencies):.2f} | {calculate_stats(latencies)['min']} | {calculate_stats(latencies)['median']} | {calculate_stats(latencies)['mean']} | {calculate_stats(latencies)['max']} |",
            f"| **Input Tokens** | {sum(in_tokens)} | {calculate_stats(in_tokens)['min']} | {calculate_stats(in_tokens)['median']} | {calculate_stats(in_tokens)['mean']} | {calculate_stats(in_tokens)['max']} |",
            f"| **Output Tokens** | {sum(out_tokens)} | {calculate_stats(out_tokens)['min']} | {calculate_stats(out_tokens)['median']} | {calculate_stats(out_tokens)['mean']} | {calculate_stats(out_tokens)['max']} |",
            f"| **Total Tokens** | {sum(tot_tokens)} | {calculate_stats(tot_tokens)['min']} | {calculate_stats(tot_tokens)['median']} | {calculate_stats(tot_tokens)['mean']} | {calculate_stats(tot_tokens)['max']} |",
            f"| **Response Chars** | {sum(char_lens)} | {calculate_stats(char_lens)['min']} | {calculate_stats(char_lens)['median']} | {calculate_stats(char_lens)['mean']} | {calculate_stats(char_lens)['max']} |",
            "",
            "### Per-Category Breakdown",
            "| Category | N | Avg Latency (s) | Avg Output Tokens | Avg Response Chars |",
            "|---|---|---|---|---|",
        ])

        for cat in CATEGORIES:
            cb = model_summary["category_breakdown"].get(cat, {})
            if cb:
                report_lines.append(
                    f"| `{cat}` | {cb['count']} | {cb['avg_latency']}s | {cb['avg_output_tokens']} | {cb['avg_chars']} |"
                )

        report_lines.append("\n### Model-Specific Observations & Anomalies")
        for anom in model_summary["anomalies"]:
            report_lines.append(f"- {anom}")

    # Write summary files
    with open(SUMMARY_FILE, "w", encoding="utf-8") as f:
        json.dump(summary_data, f, indent=2, ensure_ascii=False)

    with open(REPORT_FILE, "w", encoding="utf-8") as f:
        f.write("\n".join(report_lines) + "\n")

    print(f"\nSaved pilot summary JSON: {SUMMARY_FILE}")
    print(f"Saved pilot report Markdown: {REPORT_FILE}")

    return summary_data


# ---------------------------------------------------------------------------
# MAIN ENTRYPOINT
# ---------------------------------------------------------------------------

def main():
    print("=" * 70)
    print("PROJECT 2 — 40-PROMPT MODEL-SELECTION PILOT (DUAL-MODEL INFERENCE)")
    print("=" * 70)

    # Step 1: Pre-flight Verification
    print("\n[Step 1] Verifying environment and prompt dataset...")
    keys = verify_environment()
    prompts = load_and_validate_prompts()

    # Step 2: Initialize API clients
    print("\n[Step 2] Initializing API clients...")
    groq_client = OpenAI(
        base_url=SMALL_BASE_URL,
        api_key=keys["groq_key"],
    )
    large_client = OpenAI(
        base_url=LARGE_BASE_URL,
        api_key=keys["groq_key"],
    )
    print("[OK] Clients ready.")

    # Step 3: Run dual inference
    print("\n[Step 3] Executing dual-model inference...")
    results_by_model = run_all_inference(prompts, groq_client, large_client)

    # Step 4: Post-run verification and response serialization
    print("\n[Step 4] Running post-inference verification...")
    post_run_verification_and_storage(prompts, results_by_model)

    # Step 5: Generate summary and print statistics
    print("\n[Step 5] Generating summary and report...")
    summary = generate_pilot_summary_and_report(prompts, results_by_model)

    print("\n" + "=" * 70)
    print("PILOT EXECUTION COMPLETE")
    print("=" * 70)


if __name__ == "__main__":
    main()
