"""
Project 2 — Pilot Phase 1: Prompt Selection & Category Assignment
=================================================================

Extracts candidate prompts from LMSYS Chatbot Arena, assigns each to
exactly one category using explicit keyword-based rules, and saves
the selection for researcher review before inference.

NO LLM is used for classification. Categories are assigned by
deterministic, documented keyword heuristics.

This is a feasibility/capability-gap pilot (40 prompts), NOT a
statistically representative sample of the LMSYS dataset.

Required environment variable:
  HF_TOKEN — HuggingFace token (for gated LMSYS dataset)

Usage:
  python select_prompts.py

Output:
  pilot_data/prompts.json — 40 prompts with category assignments
                            (review and edit before running inference)
"""

import json
import os
import re
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# CONFIGURATION
# ---------------------------------------------------------------------------

PROJECT_DIR = Path(__file__).parent
DATA_DIR = PROJECT_DIR / "pilot_data"
RAW_CACHE = DATA_DIR / "raw_prompts.json"
PROMPTS_FILE = DATA_DIR / "prompts.json"

CATEGORIES = ["factual_qa", "summarization", "reasoning_math", "creative"]
PROMPTS_PER_CATEGORY = 10
CANDIDATE_POOL_SIZE = 500  # Extract this many prompts to find 10 per category

# ---------------------------------------------------------------------------
# CATEGORY DEFINITIONS AND CLASSIFICATION RULES
# ---------------------------------------------------------------------------

# These are the explicit category definitions used for assignment.
# Each rule set is a list of (pattern, weight) tuples. The category
# with the highest total weight wins. All patterns are case-insensitive.
# This is deterministic and reproducible.

CATEGORY_DEFINITIONS = {
    "reasoning_math": {
        "definition": (
            "Math problems, logic puzzles, word problems, analytical reasoning, "
            "calculations, proofs, or any task requiring multi-step logical deduction "
            "with a verifiable numerical or logical answer."
        ),
        "patterns": [
            (r"\b\d+\s*[\+\-\*\/\^]\s*\d+", 3),       # arithmetic expressions
            (r"\bcalculat[e|ion]", 3),
            (r"\bsolve\b", 3),
            (r"\bequation\b", 3),
            (r"\bprob(?:ability|lem)\b", 2),
            (r"\bhow many\b", 2),
            (r"\bmath\b", 3),
            (r"\balgebra\b", 3),
            (r"\bgeometry\b", 3),
            (r"\bderivative\b", 3),
            (r"\bintegral\b", 3),
            (r"\bprove\b", 2),
            (r"\blogic(?:al)?\b", 2),
            (r"\bpuzzle\b", 2),
            (r"\bif\b.*\bthen\b.*\bwhat\b", 2),
            (r"\bpercent\b", 2),
            (r"\bratio\b", 2),
            (r"\bstatistic", 2),
            (r"\baverage\b", 2),
            (r"\bmedian\b", 2),
        ],
    },
    "factual_qa": {
        "definition": (
            "Questions with specific, verifiable factual answers: names, dates, "
            "definitions, places, quantities, or explanations of how specific "
            "things work. The correct answer is a concrete fact."
        ),
        "patterns": [
            (r"\bwhat is\b", 2),
            (r"\bwhat are\b", 2),
            (r"\bwho is\b", 3),
            (r"\bwho was\b", 3),
            (r"\bwhen did\b", 3),
            (r"\bwhen was\b", 3),
            (r"\bwhere is\b", 3),
            (r"\bwhere was\b", 3),
            (r"\bdefine\b", 3),
            (r"\bdefinition\b", 3),
            (r"\bhow does\b.*\bwork\b", 2),
            (r"\bwhat does\b.*\bmean\b", 2),
            (r"\bname\b.*\b(?:the|a)\b", 1),
            (r"\bcapital\b.*\bof\b", 3),
            (r"\bpopulation\b", 2),
            (r"\bfounded\b", 2),
            (r"\binvented\b", 2),
            (r"\bdiscovered\b", 2),
            (r"\bwhat year\b", 3),
            (r"\btrue or false\b", 2),
        ],
    },
    "creative": {
        "definition": (
            "Creative writing, brainstorming, roleplay, stories, poems, "
            "fictional scenarios, opinion pieces, or open-ended tasks where "
            "quality is subjective and no single correct answer exists."
        ),
        "patterns": [
            (r"\bwrite\b.*\b(?:story|poem|essay|song|script|letter)\b", 3),
            (r"\bstory\b", 2),
            (r"\bpoem\b", 3),
            (r"\bcreativ", 2),
            (r"\bimagin[e|ation]", 3),
            (r"\broleplay\b", 3),
            (r"\bpretend\b", 3),
            (r"\bfiction", 2),
            (r"\bact as\b", 2),
            (r"\byou are\b.*\b(?:a|an|the)\b", 2),
            (r"\bbrainstorm\b", 2),
            (r"\bgenerate\b.*\bideas?\b", 2),
            (r"\binvent\b", 1),
            (r"\bmake up\b", 2),
            (r"\bcontinue\b.*\bstory\b", 3),
            (r"\bdialogue\b", 2),
            (r"\bcharacter\b", 1),
            (r"\bplot\b", 1),
        ],
    },
    "summarization": {
        "definition": (
            "Requests to summarize, explain, describe, or give an overview "
            "of a topic, concept, or provided text. The task is to condense "
            "or present information clearly."
        ),
        "patterns": [
            (r"\bsummari[zs]", 4),
            (r"\bsummary\b", 4),
            (r"\bexplain\b", 2),
            (r"\bdescribe\b", 2),
            (r"\boverview\b", 3),
            (r"\bin\s+(?:simple|brief|short)\b", 2),
            (r"\bbriefly\b", 2),
            (r"\boutline\b", 2),
            (r"\bbreak\s+down\b", 2),
            (r"\bkey\s+points?\b", 3),
            (r"\bmain\s+(?:idea|point|takeaway)", 3),
            (r"\bparaphrase\b", 3),
            (r"\beli5\b", 3),
            (r"\blayman", 2),
            (r"\btl;?\s*dr\b", 4),
            (r"\bgist\b", 3),
        ],
    },
}


