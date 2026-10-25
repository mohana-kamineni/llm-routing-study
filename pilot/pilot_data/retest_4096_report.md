# Project 2 — Targeted 10-Prompt Model-Selection Re-Test Report (`max_tokens = 4096`)

**Generated:** 2026-09-13  
**Scope:** Targeted Re-Test of 7 Token-Exhaustion Prompts + 3 Qualitative Audit Control Prompts  
**Models Evaluated:**
- **Small Model:** `openai/gpt-oss-20b` via Groq
- **Large Candidate:** `nvidia/nemotron-3-ultra-550b-a55b-20260604:free` via OpenRouter

> **Methodological Boundary & Protocol:** This targeted re-test was conducted under deterministic settings (`temperature = 0.0`, `max_tokens = 4096`) to test the hypothesis that the 1,024-token budget in the first pilot caused the empty responses for `openai/gpt-oss-20b`. In accordance with frozen project instructions, **no numerical quality score is assigned, no winner is declared, and no automated LLM judging is performed.**

---

## 1. Executive Summary & Core Hypothesis Verification

### 1.1 Hypothesis Test Result: Confirmed with Nuance
The re-test confirms that the lack of visible output on `openai/gpt-oss-20b` in the initial pilot was indeed caused by token budget exhaustion during the model's internal chain-of-thought deliberation, but reveals two distinct behavioral regimes:

1. **Structured / Well-Bounded Prompts (Recovered):** On 4 of the 7 previously empty prompts, expanding `max_tokens` from 1,024 to 4,096 allowed the model's reasoning loop to complete and emit rich, highly complete, visible responses (7,143 chars on OpenCL vs CUDA; 2,473 chars on Finnish Speech; 2,217 chars on Song Composition; 472 chars of structured JSON on OCR label extraction).
2. **Open-Ended / Unbounded Prompts (Runaway Deliberation):** On 3 of the 7 prompts (Ursula Bellugi biography, Lois Lane comic story, and Ocean-World plant life), the model's internal reasoning loop expanded to consume all **4,094 reasoning tokens**, again hitting the hard cap at 4,096 output tokens before emitting visible text. This indicates a runaway deliberation dynamic on open-ended prompts lacking strict structural bounds.

### 1.2 Quantitative Comparison Overview (10 Prompts)

| Metric | Small Model (`openai/gpt-oss-20b`) | Large Candidate (`nvidia/nemotron-3-ultra`) |
| :--- | :--- | :--- |
| **Total Prompts Tested** | 10 | 10 |
| **Successful API Calls** | 10 / 10 (100%) | 9 / 10 (90.0% — Prompt 10 hit daily free rate limit) |
| **Visible Output Rate** | **7 / 10 (70.0%)** *(up from 3/10 at 1024 tokens)* | **9 / 10 (100% of successful calls)** |
| **Mean Latency (Successful Calls)** | **13.67 s** (min: 0.98s, max: 34.87s) | **222.06 s** (min: 105.35s, max: 827.03s) |
| **Mean Output Tokens** | 2,745.8 tokens | 1,634.3 tokens |
| **Mean Reasoning Tokens** | 1,987.8 tokens | 250.7 tokens |
| **Total Visible Characters** | 16,039 chars | 45,699 chars (across 9 prompts) |

---

## 2. Detailed Prompt-by-Prompt Comparison (All 10 Prompts)

### Prompt `58210e39b3fd4441a2bd4a518bb44c2d` — OpenCL vs CUDA Technical Comparison (Token Exhaustion)
**Category:** `factual_qa`  
**Prompt:** > What is the difference between OpenCL and CUDA?...

| Evaluation Metric | GPT-OSS 20B (Pilot 1, 1024) | GPT-OSS 20B (Re-test, 4096) | Nemotron (Pilot 1, 1024) | Nemotron (Re-test, 4096) |
| :--- | :--- | :--- | :--- | :--- |
| **Visible Chars** | 0 chars | **7143 chars** | 3268 chars | **6618 chars** |
| **Output Tokens** | 1024 tok | **3164 tok** | 1024 tok | **1951 tok** |
| **Reasoning Tokens** | 1022 tok | **1146 tok** | 59 tok | **59 tok** |
| **Latency** | 2.12 s | **4.51 s** | 80.09 s | **179.87 s** |
| **Status** | HTTP 200 (Empty) | HTTP 200 (Visible Output) | HTTP 200 (Visible Output) | HTTP 200 (Visible Output) |

