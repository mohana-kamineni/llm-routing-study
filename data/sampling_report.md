# Project 2 — Phase 1 Benchmark Sampling Report

**Dataset:** `lmsys/chatbot_arena_conversations` (train split)  
**Total Prompts Sampled:** 500 (125 per category across 4 categories)  
**Random Seed:** 42  
**Storage Location:** `data/prompts.json`  

---

## 1. Category Distribution & Sampling Statistics

| Category | Target Prompts | Qualifying Candidates | Selected | Mean Word Count | Mean Heuristic Score $S(x)$ |
|---|---|---|---|---|---|
| **factual_qa** | 125 | 250 | 125 | 13.8 | 0.3027 |
| **summarization** | 125 | 234 | 125 | 242.9 | 0.6144 |
| **reasoning_math** | 125 | 250 | 125 | 68.9 | 0.5848 |
| **creative** | 125 | 250 | 125 | 42.7 | 0.2749 |

---

## 2. Summarization 50/75 Sensitivity Stratification

- **Independent-Reference Subset:** 50 prompts (stratified across source text length distribution).
- **Assisted-Reference Subset:** 75 prompts.

---

## 3. Heuristic Score Distribution Across Categories

The pre-specified heuristic difficulty score $S(x) \in [0, 1]$ exhibits expected domain differentiation based on frozen design weights:
- **Creative / Open-Ended:** Lowest baseline difficulty ($f_{\text{cat}} = 0.20$), fluent open-ended responses.
- **Factual QA:** Moderate difficulty ($f_{\text{cat}} = 0.40$), short queries ($f_{\text{len}}$ low).
- **Summarization:** Moderate-to-high difficulty ($f_{\text{cat}} = 0.60$), longer source passages ($f_{\text{len}}$ high).
- **Reasoning / Math:** Highest difficulty ($f_{\text{cat}} = 0.80$, $f_{\text{reason}}$ high), symbolic and multi-step deduction.

---

## 4. Phase 1 Verification Status

- [x] 500 single-turn English prompts sampled from `lmsys/chatbot_arena_conversations`.
- [x] Exactly 125 prompts per category across 4 categories.
- [x] Code synthesis / programming prompts completely excluded.
- [x] Summarization 50/75 split stratified by text length.
- [x] Pre-specified heuristic router difficulty scores $S(x)$ computed and stored for all 500 prompts.
- [x] All candidate questions retain original LMSYS `question_id` for provenance.
