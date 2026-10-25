# Chapter: Empirical Evaluation of LLM Routing Between Parameter-Scaled Models Across Task Domains

## Executive Summary & Study Overview

This chapter presents the empirical evaluation of dynamic language model routing between two open-weight models of disparate parameter scales: **`openai/gpt-oss-20b`** (20 billion parameters) and **`openai/gpt-oss-120b`** (120 billion parameters). A central promise of LLM routing architectures is that inference expenditures can be substantially curtailed by deploying lightweight models on routine or "simple" requests while selectively reserving frontier parameter-scaled models for complex queries. Most existing routing proposals rely on *a priori* heuristics—such as static domain difficulty rankings, prompt token length, and lexical reasoning markers—under the working hypothesis that small models reliably suffice for broad classes of everyday user requests.

To empirically test this hypothesis, we constructed a standardized, category-balanced benchmark of **500 single-turn prompt tasks** drawn from the LMSYS Chatbot Arena conversations dataset, distributed evenly across four core domains: **Creative Generation** ($n=125$), **Factual Question Answering** ($n=125$), **Reasoning and Mathematics** ($n=125$), and **Passage Summarization** ($n=125$). Candidate responses from both models were generated under identical deterministic conditions ($T=0.0$, `max_tokens=4096`, `tools=None`). The resulting 1,000 outputs were deterministically evaluated using **`qwen/qwen3.8-27b`** at $T=0.0$ (`max_tokens=1024`) under pre-specified, category-tailored PASS/FAIL rubrics, validated against a 64-judgment blinded human calibration baseline.

The empirical findings challenge conventional routing assumptions:

1. **Marginal Scaling Advantage**: Parameter scaling from 20B to 120B yields an absolute overall PASS rate increase of **+9.8 percentage points** (66.0% vs. 75.8%, study-wide McNemar exact $p = 6.405 \times 10^{-7}$). However, this capability gain is heavily concentrated in specific domains: the 120B model significantly outperforms the 20B model in **Creative** tasks ($\Delta = +21.6\%$, BH-FDR $q = 1.013 \times 10^{-4}$) and **Factual QA** ($\Delta = +7.2\%$, BH-FDR $q = 0.0449$). In contrast, in **Reasoning/Math** ($\Delta = +7.2\%$, BH-FDR $q = 0.1045$) and **Summarization** ($\Delta = +3.2\%$, BH-FDR $q = 0.5235$), **no statistically significant difference was detected after multiplicity correction**.
2. **Four-Cell Discordance**: Out of 500 matched prompts, **306 (61.2%)** prompts succeed under both models (Cell A), and **97 (19.4%)** prompts remain **unresolved by either evaluated model** (Cell D). Across the 97 discordant prompts, the large model rescues a small-model failure in **73 cases** (Cell B, 14.6%), whereas small-model capability inversion occurs in **24 cases** (Cell C, 4.8%), establishing an empirical rescue-to-inversion odds ratio of **$3.042$**.
3. **Heuristic Router Inversion**: A static heuristic router combining domain priors ($w_{\text{cat}}=0.40$), prompt length ($w_{\text{len}}=0.35$), and reasoning markers ($w_{\text{reason}}=0.25$) fails to achieve a Pareto-optimal operating point. At balanced traffic split ($\theta = 0.45$), the heuristic router achieved an observed pass rate of **68.4%** at a cost of **\$0.23124**, underperforming a naive Random 50/50 baseline (**70.9%** expected pass rate, **\$0.22604** cost) in both observed quality and expenditure. As detailed in Section 4.2, this comparison is descriptive rather than a formal hypothesis test, serving as evidence of observed heuristic underperformance on this benchmark rather than proof of statistically significant inferiority. This underperformance stems from an empirical **domain prior inversion**: human intuition assigned the lowest difficulty prior to creative tasks and the highest to math, whereas the small model empirically exhibited its lowest success rate in creative generation (49.6%) and its highest in mathematics (77.6%).
4. **Theoretical Upper Bound**: A retrospective Oracle router that perfectly selects the cost-minimal passing model achieves an **80.6% PASS rate** with **33.17% cost savings** (\$0.17844). However, this represents an unachievable hindsight upper bound rather than an operational routing strategy.

---

## 1. Experimental Methodology & Pre-Evaluation Calibration

### 1.1 Benchmark Design & Provenance

The evaluation corpus comprises exactly 500 prompts sampled from the LMSYS Chatbot Arena dataset, filtered for English single-turn user queries and excluding pure software code-generation tasks. Prompts were partitioned equally across four domains ($n=125$ each):
- **`creative`**: Open-ended and constrained writing tasks (e.g., poetry, narrative fiction, rhetorical dialogue, style mimicry) evaluated against a four-part rubric requiring compliance with explicit structural constraints, persona/tone consistency, thematic coherence, and absence of degenerative repetition.
- **`factual_qa`**: Closed-domain and open-domain knowledge queries paired with verified factual ground-truth references.
- **`reasoning_math`**: Multi-step mathematical calculations, word problems, and formal logical puzzles paired with verified step-by-step solutions and exact terminal answers.
- **`summarization`**: Text summarization tasks partitioned into 50 independent reference summaries and 75 assisted reference summaries equipped with 3–5 indispensable key aspects.

All benchmark artifacts were frozen under cryptographic SHA-256 digests prior to evaluation execution:
- `data/prompts.json`: `a9214823cb8fdc0586f5fb2fb88ac29eeebbdf7d7b70da318be495eae8b8ce03`
- `data/references.json`: `b1531df0fac52057da5b70e2279fc87eb6475236d194234775fae1231b79e9f3`
- `data/prompts_manifest.json`: `45d927529bab7e09dd18e536c64ea52bd84bd7f415dd506827f9f863c19d90f5`