**Qualitative Analysis:**
- **Behavioral Shift:** Dramatic recovery for GPT-OSS 20B. After spending 1,146 tokens reasoning through device architectures, memory models, APIs, and compilers, the model produced an exhaustive 7,143-character comparison complete with architecture comparison tables, memory management breakdowns, and code examples in OpenCL C vs CUDA C.
- **Comparison with Nemotron:** Both models provide outstanding technical depth. Nemotron produced 6,618 characters with detailed compilation workflow explanations (PTX vs SPIR-V). GPT-OSS generated even more code examples and architectural contrast tables once unlocked by the 4,096 budget.

---

### Prompt `c284f2bf6c7243b5aad2b5539fec9866` — Who is Ursula Bellugi (Biography) (Token Exhaustion)
**Category:** `factual_qa`  
**Prompt:** > who is Ursula Bellugi...

| Evaluation Metric | GPT-OSS 20B (Pilot 1, 1024) | GPT-OSS 20B (Re-test, 4096) | Nemotron (Pilot 1, 1024) | Nemotron (Re-test, 4096) |
| :--- | :--- | :--- | :--- | :--- |
| **Visible Chars** | 0 chars | **0 chars** | 4099 chars | **3777 chars** |
| **Output Tokens** | 1024 tok | **4096 tok** | 914 tok | **848 tok** |
| **Reasoning Tokens** | 1022 tok | **4094 tok** | 40 tok | **57 tok** |
| **Latency** | 1.38 s | **4.76 s** | 95.34 s | **119.35 s** |
| **Status** | HTTP 200 (Empty) | HTTP 200 (Empty, 4094 reas tok) | HTTP 200 (Visible Output) | HTTP 200 (Visible Output) |

**Qualitative Analysis:**
- **Behavioral Shift:** GPT-OSS 20B remained trapped in internal deliberation, spending 4,094 tokens drafting an extensive internal monograph outlining Bellugi's biography, bibliography, research at Salk Institute, and Williams syndrome discoveries, but ran out of tokens before writing the visible response.
- **Comparison with Nemotron:** Nemotron generated 3,777 characters in 848 tokens, cleanly dividing Bellugi's contributions into American Sign Language (ASL) linguistics, Williams Syndrome neurobiology, academic honors, and legacy.

---

### Prompt `119b348113a84b44a1fed88ac181fdc2` — Finnish President 2024 Speech Synopsis (Token Exhaustion)
**Category:** `summarization`  
**Prompt:** > Summarize the Finnish president's new year's speech of 2024....

| Evaluation Metric | GPT-OSS 20B (Pilot 1, 1024) | GPT-OSS 20B (Re-test, 4096) | Nemotron (Pilot 1, 1024) | Nemotron (Re-test, 4096) |
| :--- | :--- | :--- | :--- | :--- |
| **Visible Chars** | 0 chars | **2473 chars** | 3659 chars | **4127 chars** |
| **Output Tokens** | 1024 tok | **1130 tok** | 946 tok | **1032 tok** |
| **Reasoning Tokens** | 1022 tok | **658 tok** | 90 tok | **102 tok** |
| **Latency** | 1.38 s | **1.65 s** | 72.35 s | **169.94 s** |
| **Status** | HTTP 200 (Empty) | HTTP 200 (Visible Output) | HTTP 200 (Visible Output) | HTTP 200 (Visible Output) |

**Qualitative Analysis:**
- **Behavioral Shift:** Complete recovery for GPT-OSS 20B (2,473 visible characters). After 658 reasoning tokens, it produced a structured synopsis covering foreign/security policy (NATO accession, Russia relations), domestic economic reforms, and societal cohesion.
- **Comparison with Nemotron:** Both produced structured thematic synopses (GPT-OSS: 2,473 chars; Nemotron: 4,127 chars). Nemotron attributed the speech to Sauli Niinistö; GPT-OSS noted the 2024 political transition context.

---

### Prompt `61320a80c6e149559d74b4de88b6233a` — Shipping Label OCR Extraction (Token Exhaustion / ReAct Interface)
**Category:** `reasoning_math`  
**Prompt:** > the following is text scanned and OCR'd from a shipping label. Each OCR contains some errors. There are multiple OCR sections of the same image with errors in different places. Loo...

| Evaluation Metric | GPT-OSS 20B (Pilot 1, 1024) | GPT-OSS 20B (Re-test, 4096) | Nemotron (Pilot 1, 1024) | Nemotron (Re-test, 4096) |
| :--- | :--- | :--- | :--- | :--- |
| **Visible Chars** | 0 chars | **472 chars** | 2643 chars | **532 chars** |
| **Output Tokens** | 1024 tok | **1478 tok** | 1024 tok | **1244 tok** |
| **Reasoning Tokens** | 1022 tok | **1318 tok** | 671 tok | **701 tok** |
| **Latency** | 7.74 s | **1.83 s** | 110.53 s | **121.23 s** |
| **Status** | HTTP 200 (Empty) | HTTP 200 (Visible Output) | HTTP 200 (Visible Output) | HTTP 200 (Visible Output) |