# ---------------------------------------------------------------------------
# CLASSIFICATION
# ---------------------------------------------------------------------------

def classify_prompt(prompt_text):
    """
    Classify a prompt using deterministic keyword heuristics.
    Returns (category, score, matched_patterns).
    """
    text_lower = prompt_text.lower()
    scores = {}
    matches = {}

    for cat, rules in CATEGORY_DEFINITIONS.items():
        total_score = 0
        cat_matches = []
        for pattern, weight in rules["patterns"]:
            if re.search(pattern, text_lower):
                total_score += weight
                cat_matches.append(pattern)
        scores[cat] = total_score
        matches[cat] = cat_matches

    # Find the category with the highest score
    best_cat = max(scores, key=scores.get)
    best_score = scores[best_cat]

    if best_score == 0:
        return "unclassified", 0, {}

    return best_cat, best_score, matches[best_cat]


# ---------------------------------------------------------------------------
# DATA LOADING
# ---------------------------------------------------------------------------

def load_lmsys_prompts(hf_token, max_prompts=CANDIDATE_POOL_SIZE):
    """Load single-turn English prompts from LMSYS Chatbot Arena."""
    print(f"--- Loading LMSYS Chatbot Arena data ---")

    # Use cache if available
    if RAW_CACHE.exists():
        with open(RAW_CACHE, "r", encoding="utf-8") as f:
            cached = json.load(f)
        if len(cached) >= max_prompts:
            print(f"[CACHE] Loaded {len(cached)} prompts from cache.")
            return cached[:max_prompts]

    from datasets import load_dataset

    print("Downloading dataset (streaming)...")
    ds = load_dataset(
        "lmsys/chatbot_arena_conversations",
        split="train",
        streaming=True,
        token=hf_token,
    )

    prompts = []
    seen = 0
    for row in ds:
        seen += 1
        if seen % 1000 == 0:
            print(f"  Scanned {seen} rows, extracted {len(prompts)} prompts...")

        conv = row.get("conversation_a", [])
        if not conv or len(conv) == 0:
            continue

        user_msgs = [m for m in conv if m.get("role") == "user"]
        if len(user_msgs) != 1:
            continue

        prompt_text = user_msgs[0].get("content", "").strip()
        if not prompt_text or len(prompt_text) < 10:
            continue

        # Basic English filter: >80% ASCII
        ascii_ratio = sum(1 for c in prompt_text if ord(c) < 128) / len(prompt_text)
        if ascii_ratio < 0.80:
            continue

        # Skip very long prompts for pilot
        if len(prompt_text) > 3000:
            continue

        prompts.append({
            "question_id": row.get("question_id", f"q_{seen}"),
            "prompt_text": prompt_text,
            "source_row": seen,
        })

        if len(prompts) >= max_prompts:
            break

    print(f"Extracted {len(prompts)} single-turn English prompts from {seen} rows.")

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with open(RAW_CACHE, "w", encoding="utf-8") as f:
        json.dump(prompts, f, indent=2, ensure_ascii=False)

    return prompts


# ---------------------------------------------------------------------------
# SELECTION
# ---------------------------------------------------------------------------