### 1.2 Candidate Generation & Terminal Failure Accounting

Candidate models were executed via the Groq API under zero-temperature greedy decoding ($T=0.0$, `max_tokens=4096`, `tools=None`). Candidate model execution yielded exactly 1,000 JSON response files on disk (500 per model).

Before passing candidate outputs to the automated judge, an exhaustive terminal-failure audit was conducted:
1. **Empty-Text Completions**: In 38 instances, `openai/gpt-oss-20b` exhausted its 4,096-token generation ceiling emitting strictly whitespace/newline characters (`finish_reason="length"` with zero substantive text). These were categorized as terminal candidate failures (`empty_text_generation`, Auto-FAIL).
2. **Tool-Use API Rejections**: In 2 instances, `openai/gpt-oss-20b` attempted invalid tool invocations that triggered HTTP 400 API rejections. These were categorized as terminal candidate failures (`tool_use_api_rejection`, Auto-FAIL).
3. **Repetitive Degeneracy Screening**: Both models were screened for degenerative cyclic looping using an automated screening pipeline (compression ratio $\ge 4.0$, line repetition ratio $\ge 0.50$, 4-gram diversity $\le 0.50$) followed by manual verification of every candidate response:
   - For `openai/gpt-oss-20b`, exactly **8 responses** (1.6%) exhibited confirmed pathological generation loops (e.g., prompt `97ec5b57...` repeating a 6-date sequence 94 times across 563 lines). These were classified as `CANDIDATE_DEGENERATE` (FAIL). Eleven additional flagged responses hitting length limits were manually confirmed to be non-cyclic, rich technical implementations and were retained for evaluator scoring.
   - For `openai/gpt-oss-120b`, exactly **1 response** (0.2%, prompt `97ec5b57...`) exhibited cyclic degeneracy (compression ratio 93.81, 4-gram diversity 0.012) and was classified as `CANDIDATE_DEGENERATE` (FAIL).
   - In total, 48 20B candidate responses (9.6%) and 1 120B candidate response (0.2%) were classified as terminal candidate failures.

### 1.3 Cost Model Accounting

Inference costs were calculated based on published Groq token rates:
- `openai/gpt-oss-20b`: \$0.075 per 1M prompt tokens; \$0.300 per 1M completion tokens.
- `openai/gpt-oss-120b`: \$0.150 per 1M prompt tokens; \$0.600 per 1M completion tokens.