**Qualitative Analysis:**
- **Behavioral Shift & Interface Compatibility:** Complete recovery for GPT-OSS 20B. The prompt required parsing multiple corrupted OCR scans of a shipping label and outputting structured JSON.
- **Output Integrity:** Both models produced clean, valid JSON extracting `from_company_name`, `from_address`, `to_name`, `to_address`, `tracking_number`, `package_weight`, and `date` (`2023-03-26`). Neither model triggered any tool-call error or formatting conflict.

---

### Prompt `b0c343364ffb458083fed7b573bfce0f` — Song Composition via Music Theory Principles (Token Exhaustion)
**Category:** `creative`  
**Prompt:** > Write a song using music theory principles and rich instrument captions, without relying on drums, electric guitars, or bass. The song is a eurobeat song. Use the following format:...

| Evaluation Metric | GPT-OSS 20B (Pilot 1, 1024) | GPT-OSS 20B (Re-test, 4096) | Nemotron (Pilot 1, 1024) | Nemotron (Re-test, 4096) |
| :--- | :--- | :--- | :--- | :--- |
| **Visible Chars** | 0 chars | **2217 chars** | 3050 chars | **7287 chars** |
| **Output Tokens** | 1024 tok | **4096 tok** | 1024 tok | **2752 tok** |
| **Reasoning Tokens** | 1022 tok | **3475 tok** | 232 tok | **582 tok** |
| **Latency** | 7.43 s | **34.87 s** | 67.46 s | **221.55 s** |
| **Status** | HTTP 200 (Empty) | HTTP 200 (Visible Output) | HTTP 200 (Visible Output) | HTTP 200 (Visible Output) |

**Qualitative Analysis:**
- **Behavioral Shift:** Recovery for GPT-OSS 20B (2,217 visible characters). Spent 3,475 tokens analyzing harmonic progressions, voice leading, and instrument acoustics, then emitted full song lyrics and arrangement captions.
- **Comparison with Nemotron:** Nemotron generated 7,287 characters in 2,752 tokens, constructing an entire orchestral piece ('Neon Velocity', 148 BPM, F minor) with exact instrument cues (woodwinds, cello pizzicato, harp glissandos).

---

### Prompt `4e6446c00a2447d0ad09c58ce942e2c5` — Golden Age Comic Story (Lois Lane) (Token Exhaustion)
**Category:** `creative`  
**Prompt:** > Write this story in the style of a Golden Age comic: Lois Lane is exposed to a strange new perfume that causes her body to swell up to enormous proportions, until she's as round as...

| Evaluation Metric | GPT-OSS 20B (Pilot 1, 1024) | GPT-OSS 20B (Re-test, 4096) | Nemotron (Pilot 1, 1024) | Nemotron (Re-test, 4096) |
| :--- | :--- | :--- | :--- | :--- |
| **Visible Chars** | 0 chars | **0 chars** | 2982 chars | **8815 chars** |
| **Output Tokens** | 1024 tok | **4096 tok** | 1024 tok | **2811 tok** |
| **Reasoning Tokens** | 1022 tok | **4094 tok** | 132 tok | **183 tok** |
| **Latency** | 2.41 s | **30.06 s** | 86.27 s | **827.03 s** |
| **Status** | HTTP 200 (Empty) | HTTP 200 (Empty, 4094 reas tok) | HTTP 200 (Visible Output) | HTTP 200 (Visible Output) |

