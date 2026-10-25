# Project 2 - 40-Prompt Model-Selection Pilot Report

**Generated:** 2026-09-13 14:54:48

> **Methodological Boundary:** This is a feasibility and capability-gap pilot for 40 researcher-reviewed
> candidate prompts (10 per category). It is NOT a statistically representative sample of LMSYS Chatbot Arena,
> and no quality scoring or routing claims are made.

## 1. Experimental Configuration
- **Small Model:** `openai/gpt-oss-20b` via `groq`
- **Large Candidate:** `nvidia/nemotron-3-ultra-550b-a55b-20260604:free` via `openrouter`
- **Temperature:** `0.0` (deterministic)
- **Max Output Tokens:** `1024`
- **Rate Delays:** Groq: 2.5s/call | OpenRouter: 2.0s/call

## 2. Category Distribution
| Category | Prompt Count |
|---|---|
| `factual_qa` | 10 |
| `summarization` | 10 |
| `reasoning_math` | 10 |
| `creative` | 10 |

## 3. SMALL Model Performance: `openai/gpt-oss-20b` (groq)
- **Success Rate:** 39/40 (1 errors, 3 retries)

### Aggregate Statistics
| Metric | Total | Min | Median | Mean | Max |
|---|---|---|---|---|---|
| **Latency (s)** | 99.17 | 0.32 | 1.38 | 2.54 | 7.74 |
| **Input Tokens** | 6682 | 76 | 98 | 171.33 | 538 |
| **Output Tokens** | 27294 | 35 | 876 | 699.85 | 1024 |
| **Total Tokens** | 33976 | 121 | 988 | 871.18 | 1562 |
| **Response Chars** | 45658 | 0 | 719 | 1170.72 | 4318 |

### Per-Category Breakdown
| Category | N | Avg Latency (s) | Avg Output Tokens | Avg Response Chars |
|---|---|---|---|---|
| `factual_qa` | 10 | 0.93s | 510.7 | 818.8 |
| `summarization` | 10 | 1.02s | 680.9 | 1284.0 |
| `reasoning_math` | 9 | 3.11s | 686.4 | 885.9 |
| `creative` | 10 | 5.17s | 920.0 | 1665.7 |

### Model-Specific Observations & Anomalies
- Model returned by API: openai/gpt-oss-20b
- Empty responses returned on prompt IDs: ['58210e39b3fd4441a2bd4a518bb44c2d', 'c284f2bf6c7243b5aad2b5539fec9866', '119b348113a84b44a1fed88ac181fdc2', '61320a80c6e149559d74b4de88b6233a', 'b0c343364ffb458083fed7b573bfce0f', '4e6446c00a2447d0ad09c58ce942e2c5', '859c561d217746fb865dc5328152abb5']
- Model generates reasoning tokens (total: 15719, avg: 403.1)

## 3. LARGE Model Performance: `nvidia/nemotron-3-ultra-550b-a55b-20260604:free` (openrouter)
- **Success Rate:** 40/40 (0 errors, 10 retries)

### Aggregate Statistics
| Metric | Total | Min | Median | Mean | Max |
|---|---|---|---|---|---|
| **Latency (s)** | 3578.97 | 53.09 | 75.26 | 89.47 | 246.37 |
| **Input Tokens** | 5044 | 21 | 43.5 | 126.1 | 560 |
| **Output Tokens** | 28205 | 21 | 960.5 | 705.12 | 1024 |
| **Total Tokens** | 33249 | 44 | 1014.0 | 831.23 | 1584 |
| **Response Chars** | 89960 | 12 | 2802.5 | 2249.0 | 4367 |

### Per-Category Breakdown
| Category | N | Avg Latency (s) | Avg Output Tokens | Avg Response Chars |
|---|---|---|---|---|
| `factual_qa` | 10 | 68.01s | 579.5 | 1999.3 |
| `summarization` | 10 | 106.8s | 673.7 | 2143.4 |
| `reasoning_math` | 10 | 90.65s | 650.7 | 1518.3 |
| `creative` | 10 | 92.44s | 916.6 | 3335.0 |

### Model-Specific Observations & Anomalies
- Model returned by API: nvidia/nemotron-3-ultra-550b-a55b:free
- Model generates reasoning tokens (total: 6315, avg: 157.9)