Every terminal failure—including empty-text generations and degeneracies that reached 4,096 tokens—was accounted for using its recorded token consumption. Across the 500 prompts:
- Full 20B candidate evaluation cost: **\$0.18506** (averaging \$0.000370 per query).
- Full 120B candidate evaluation cost: **\$0.26701** (averaging \$0.000534 per query).
- Total published token outlay across 1,000 evaluations: **\$0.45207**. (Actual marginal cash expenditure was \$0.00 within Groq's developer tier).

### 1.4 Evaluator Judge & Blinded Human Validation

The automated evaluator judge, **`qwen/qwen3.8-27b`**, was executed at $T=0.0$ with `max_tokens=1024` using strict verdict-first parsing (`VERDICT: PASS` or `VERDICT: FAIL`). Across all 1,000 evaluations (comprising 951 evaluated by the Qwen judge and 49 candidate-side terminal failures), zero records were unparseable or lost to evaluator errors, with all terminal failures accounted for deterministically.

> [!NOTE]
> **Evaluator Token Limit Reconciliation (`max_tokens=1024`)**: While early design and pilot proposals initially explored a 150-token cap for concise verdict generation, the finalized Phase 3 evaluation pipeline froze `max_tokens=1024` to permit complete, untruncated rationale critiques before or after the machine-readable verdict. Verification across the 1,000 finalized evaluation records on disk confirms that 359 evaluations generated between 151 and 1,024 completion tokens (mean completion tokens = 172.8, 90th percentile = 289.1 tokens). A 150-token limit would have truncated over 37% of the evaluator rationales. All 1,000 evaluations completed with zero unparseable or truncated verdict failures under this 1,024-token setting.

To calibrate evaluator reliability, a pre-registered **blinded human validation study** was conducted across 32 randomly sampled benchmark prompts (8 per domain) evaluated across both candidate models, yielding exactly **64 candidate-response judgments**:
- **Strict Rubric Evaluation**: The human researcher agreed with the automated judge on **64 / 64 judgments** (**100.0% agreement**, Cohen's $\kappa = \mathbf{1.0000}$).
- **Charitable Sensitivity Variant**: On prompt `84fa8433...` (Factual QA), `openai/gpt-oss-20b` provided the correct factual answer in its opening sentence but subsequently entered a repetitive generation loop repeating `*The Simpsons*-style` 341 times. The automated judge marked the response as PASS because the factual statement met the factual rubric, explicitly noting the trailing error in its critique. Under a charitable variant overlooking tail degradation, agreement was **62 / 64** (**96.9% agreement**, Cohen's $\kappa = \mathbf{0.9036}$). This finding was documented as an evaluator rubric limitation under tail repetition; the main-study record was frozen under the candidate degeneracy protocol.

---

## 2. Four-Cell Paired Contingency Analysis

Because both models were evaluated on the identical set of 500 prompts, candidate outcomes form a matched $2 \times 2$ contingency matrix. Following our pre-registered classification schema:
- **Cell A (PASS / PASS)**: Prompts resolved successfully by both models. The 20B model is sufficient; routing to 20B preserves performance while minimizing cost.
- **Cell B (FAIL / PASS)**: Prompts failed by 20B but rescued by 120B. These represent the genuine capability surplus of the larger model.
- **Cell C (PASS / FAIL)**: Prompts passed by 20B but failed by 120B. These represent small-model capability inversions where 120B underperforms.
- **Cell D (FAIL / FAIL)**: Prompts failed by both models. These tasks are **unresolved by either evaluated model** under our strict rubric criteria. Routing to 20B minimizes cost on these unresolvable queries.

```
                     openai/gpt-oss-120b
                     PASS            FAIL
                 +---------------+---------------+
           PASS  |    Cell A     |    Cell C     |
openai/          |  306 (61.2%)  |   24 (4.8%)   |  Total 20B PASS: 330 (66.0%)
gpt-oss-20b      +---------------+---------------+
           FAIL  |    Cell B     |    Cell D     |
                 |   73 (14.6%)  |   97 (19.4%)  |  Total 20B FAIL: 170 (34.0%)
                 +---------------+---------------+
                 Total 120B PASS: Total 120B FAIL:
                   379 (75.8%)     121 (24.2%)
```

### Table 1: Study-Wide Four-Cell Paired Performance Matrix ($N = 500$)

| Cell | 20B Verdict | 120B Verdict | Count ($N=500$) | Percentage | Semantic Role in Routing Policy |
| :--- | :---: | :---: | :---: | :---: | :--- |
| **Cell A** | PASS | PASS | **306** | 61.2% | Small model sufficiency; routing to 20B cuts cost at quality parity. |
| **Cell B** | FAIL | PASS | **73** | 14.6% | Large model superiority; 120B required to rescue small-model failure. |
| **Cell C** | PASS | FAIL | **24** | 4.8% | Small-model inversion; 20B succeeds where 120B fails. |
| **Cell D** | FAIL | FAIL | **97** | 19.4% | Unresolved by either evaluated model under strict rubric. |

### 2.1 Paired Concordance & Discordance Metrics

- **Concordant Prompts ($A + D$)**: Exactly **403 / 500 (80.6%)** of prompts produce identical outcomes between the two models. For these queries, routing decisions have no impact on task pass status: 306 pass regardless of route, and 97 fail regardless of route.
- **Discordant Prompts ($B + C$)**: Exactly **97 / 500 (19.4%)** of prompts exhibit divergent model performance.
- **Discordant Odds Ratio ($B / C$)**: The ratio of large-model rescues to small-model inversions is:
  $$\text{OR}_{\text{paired}} = \frac{B}{C} = \frac{73}{24} \approx \mathbf{3.042}$$
  The 120B model is approximately three times more likely to rescue a failure of the 20B model than it is to fail on a prompt that the 20B model successfully resolved.
- **Study-Wide McNemar Test**: Evaluating the null hypothesis of marginal homogeneity ($H_0: P(B) = P(C)$):
  $$\chi^2 = \frac{(|B - C| - 1)^2}{B + C} = \frac{(|73 - 24| - 1)^2}{97} = \frac{48^2}{97} \approx 23.7526$$
  The exact two-sided binomial test yields $p = \mathbf{6.405 \times 10^{-7}}$. This confirms that the observed +9.8 percentage point advantage of the 120B model (75.8% vs. 66.0%) is statistically significant on this benchmark.

> [!NOTE]
> **Clarification on Concordant vs. Resolvable Sets**: Note that the count of concordant prompts ($A + D = 306 + 97 = 403$, 80.6%) and the count of resolvable prompts ($A + B + C = 306 + 73 + 24 = 403$, 80.6%) share the identical numerical count of 403. This equivalence occurs purely as an arithmetic property of this sample because the discordant pairs happen to sum exactly to the count of Cell D ($B + C = 73 + 24 = 97 = D$). However, they represent two conceptually distinct subsets of the benchmark:
> - **Concordant Subspace ($A \cup D$)**: Prompts where both models produce identical pass/fail outcomes, meaning that routing decisions have zero effect on task success (306 pass under both; 97 fail under both).
> - **Resolvable Subspace ($A \cup B \cup C$)**: Prompts where at least one evaluated model is capable of satisfying the rubric criteria, defining the active domain of candidate competence (403 prompts).

> [!IMPORTANT]
> **Generalization Guardrail**: This paired McNemar test specifically establishes that `openai/gpt-oss-120b` outperforms `openai/gpt-oss-20b` across the 500 prompts of this study. It does not establish that parameter scaling unconditionally guarantees performance gains across all model families, architectures, or unrepresented task domains.

---

## 3. Domain-Specific Model Performance & Hypothesis Testing

To examine whether parameter scaling benefits all domains uniformly, we analyzed paired model performance within each of the four 125-prompt domains. Multiple hypothesis testing across the four domain comparisons was controlled using the Benjamini-Hochberg False Discovery Rate (BH-FDR) procedure at $\alpha = 0.05$.

### Table 2: Category-Specific Model Performance, Four-Cell Distribution, and McNemar Tests

| Domain | Prompts | 20B PASS ($k/125$) | 120B PASS ($k/125$) | Delta ($\Delta P$) | Cell A | Cell B | Cell C | Cell D | McNemar Exact $p$ | BH-FDR $q$ | Significant ($\alpha=0.05$) |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **Creative** | 125 | 62 (49.6%) | 89 (71.2%) | **+21.6%** | 55 | 34 | 7 | 29 | $\mathbf{2.532 \times 10^{-5}}$ | $\mathbf{1.013 \times 10^{-4}}$ | **Yes** (120B wins) |
| **Factual QA** | 125 | 88 (70.4%) | 97 (77.6%) | **+7.2%** | 86 | 11 | 2 | 26 | $\mathbf{0.02246}$ | $\mathbf{0.04492}$ | **Yes** (120B wins) |
| **Reasoning / Math** | 125 | 97 (77.6%) | 106 (84.8%) | **+7.2%** | 91 | 15 | 6 | 13 | $0.07835$ | $0.10447$ | No |
| **Summarization** | 125 | 83 (66.4%) | 87 (69.6%) | **+3.2%** | 74 | 13 | 9 | 29 | $0.52347$ | $0.52347$ | No |
| **Study-Wide Total** | **500** | **330 (66.0%)** | **379 (75.8%)** | **+9.8%** | **306** | **73** | **24** | **97** | $\mathbf{6.405 \times 10^{-7}}$ | — | **Yes** |

![Figure 2: Empirical PASS Rate by Task Domain with 95% Wilson CIs](figures/figure2_category_performance.png)

![Figure 3: Four-Cell Paired Contingency Matrix and Domain Breakdown](figures/figure3_contingency_and_domains.png)

### 3.1 Domain Breakdown Insights

1. **Creative Generation**: Creative generation demonstrated the largest scaling effect in the study ($\Delta = +21.6\%$, McNemar $p = 2.532 \times 10^{-5}$, $q = 1.013 \times 10^{-4}$). The 120B model rescued 34 failures of the 20B model while suffering only 7 inversions ($B/C = 4.857$). Decomposing candidate outcomes reveals that 20B performance was severely depressed by **27 candidate-terminal failures** (empty generations and degeneracies). Among substantive, usable outputs, the 20B model achieved a 63.3% pass rate, indicating that small-model fragility in open-ended creative tasks is driven primarily by decoding instability under length constraints.
2. **Factual Question Answering**: The 120B model achieved a statistically significant +7.2 percentage point gain ($p = 0.02246$, $q = 0.04492$). Out of 125 prompts, 86 passed under both models (Cell A), 11 were rescued by 120B (Cell B), and only 2 inverted (Cell C), demonstrating that parameter scaling reliably improved rubric-based factual QA performance on this benchmark.
3. **Reasoning and Mathematics**: Although the 120B model improved observed accuracy by +7.2 percentage points (84.8% vs. 77.6%), no statistically significant difference was detected after multiplicity correction ($p = 0.07835$, $q = 0.10447$). Concordance was exceptionally high: 91 of 125 prompts passed under both models (Cell A). When small models successfully parse multi-step mathematical instructions, they frequently arrive at correct final terminal values.
4. **Summarization**: Summarization showed the smallest scaling delta in the study (+3.2%, 69.6% vs. 66.4%, $p = 0.52347$), with no statistically significant difference detected between models. Discordant outcomes were nearly balanced (13 Cell B vs. 9 Cell C), indicating that parameter scaling provided minimal marginal benefit for passage compression.

### 3.2 Summarization Split Sensitivity Analysis (50 Independent vs. 75 Assisted)

The 125 summarization prompts comprised two distinct reference styles: 50 prompts with independent reference summaries, and 75 prompts with assisted reference summaries incorporating 3–5 explicit key aspect requirements. We performed a sensitivity analysis to determine whether reference style influenced evaluator stringency or favored the larger model:

### Table 3: Summarization Sub-Split Performance & Sensitivity Analysis

| Sub-Split | Prompts ($N$) | 20B PASS ($k/n$) | 120B PASS ($k/n$) | Delta ($\Delta P$) | Cell A | Cell B | Cell C | Cell D | McNemar Exact $p$ |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **Independent References** | 50 | 42 (84.0%) | 41 (82.0%) | **-2.0%** | 37 | 4 | 5 | 4 | $1.0000$ |
| **Assisted References** | 75 | 41 (54.7%) | 46 (61.3%) | **+6.7%** | 37 | 9 | 4 | 25 | $0.2668$ |

- **Impact of Explicit Key Aspects**: The inclusion of explicit key aspect criteria significantly depressed absolute pass rates for both models:
  - 20B pass rate dropped from 84.0% to 54.7% (Fisher's exact test $p = 0.000897$, $\text{OR} = 4.354$).
  - 120B pass rate dropped from 82.0% to 61.3% (Fisher's exact test $p = 0.01718$, $\text{OR} = 2.872$).
- **Evaluating Model Advantage Across Reference Styles**: The paired difference between models was not statistically significant in either the independent reference subset (McNemar exact $p = 1.0000$) or the assisted reference subset (McNemar exact $p = 0.2668$). While these non-significant tests do not establish the complete absence of bias, they provide no empirical evidence that the inclusion of explicit key aspects systematically favored the larger parameter-scaled model.

---

## 4. Evaluation of Dynamic Routing Policies

### 4.1 Fixed Baselines vs. Heuristic Routing

To evaluate the operational utility of dynamic routing, we compare the heuristic router against three fixed baselines and a theoretical upper bound:
- **Always-120B ($\theta = 0.00$)**: Routes all traffic to the large model. Maximizes quality at maximum cost.
- **Always-20B ($\theta = 1.00$)**: Routes all traffic to the small model. Minimizes cost while sacrificing quality.
- **Random 50/50 Baseline**: Stochastically routes each query to either model with equal probability ($p=0.5$).
- **Oracle Ceiling (Hindsight Upper Bound)**: Retrospective upper bound that routes to 20B whenever Cell A or Cell C occurs, routes to 120B on Cell B, and routes to 20B on Cell D (cost-minimizing tie-break). **This is a non-deployable, counterfactual benchmark that assumes clairvoyant knowledge of execution outcomes**.

### Table 4: Baseline Policy Comparison ($N = 500$)

| Routing Policy | PASS Count ($k/500$) | Pass Rate (%) | Uncertainty Interval | Published Cost | Cost Savings vs. 120B | Quality Retention vs. 120B |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| **Always-120B** ($\theta = 0.0$) | 379 | 75.8% | 95% Wilson: [71.9%, 79.3%] | \$0.26701 | 0.00% | 100.00% |
| **Always-20B** ($\theta = 1.0$) | 330 | 66.0% | 95% Wilson: [61.7%, 70.0%] | \$0.18506 | 30.69%* | 87.07% |
| **Random 50/50 Baseline** | 354.5 | 70.9% | Algorithmic 95% CI: [69.0%, 72.8%]<br>Prompt Bootstrap 95% CI: [67.6%, 74.6%] | \$0.22604 | 15.35% | 93.54% |
| **Heuristic Router ($\theta = 0.45$)** | 342 | 68.4% | 95% Wilson: [64.2%, 72.3%] | \$0.23124 | 13.40% | 90.24% |
| **Oracle Ceiling (Hindsight)** | **403** | **80.6%** | 95% Wilson: [76.9%, 83.8%] | **\$0.17844** | **33.17%** | **106.33%** |

*\*Note on Bootstrap Cost Consistency: The full-sample point estimate for Always-20B cost savings is 30.69%. The 1,000-replicate non-parametric bootstrap mean is 30.59% (95% CI: [24.96%, 35.67%]). At $\theta = 0.00$, paired bootstrap savings are identically 0.00% across all replicates.*

### 4.2 Disaggregated Uncertainty Intervals for the Random 50/50 Baseline

Because the Random 50/50 baseline has a fractional expected PASS count ($\mathbb{E}[K] = 306 + 97 \times 0.5 = 354.5$), applying a naive Wilson interval treating $355$ as an observed binomial count is mathematically invalid. We report two formally derived, separate uncertainty intervals:
1. **Exact Algorithmic Randomization Interval (Fixed Prompts)**: Conditional on the fixed 500 benchmark prompts, outcomes on Cell A ($n=306$) and Cell D ($n=97$) are invariant to routing. Variance arises solely from the 97 discordant pairs:
   $$K \sim 306 + \text{Binomial}(97, 0.5), \quad \text{SE} = \frac{\sqrt{97 \times 0.25}}{500} \approx 0.985\%$$
   The exact 95% binomial interval spans **345 to 364 passes**, corresponding to **[69.00%, 72.80%]**.
2. **Superpopulation Prompt Bootstrap Interval**: Accounting for prompt-sampling variability from the underlying task distribution via 1,000 paired non-parametric resamples yields **[67.60%, 74.60%]** ($\text{SE} = 1.78\%$).

> [!WARNING]
> **Baseline Hypothesis Interpretation**: Neither the algorithmic randomization interval nor the prompt bootstrap interval constitutes a formal two-sample hypothesis test comparing the deterministic heuristic router to random routing. The comparison between the heuristic router (68.4% observed pass rate, \$0.23124 cost) and the random baseline (70.9% expected pass rate, \$0.22604 cost) is reported strictly as a descriptive benchmark evaluation demonstrating observed underperformance on this benchmark, not by itself proof of statistically significant inferiority.

---

## 5. Router Threshold Sweep across $\theta \in [0.0, 1.0]$

The heuristic router estimates prompt difficulty $S(x) \in [0, 1]$ via the frozen linear formula:
$$S(x) = 0.40 \cdot f_{\text{cat}}(x) + 0.35 \cdot f_{\text{len}}(x) + 0.25 \cdot f_{\text{reason}}(x)$$
where category priors are assigned as $\text{creative}=0.20$, $\text{factual\_qa}=0.40$, $\text{summarization}=0.60$, and $\text{reasoning\_math}=0.80$. A query is routed to `openai/gpt-oss-20b` if $S(x) \le \theta$, and to `openai/gpt-oss-120b` otherwise.

We swept $\theta$ across 21 increments from $0.00$ to $1.00$. To eliminate past metric conflation, we report two distinct evaluative measures on the 403 resolvable tasks ($A+B+C$):
- **Resolvable Task Pass Rate**: The proportion of the 403 resolvable prompts where the routed model outputs PASS:
  $$\text{Pass}_{\text{res}}(\theta) = \frac{\sum_{i \in A \cup B \cup C} \mathbb{I}(\text{RoutedModel}_i \text{ PASS})}{403}$$
- **Oracle Cost-Target Agreement**: The proportion of the 403 resolvable prompts where the router selected the cost-minimizing passing model:
  $$\text{Agr}_{\text{oracle}}(\theta) = \frac{\sum_{i \in A \cup B \cup C} \mathbb{I}(\text{SelectedModel}_i = \text{OracleTarget}_i)}{403}$$
  *Oracle Tie-Breaking Rule*: On Cell A ($n=306$, both pass), the Oracle targets 20B to minimize token cost. On Cell B ($n=73$), it targets 120B. On Cell C ($n=24$), it targets 20B. Cell D ($n=97$, both fail) is excluded from resolvable metrics because neither model satisfies criteria.

### Table 5: 21-Threshold Sweep Across Heuristic Routing Parameter $\theta$

| $\theta$ | % to 20B | % to 120B | Routed PASS ($k/500$) | Pass Rate (%) | 95% Wilson CI | Total Cost | Cost Savings vs. 120B | **Resolvable Task Pass Rate** ($k/403$) | **Oracle Cost-Target Agreement** ($k/403$) |
| :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **0.00** | 0.0% | 100.0% | 379 | 75.8% | [71.9%, 79.3%] | \$0.26701 | 0.00% | **94.04%** (379/403) | **18.11%** (73/403) |
| **0.05** | 0.0% | 100.0% | 379 | 75.8% | [71.9%, 79.3%] | \$0.26701 | 0.00% | **94.04%** (379/403) | **18.11%** (73/403) |
| **0.10** | 0.0% | 100.0% | 379 | 75.8% | [71.9%, 79.3%] | \$0.26701 | 0.00% | **94.04%** (379/403) | **18.11%** (73/403) |
| **0.15** | 0.0% | 100.0% | 379 | 75.8% | [71.9%, 79.3%] | \$0.26701 | 0.00% | **94.04%** (379/403) | **18.11%** (73/403) |
| **0.20** | 3.6% | 96.4% | 375 | 75.0% | [71.0%, 78.6%] | \$0.26583 | 0.44% | **93.05%** (375/403) | **20.10%** (81/403) |
| **0.25** | 10.8% | 89.2% | 368 | 73.6% | [69.6%, 77.3%] | \$0.26490 | 0.79% | **91.32%** (368/403) | **23.33%** (94/403) |
| **0.30** | 34.2% | 65.8% | 351 | 70.2% | [66.0%, 74.0%] | \$0.24619 | 7.80% | **87.10%** (351/403) | **35.73%** (144/403) |
| **0.35** | 42.4% | 57.6% | 345 | 69.0% | [64.8%, 72.9%] | \$0.23452 | 12.17% | **85.61%** (345/403) | **39.21%** (158/403) |
| **0.40** | 47.4% | 52.6% | 346 | 69.2% | [65.0%, 73.1%] | \$0.23301 | 12.73% | **85.86%** (346/403) | **43.92%** (177/403) |
| **0.45** | 49.0% | 51.0% | 342 | 68.4% | [64.2%, 72.3%] | \$0.23124 | 13.40% | **84.86%** (342/403) | **43.18%** (174/403) |
| **0.50** | 56.0% | 44.0% | 343 | 68.6% | [64.4%, 72.5%] | \$0.22640 | 15.21% | **85.11%** (343/403) | **49.63%** (200/403) |
| **0.55** | 64.0% | 36.0% | 338 | 67.6% | [63.4%, 71.6%] | \$0.22178 | 16.94% | **83.87%** (338/403) | **56.33%** (227/403) |
| **0.60** | 74.8% | 25.2% | 337 | 67.4% | [63.2%, 71.4%] | \$0.21179 | 20.68% | **83.62%** (337/403) | **63.28%** (255/403) |
| **0.65** | 85.6% | 14.4% | 333 | 66.6% | [62.4%, 70.6%] | \$0.19837 | 25.71% | **82.63%** (333/403) | **70.47%** (284/403) |
| **0.70** | 95.6% | 4.4% | 330 | 66.0% | [61.7%, 70.0%] | \$0.19077 | 28.55% | **81.89%** (330/403) | **77.92%** (314/403) |
| **0.75** | 99.8% | 0.2% | 330 | 66.0% | [61.7%, 70.0%] | \$0.18561 | 30.49% | **81.89%** (330/403) | **81.89%** (330/403) |
| **0.80** | 100.0% | 0.0% | 330 | 66.0% | [61.7%, 70.0%] | \$0.18506 | 30.69% | **81.89%** (330/403) | **81.89%** (330/403) |
| **0.85** | 100.0% | 0.0% | 330 | 66.0% | [61.7%, 70.0%] | \$0.18506 | 30.69% | **81.89%** (330/403) | **81.89%** (330/403) |
| **0.90** | 100.0% | 0.0% | 330 | 66.0% | [61.7%, 70.0%] | \$0.18506 | 30.69% | **81.89%** (330/403) | **81.89%** (330/403) |
| **0.95** | 100.0% | 0.0% | 330 | 66.0% | [61.7%, 70.0%] | \$0.18506 | 30.69% | **81.89%** (330/403) | **81.89%** (330/403) |
| **1.00** | 100.0% | 0.0% | 330 | 66.0% | [61.7%, 70.0%] | \$0.18506 | 30.69% | **81.89%** (330/403) | **81.89%** (330/403) |

![Figure 1: Cost vs. Pass Rate Pareto Frontier across Routing Policies](figures/figure1_pareto_frontier.png)

### 5.1 Non-Parametric Bootstrap Pareto Analysis (1,000 Resamples)

To quantify sampling uncertainty along the empirical trade-off curve, 1,000 non-parametric bootstrap resamples (seed `42`, preserving paired prompt outcomes) were executed. Within each bootstrap replicate $b$, the cost savings of threshold $\theta$ was computed relative to that replicate's own Always-120B baseline cost:
$$\text{Savings}^{(b)}(\theta) = \frac{\text{Cost}^{(b)}_{120\text{B}} - \text{Cost}^{(b)}(\theta)}{\text{Cost}^{(b)}_{120\text{B}}} \times 100\%$$
This formulation ensures exact pairing, guaranteeing that savings at $\theta = 0.00$ are identically $0.00\%$ across all replicates.

### Table 6: Bootstrap Mean & 95% Confidence Intervals for Key Sweep Thresholds (Directly from `phase4_statistical_results.json`)

| Threshold $\theta$ | Bootstrap Mean Pass Rate | 95% CI Pass Rate | Bootstrap Mean Cost | 95% CI Cost | Bootstrap Mean Cost Savings | 95% CI Cost Savings |
| :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **$\theta = 0.00$** | 75.92% | [72.20%, 79.80%] | \$0.26679 | [\$0.24284, \$0.29020] | **0.00%** | **[0.00%, 0.00%]** |
| **$\theta = 0.35$** | 69.13% | [65.00%, 73.20%] | \$0.23441 | [\$0.21281, \$0.25502] | **12.11%** | **[6.94%, 16.99%]** |
| **$\theta = 0.45$** | 68.55% | [64.40%, 72.60%] | \$0.23124 | [\$0.21008, \$0.25116] | **13.28%** | **[7.46%, 18.90%]** |
| **$\theta = 0.50$** | 68.74% | [64.60%, 72.80%] | \$0.22644 | [\$0.20601, \$0.24615] | **15.08%** | **[9.35%, 20.60%]** |
| **$\theta = 0.65$** | 66.73% | [62.60%, 71.00%] | \$0.19841 | [\$0.18144, \$0.21741] | **25.58%** | **[19.58%, 30.66%]** |
| **$\theta = 0.75$** | 66.13% | [62.00%, 70.40%] | \$0.18557 | [\$0.17027, \$0.20179] | **30.39%** | **[24.82%, 35.54%]** |
| **$\theta = 1.00$** | 66.13% | [62.00%, 70.40%] | \$0.18502 | [\$0.16972, \$0.20134] | **30.59%** | **[24.96%, 35.67%]** |

> [!NOTE]
> **Reconciliation Note on Bootstrap Cost Savings**: In Table 6, Cost Savings is reported as the sample mean and percentile confidence interval of the paired percentage savings computed within each of the 1,000 bootstrap resamples ($\text{Mean}(\frac{\text{Cost}_{120\text{B}}^{(b)} - \text{Cost}_\theta^{(b)}}{\text{Cost}_{120\text{B}}^{(b)}} \times 100\%)$), drawn directly from `phase4_statistical_results.json`. This is mathematically distinct from the ratio of the sample mean costs ($\frac{\text{Mean}(\text{Cost}_{120\text{B}}) - \text{Mean}(\text{Cost}_\theta)}{\text{Mean}(\text{Cost}_{120\text{B}})}$), which would yield slightly different figures (e.g., 12.14%, 13.33%, 15.13%). Preserving replicate-level pairing respects the covariance between policy costs and baseline costs on each resample and guarantees exact 0.00% savings at $\theta = 0.00$ across all replicates.

---

## 6. Analytical Discussion: The Mechanism of Heuristic Underperformance

A central finding of this investigation is that the heuristic router underperformed a naive Random 50/50 baseline in both observed pass rate and expenditure at balanced traffic ($\theta = 0.45$: 68.4% pass, \$0.23124 cost vs. 70.9% expected pass, \$0.22604 cost). As emphasized in Section 4.2, this comparison is descriptive rather than a formal hypothesis test, serving as evidence of observed heuristic underperformance on this benchmark rather than proof of statistically significant inferiority. Inspecting the query routing ledger reveals three distinct structural mechanisms responsible for this underperformance:

### 6.1 Domain Prior Inversion

The most consequential driver of heuristic failure was the inverted ranking of domain difficulty priors ($w_{\text{cat}} = 0.40$). The heuristic formula assigned priors based on conventional human intuition regarding cognitive complexity:
$$\text{Heuristic Priors: } \text{Creative (0.20)} < \text{Factual QA (0.40)} < \text{Summarization (0.60)} < \text{Reasoning/Math (0.80)}$$

Empirically, small-model task competence followed an almost perfectly inverted ordering:
$$\text{Empirical 20B Pass Rate: } \text{Reasoning/Math (77.6\%)} > \text{Factual QA (70.4\%)} > \text{Summarization (66.4\%)} > \text{Creative (49.6\%)}$$

Because Creative tasks received the lowest difficulty prior ($0.20$), the router systematically dispatched creative prompts to the small model (`openai/gpt-oss-20b`). However, Creative generation was precisely where the small model was weakest, suffering from 27 terminal candidate failures and a high failure rate ($n=63$ failures out of 125). Conversely, Reasoning/Math tasks received the highest difficulty prior ($0.80$), causing the router to dispatch math prompts to the expensive 120B model—even though the 20B model successfully solved 77.6% of these tasks on its own (Cell A: 91 / 125 prompts).

> [!NOTE]
> **Methodological Framing Guardrail**:
> *"The observed category PASS-rate ordering differs substantially from the researcher-specified router priors, and this difference persists after decomposing candidate-terminal failures from evaluator-scored outputs."* Even among substantive, non-degenerate outputs, the 20B creative pass rate was only 63.3%, still substantially lower than its 77.6% pass rate in reasoning and math.

### 6.2 Token Length as a Misleading Proxy for Model Sufficiency

The second feature in the heuristic formula was prompt character length density ($w_{\text{len}} = 0.35$). In user interaction benchmarks, prompt length is often uncorrelated or negatively correlated with underlying task difficulty:
- In `factual_qa`, long prompts frequently contain extensive background context, quoted extracts, or conversational preambles that make factual retrieval *easier* for small models by providing rich semantic anchors.
- Conversely, extremely short prompts in `creative` (e.g., *"Write a rhyming limerick about quantum mechanics with strict AABBA meter"*) impose severe, dense constraints that small models struggle to satisfy without looping or violating meter.
By penalizing prompt length, the router misrouted context-rich factual queries to 120B and dispatched terse, highly constrained creative prompts to 20B.

### 6.3 Absence of Empirical Calibration

Heuristic routers lack a learned loss function. Whereas learned routing models (e.g., matrix factorization, BERT-based classifiers, or causal reward predictors) calibrate decision boundaries against empirical performance logs, static heuristics rely on unverified proxy features. When heuristic proxy assumptions contradict empirical model capabilities, dynamic routing achieves worse cost-quality trade-offs than simple stochastic allocation.

---

## 7. Methodological Limitations

To maintain academic rigor and transparent reporting, several limitations of this empirical study must be emphasized:

1. **Evaluator Dependence**: All main-study candidate evaluations were conducted by an automated LLM judge (`qwen/qwen3.8-27b`). Although the 64-judgment human validation confirmed strong inter-rater reliability ($\kappa = 1.0000$ strict, $\kappa = 0.9036$ charitable), automated judges possess inherent stylistic biases. Specifically, case inspection of prompt `84fa8433...` confirmed that Qwen's factual QA rubric evaluates factual correctness strictly and does not penalize tail repetition, requiring external candidate degeneracy screening to maintain dataset hygiene.
2. **Human Calibration Sample Size**: The blinded human calibration sample was bounded at 64 candidate-response judgments (32 prompts $\times$ 2 models, 16 per domain). While sufficient to detect catastrophic judge misalignment and estimate Cohen's $\kappa$, larger human validation samples are desirable to detect subtle, low-frequency evaluator misalignments.
3. **Model Pair Specificity**: The empirical findings apply specifically to the evaluated model pair: `openai/gpt-oss-20b` and `openai/gpt-oss-120b`. These models share architectural lineage and training corpora. Different model pairings (e.g., routing between distinct model families like Llama 3 and Mistral, or between reasoning models like DeepSeek-R1 and standard chat models) may exhibit different discordance structures, rescue ratios, or failure modes.
4. **Benchmark Representativeness**: The 500 prompts were drawn from single-turn English conversations in the LMSYS Chatbot Arena. While diverse and balanced across four domains, the benchmark excludes multi-turn dialogues, real-time tool/function-calling execution, retrieval-augmented generation (RAG) pipelines, and code synthesis tasks.
5. **Oracle Non-Deployability**: The Oracle router reported in Tables 4 and 5 reflects a retrospective hindsight ceiling that assumes perfect knowledge of candidate execution. It must not be cited as an achievable deployment strategy.

---

## 8. Reproducibility Appendix & Audit Trail

All experimental assets, candidate outputs, evaluator judgements, and statistical analysis scripts are frozen and publicly verifiable.

### 8.1 Cryptographic Digests of Core Assets

| File Path | Description | Frozen SHA-256 Digest |
| :--- | :--- | :--- |
| `data/prompts.json` | 500 benchmark prompts with heuristic scores | `a9214823cb8fdc0586f5fb2fb88ac29eeebbdf7d7b70da318be495eae8b8ce03` |
| `data/references.json` | Category reference criteria and ground truth | `b1531df0fac52057da5b70e2279fc87eb6475236d194234775fae1231b79e9f3` |
| `data/prompts_manifest.json` | Full benchmark provenance manifest | `45d927529bab7e09dd18e536c64ea52bd84bd7f415dd506827f9f863c19d90f5` |
| `data/public_benchmark_manifest.json` | Public LMSYS-compliant redistribution ledger | `13aa93eb83da966f9a06ee526b70c326e5564883d6a0ec163b7cff5b62b08051` |
| `data/human_validation_results.json` | 64-judgment blinded human calibration ledger | `6452fdbad79a61e7127d1487bb83c4820dc743c3d52623e1dc28555883726aa1` |
| `data/phase4_statistical_results.json` | Corrected statistical results and bootstrap data | `c244b2f90580be47ddac82195b65ad3784f3b2f56da60bc086e42977648889f8` |
| `scripts/run_phase4_statistical_analysis.py` | Complete statistical analysis pipeline | `b6a70e736a3acdac57754d303b9ee78c7d5d0d02bf000959107a5c05d18432e0` |
| `scripts/test_phase4_regression.py` | 7-point Phase 4 regression test suite | `6f48ac981906efb7f2241748d07945e7e438f483e45b1b6af9920960cac8fa9d` |
| `scripts/generate_thesis_figures.py` | Publication figure generation script | Verified in repository |

### 8.2 Execution Parameters

- **Candidate Generation**:
  - `openai/gpt-oss-20b`: Temperature $0.0$, `max_tokens=4096`, `top_p=1.0`, `presence_penalty=0.0`, `frequency_penalty=0.0`, tools disabled.
  - `openai/gpt-oss-120b`: Temperature $0.0$, `max_tokens=4096`, `top_p=1.0`, `presence_penalty=0.0`, `frequency_penalty=0.0`, tools disabled.
- **Evaluator Judge**:
  - `qwen/qwen3.8-27b`: Temperature $0.0$, `max_tokens=1024`, verdict-first system prompts with domain-specific rubrics.
- **Statistical Pipeline**:
  - Exact two-sided binomial McNemar tests using `scipy.stats.binomtest`.
  - Multiple testing adjustment via Benjamini-Hochberg False Discovery Rate ($m=4$ domain tests).
  - Non-parametric bootstrap: 1,000 resamples, seed `42`, prompt-level paired resampling.
  - Binomial confidence intervals via Wilson score method ($z = 1.95996$).

### 8.3 Exact Reproduction Commands

```bash
# 1. Clone repository and navigate to root
cd llm-routing-study

# 2. Verify frozen asset hashes and 1,000 evaluation records
python scripts/audit_phase3_completion.py

# 3. Execute Phase 4 statistical test suite
python scripts/run_phase4_statistical_analysis.py

# 4. Run automated 7-point regression verification
python scripts/test_phase4_regression.py

# 5. Generate publication figures (saved to figures/)
python scripts/generate_thesis_figures.py
```