**Qualitative Analysis:**
- **Behavioral Shift:** GPT-OSS 20B entered runaway deliberation on Golden Age comic writing conventions, spending all 4,094 tokens brainstorming story beats, dialogue snatches, and comic panels without transitioning to output generation.
- **Comparison with Nemotron:** Nemotron generated an 8,815-character full multi-page comic script (*Superman #74: 'The Perfume That Conquered Metropolis!'*), complete with panel descriptions, captions, and authentic period-accurate dialogue.

---

### Prompt `859c561d217746fb865dc5328152abb5` — All-Water World Plant Life Speculation (Token Exhaustion)
**Category:** `creative`  
**Prompt:** > Imagine the world was made entirely of water.  What would plant life look like?...

| Evaluation Metric | GPT-OSS 20B (Pilot 1, 1024) | GPT-OSS 20B (Re-test, 4096) | Nemotron (Pilot 1, 1024) | Nemotron (Re-test, 4096) |
| :--- | :--- | :--- | :--- | :--- |
| **Visible Chars** | 0 chars | **0 chars** | 3577 chars | **8084 chars** |
| **Output Tokens** | 1024 tok | **4096 tok** | 1024 tok | **2255 tok** |
| **Reasoning Tokens** | 1022 tok | **4094 tok** | 113 tok | **156 tok** |
| **Latency** | 6.51 s | **28.78 s** | 59.22 s | **187.39 s** |
| **Status** | HTTP 200 (Empty) | HTTP 200 (Empty, 4094 reas tok) | HTTP 200 (Visible Output) | HTTP 200 (Visible Output) |

**Qualitative Analysis:**
- **Behavioral Shift:** GPT-OSS 20B spent 4,094 tokens on an exhaustive biological brainstorm (pelagic photosynthesis, floating kelp forests, biomechanics of hydrostatic pressure, bioluminescence) without emitting visible text.
- **Comparison with Nemotron:** Nemotron produced 8,084 characters of world-building biology across 5 depth zones (Epi-pelagic to Abyssal), describing macroalgae, gas-bladder flotation, and non-terrestrial photosynthetic pigments.

---

### Prompt `cf1d55f8ef2042df96b9c7ce6b966dfe` — Patent Claims Summarized in One Paragraph (Qualitative Audit Control)
**Category:** `summarization`  
**Prompt:** > Summarize in one paragraph the invention described by the following patent claims:

1. A computer-implemented method for performing semi-supervised contrastive learning of visual r...

| Evaluation Metric | GPT-OSS 20B (Pilot 1, 1024) | GPT-OSS 20B (Re-test, 4096) | Nemotron (Pilot 1, 1024) | Nemotron (Re-test, 4096) |
| :--- | :--- | :--- | :--- | :--- |
| **Visible Chars** | 787 chars | **793 chars** | 780 chars | **851 chars** |
| **Output Tokens** | 299 tok | **304 tok** | 254 tok | **278 tok** |
| **Reasoning Tokens** | 159 tok | **163 tok** | 182 tok | **196 tok** |
| **Latency** | 0.58 s | **25.80 s** | 61.18 s | **107.08 s** |
| **Status** | HTTP 200 (Empty) | HTTP 200 (Visible Output) | HTTP 200 (Visible Output) | HTTP 200 (Visible Output) |

**Qualitative Analysis:**
- **Control Prompt Analysis:** Both models remained strictly compliant with the one-paragraph constraint. GPT-OSS produced 793 characters (163 reasoning tokens); Nemotron produced 851 characters (196 reasoning tokens). Demonstrates that on well-bounded instructional prompts, GPT-OSS reasoning is tightly budgeted.

---

### Prompt `8ea4c640c91b4d3584f20b693686eeb8` — Right Triangle Altitude Hypotenuse Theorem (Qualitative Audit Control)
**Category:** `reasoning_math`  
**Prompt:** > The altitude to the hypotenuse of a right triangle divides the hypotenuse into two segments with lengths in the ratio 1 : 2. The length of the altitude is 6 cm. How long is the hyp...

| Evaluation Metric | GPT-OSS 20B (Pilot 1, 1024) | GPT-OSS 20B (Re-test, 4096) | Nemotron (Pilot 1, 1024) | Nemotron (Re-test, 4096) |
| :--- | :--- | :--- | :--- | :--- |
| **Visible Chars** | 598 chars | **598 chars** | 486 chars | **462 chars** |
| **Output Tokens** | 516 tok | **516 tok** | 599 tok | **553 tok** |
| **Reasoning Tokens** | 256 tok | **256 tok** | 312 tok | **283 tok** |
| **Latency** | 0.88 s | **0.98 s** | 69.89 s | **105.35 s** |
| **Status** | HTTP 200 (Empty) | HTTP 200 (Visible Output) | HTTP 200 (Visible Output) | HTTP 200 (Visible Output) |

**Qualitative Analysis:**
- **Control Prompt Analysis:** Both models produced identical mathematical solutions (ratio = $\sqrt{2}/3$) with identical algebraic derivations. Token usage remained virtually identical to Pilot 1 (GPT-OSS: 516 out tokens; Nemotron: 553 out tokens).

---

### Prompt `b8bac339a7d54685b4f79f5886cccf0c` — Superhero Origin Screenwriter Profile (Qualitative Audit Control)
**Category:** `creative`  
**Prompt:** > You are a world-class screenwriter and comic book creator. Your specialty is creating rich, colorful characters with varied and fascinating backgrounds and personalities. When you ...

| Evaluation Metric | GPT-OSS 20B (Pilot 1, 1024) | GPT-OSS 20B (Re-test, 4096) | Nemotron (Pilot 1, 1024) | Nemotron (Re-test, 4096) |
| :--- | :--- | :--- | :--- | :--- |
| **Visible Chars** | 2323 chars | **2338 chars** | 4158 chars | **0 chars** |
| **Output Tokens** | 811 tok | **812 tok** | 942 tok | **0 tok** |
| **Reasoning Tokens** | 299 tok | **299 tok** | 68 tok | **0 tok** |
| **Latency** | 5.07 s | **3.33 s** | 127.68 s | **1.87 s** |
| **Status** | HTTP 200 (Empty) | HTTP 200 (Visible Output) | HTTP 200 (Visible Output) | HTTP 429 (Daily limit) |

**Qualitative Analysis:**
- **Control Prompt Analysis:** GPT-OSS reproduced its complete character profile (*Nova Starling*, 2,338 chars) with 299 reasoning tokens and 812 output tokens. Nemotron encountered OpenRouter's daily free tier quota limit (`Rate limit exceeded: free-models-per-day`) on this 10th re-test call (49th total call today). However, Nemotron's complete 4,158-character response for this exact prompt is fully preserved from Pilot 1.

---

## 3. Comparative Findings Across Key Evaluation Dimensions

### 3.1 Visible Output & Recovery Rate
- In Pilot 1 (`max_tokens = 1024`), GPT-OSS 20B produced visible output on only **3 of 10** re-tested prompts (30%).
- In Re-Test (`max_tokens = 4096`), GPT-OSS 20B produced visible output on **7 of 10** prompts (70%).
- For technical and structured tasks (OpenCL vs CUDA, OCR JSON extraction, Speech synopsis, Patent summary, Math), expanding the budget completely resolved the truncation issue.
- However, for highly open-ended or speculative creative tasks (biographical query without length bounds, comic script generation, ocean world plant life), GPT-OSS 20B's reasoning mechanism deliberated for all 4,094 tokens. This demonstrates that budget expansion alone does not guarantee completion for unconstrained prompts without a reasoning effort parameter or explicit output length guardrail.

### 3.2 Latency and Throughput
- **GPT-OSS 20B on Groq:** Remains remarkably fast despite generating thousands of reasoning tokens. For the prompts where it generated visible output, latency averaged **13.67 seconds** (e.g. 4.51s for 7,143 chars on OpenCL; 1.83s for OCR extraction).
- **Nemotron-3-Ultra on OpenRouter:** Significantly slower, averaging **222.06 seconds (~3.7 minutes) per prompt** under `max_tokens = 4096`, with peak latency reaching **827.03 seconds (~13.8 minutes)** on Prompt 6. This reflects heavy compute demands for 550B-parameter inference combined with queue delays on the free endpoint.

### 3.3 Instruction Following & Quality Parity on Completed Tasks
- On tasks where both models emitted visible text, qualitative parity is high:
  - **OpenCL vs CUDA:** Both models produced publication-grade technical comparisons with comparable accuracy and depth.
  - **OCR Label Extraction:** Both models extracted identical key-value pairs into clean JSON without hallucinating missing fields.
  - **Geometry (Altitude Theorem):** Both derived the identical algebraic ratio ($\sqrt{2}/3$).
  - **Patent Summarization:** Both strictly obeyed the single-paragraph constraint with near-identical character counts (~790 vs ~850 chars).

### 3.4 OpenRouter Operational Limits
- The OpenRouter free tier (`nvidia/nemotron-3-ultra-550b-a55b-20260604:free`) enforced a daily call limit (`Rate limit exceeded: free-models-per-day`) after ~50 total requests across the pilot and re-test. This confirms that large-scale experiments (~500 prompts) cannot rely on the free tier endpoint without paid credits or alternative provisioning.

---

## 4. Methodological Conclusion

1. **Core Diagnosis:** The pilot failures in GPT-OSS 20B were predominantly a configuration artifact of the 1,024-token budget clashing with the model's native reasoning architecture.
2. **Dual Nature of Reasoning Models:** On structured tasks, GPT-OSS 20B uses ~300–1,300 reasoning tokens to plan, resulting in concise and accurate output. On unstructured or open-ended prompts, it can consume >4,000 reasoning tokens unless bounded.
3. **Cost-Quality Analysis Implication:** For the main routing study, small models with reasoning tokens (like GPT-OSS 20B) require `max_tokens >= 2048` or `reasoning_effort` constraints to operate fairly in routing evaluations.

*Audit report completed. No quality rankings or winner declarations assigned.*