def select_pilot_prompts(prompts):
    """Select 10 candidate prompts per category using deterministic keyword heuristics."""
    print(f"\n--- Classifying {len(prompts)} prompts (keyword heuristics) ---")

    # Classify all
    classified = {cat: [] for cat in CATEGORIES}
    unclassified = []

    for p in prompts:
        cat, score, matched = classify_prompt(p["prompt_text"])
        entry = {
            "prompt_id": str(p["question_id"]),
            "category": cat,
            "classification_score": score,
            "matched_patterns": matched,
            "prompt_text": p["prompt_text"],
            "source_row": p["source_row"],
        }
        if cat in classified:
            classified[cat].append(entry)
        else:
            unclassified.append(entry)

    print(f"\nClassification distribution:")
    for cat in CATEGORIES:
        print(f"  {cat}: {len(classified[cat])}")
    print(f"  unclassified: {len(unclassified)}")

    # Select 10 candidate prompts per category using deterministic keyword
    # heuristics. To ensure reasonable variety within each category, we:
    #   1. Filter to prompts scoring >= MIN_SCORE (clear category match)
    #   2. Sort qualifying prompts by source_row (stable, deterministic order)
    #   3. Select evenly spaced prompts across the qualifying pool
    # This avoids homogeneity from picking only the highest-scoring prompts.

    MIN_SCORE = 2  # Minimum heuristic score to qualify

    selected = []
    for cat in CATEGORIES:
        # Filter to clear matches
        pool = [p for p in classified[cat] if p["classification_score"] >= MIN_SCORE]
        if len(pool) < PROMPTS_PER_CATEGORY:
            # Fall back to all classified prompts if too few qualify
            pool = classified[cat]
            print(f"  WARNING: Only {len(pool)} prompts for {cat} "
                  f"(score >= {MIN_SCORE}), using all available")

        # Sort by source_row for deterministic ordering
        pool = sorted(pool, key=lambda x: x["source_row"])

        if len(pool) <= PROMPTS_PER_CATEGORY:
            chosen = pool
        else:
            # Evenly spaced selection across the pool for variety
            step = len(pool) / PROMPTS_PER_CATEGORY
            indices = [int(i * step) for i in range(PROMPTS_PER_CATEGORY)]
            chosen = [pool[i] for i in indices]

        for item in chosen:
            selected.append({
                "prompt_id": item["prompt_id"],
                "category": item["category"],
                "classification_score": item["classification_score"],
                "matched_patterns": item["matched_patterns"],
                "classification_method": "keyword_heuristic",
                "prompt_text": item["prompt_text"],
                "source_row": item["source_row"],
            })
        print(f"  {cat}: selected {len(chosen)} from {len(pool)} qualifying")

    print(f"\nSelected {len(selected)} prompts.")
    return selected


# ---------------------------------------------------------------------------
# MAIN
# ---------------------------------------------------------------------------

def main():
    print("=" * 60)
    print("PROJECT 2 — PILOT PROMPT SELECTION")
    print("(Keyword-based category assignment, no LLM classifier)")
    print("=" * 60)

    # Check HF token
    hf_token = os.environ.get("HF_TOKEN", "")
    if not hf_token:
        print("\nERROR: HF_TOKEN not set. Required for gated LMSYS dataset.")
        print('Set it with: setx HF_TOKEN "hf_..."')
        print("Then restart your terminal and re-run.")
        sys.exit(1)

    # Load prompts
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    prompts = load_lmsys_prompts(hf_token)

    # Select and classify
    selected = select_pilot_prompts(prompts)

    # Save with metadata
    output = {
        "metadata": {
            "description": (
                "40-prompt model-selection pilot for Project 2. "
                "This is a feasibility/capability-gap pilot, NOT a statistically "
                "representative sample of the LMSYS dataset."
            ),
            "classification_method": "Deterministic keyword heuristic (no LLM)",
            "selection_method": (
                "10 candidate prompts per category selected using deterministic "
                "keyword heuristics. Qualifying prompts (score >= 2) are sampled "
                "at even intervals across the pool to ensure within-category variety."
            ),
            "mandatory_review": (
                "The researcher MUST review all category assignments before "
                "running inference. Edit any misassigned prompts directly in "
                "this file."
            ),
            "source": "lmsys/chatbot_arena_conversations",
            "prompts_per_category": PROMPTS_PER_CATEGORY,
            "categories": {
                cat: CATEGORY_DEFINITIONS[cat]["definition"]
                for cat in CATEGORIES
            },
        },
        "prompts": selected,
    }

    with open(PROMPTS_FILE, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    # Print summary
    print(f"\n{'=' * 60}")
    print(f"SELECTION COMPLETE")
    print(f"{'=' * 60}")
    print(f"\nSaved to: {PROMPTS_FILE}")
    print(f"\nCategory breakdown:")
    for cat in CATEGORIES:
        cat_prompts = [p for p in selected if p["category"] == cat]
        print(f"  {cat}: {len(cat_prompts)}")
        for p in cat_prompts[:2]:
            snippet = p["prompt_text"][:80].replace("\n", " ")
            print(f"    - \"{snippet}...\"")
        if len(cat_prompts) > 2:
            print(f"    ... and {len(cat_prompts) - 2} more")

    print(f"\n>>> MANDATORY: Review ALL category assignments in {PROMPTS_FILE}")
    print(">>> Edit any prompts whose category is incorrect.")
    print(">>> Inference must NOT proceed without researcher review.")
    print(">>> Then run: python run_pilot.py")


if __name__ == "__main__":
    main()
