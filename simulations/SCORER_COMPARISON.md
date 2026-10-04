# Llama 3 8B vs Jev: six research-scout runs

Six live runs of `research_scout` on 4 Oct 2026, 19:28–19:34 UTC. Three used `SCORER=llama` (local Ollama `llama3:latest`, 8.0B, Q4_0). Three used `SCORER=jev` (`jev-latest`, resolved to `jev-1.13.0`). Search planning used Llama 3 on every run. Application source was left unchanged. Each run had its own `data/`, `results/`, `logs/`, and `metrics/` directory so profiles and result files did not mix with existing checkouts.

The package module is `research_scout`. That is the command these runs used.

## Profiles

The same five intake answers were piped for each persona, once per scorer.

| Run pair | Username | Domain | Interests and skills |
| --- | --- | --- | --- |
| `*-01-cs-swe-web-infra` | `swe-web-infra` | Computer Science / Software Engineering | Web infrastructure, databases, backend and frontend, API design, caching, distributed web services |
| `*-02-ai-engineer` | `ai-engineer` | AI Engineering | LLMs, RAG, agents, evaluation, inference optimization, vector databases, PyTorch |
| `*-03-data-engineer` | `data-engineer` | Data Engineering | Databases, ML data systems, analytics, warehousing, ETL, data lakes |

Exact prompt text is in `simulations/profiles/`.

## Where the artifacts are

Each run directory holds the files the app wrote (`metrics/run-<id>.json`, `logs/session-<id>.log`, `results/<username>.csv`). Copies with stable names are in `simulations/records/`:

| Run | Metrics | Results |
| --- | --- | --- |
| Llama, software engineer | `records/llama-01-cs-swe-web-infra.metrics.json` | `records/llama-01-cs-swe-web-infra.results.csv` |
| Jev, software engineer | `records/jev-01-cs-swe-web-infra.metrics.json` | `records/jev-01-cs-swe-web-infra.results.csv` |
| Llama, AI engineer | `records/llama-02-ai-engineer.metrics.json` | `records/llama-02-ai-engineer.results.csv` |
| Jev, AI engineer | `records/jev-02-ai-engineer.metrics.json` | `records/jev-02-ai-engineer.results.csv` |
| Llama, data engineer | `records/llama-03-data-engineer.metrics.json` | `records/llama-03-data-engineer.results.csv` |
| Jev, data engineer | `records/jev-03-data-engineer.metrics.json` | `records/jev-03-data-engineer.results.csv` |

All six runs finished with `success: true`, 15 papers, 5 blogs, and zero paper shortfall. None entered the adjacent-search stage.

## How cost was priced

Local Ollama has no invoice. Every Llama token in these runs is priced as a hosted Llama 3 8B API call:

- **Input:** $0.05 per million tokens
- **Output:** $0.08 per million tokens

That is Groq’s published rate for `llama3-8b-8192`. The runs exported `COST_PER_MILLION_PROMPT_TOKENS=0.05` and `COST_PER_MILLION_COMPLETION_TOKENS=0.08`, so `estimated_cost_usd` in each metrics file is the app’s own figure at that rate.

Jev uses the rates already in this project’s config: **$0.042 per million input tokens** and **$0 per million output tokens**.

Planning tokens are Llama on both scorers. Scoring tokens are Llama or Jev depending on `SCORER`. Llama scoring is recorded on the shared Ollama counters (`prompt_tokens`, `completion_tokens`). The `scorer` block in a Llama metrics file stays at zero calls because `LlamaScorer` goes through `OllamaClient.chat_json`. The split below comes from the `llm task=plan` and `llm task=score` lines in each session log, which sum to the same totals as the metrics file.

Latency below is measured on this machine. It is local Ollama generation time plus Jev HTTP time. It is not Groq’s hosted latency.

## Per-run results

| Run | Wall clock | Query | Retrieve | Score | LLM calls | Prompt tokens | Completion tokens | App cost (USD) |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Llama SWE | 79.3 s | 4.71 s | 30.4 s | 44.1 s | 11 | 4,458 | 1,680 | 0.000357 |
| Jev SWE | 26.9 s | 1.62 s | 24.3 s | 0.71 s | 4 | 7,937 | 648 | 0.000340 |
| Llama AI | 79.5 s | 1.99 s | 26.5 s | 51.1 s | 13 | 5,615 | 1,876 | 0.000431 |
| Jev AI | 26.5 s | 1.89 s | 23.8 s | 0.54 s | 4 | 8,364 | 659 | 0.000358 |
| Llama data | 86.0 s | 1.57 s | 24.8 s | 59.6 s | 11 | 4,530 | 1,552 | 0.000351 |
| Jev data | 19.5 s | 1.45 s | 17.2 s | 0.55 s | 4 | 8,324 | 653 | 0.000355 |

The first Llama query includes a 4.00 s model load. Later Llama query stages are 1.6–2.0 s. Jev query stages stay in that same 1.5–1.9 s band because planning is still local Llama.

Written-item scores (the 15 papers and 5 blogs that were saved):

| Run | Paper min / mean / max | Papers ≥ 70 | Blog min / mean / max | Blogs rejected | Paper bands written |
| --- | --- | ---: | --- | ---: | --- |
| Llama SWE | 40 / 68.0 / 90 | 7 / 15 | 80 / 88.4 / 92 | 7 | 10 direct, 4 adjacent, 1 weak |
| Jev SWE | 94 / 98.7 / 100 | 15 / 15 | 100 / 100 / 100 | 1 | 15 direct |
| Llama AI | 70 / 82.0 / 90 | 15 / 15 | 80 / 90.0 / 100 | 5 | 14 direct, 1 weak |
| Jev AI | 89 / 97.4 / 100 | 15 / 15 | 100 / 100 / 100 | 1 | 15 direct |
| Llama data | 40 / 64.0 / 80 | 6 / 15 | 70 / 80.0 / 90 | 10 | 9 direct, 5 adjacent, 1 weak |
| Jev data | 51 / 88.9 / 100 | 13 / 15 | 100 / 100 / 100 | 0 | 12 direct, 3 adjacent |

## Tokens

Scoring is the part that differs. Planning is one Llama call of about 133 prompt tokens and 55–75 completion tokens on every run (~$0.000012 at the Groq Llama 3 8B rate).

| Scorer | Items scored | Score calls | Score prompt tokens | Score completion tokens | Score-call latency |
| --- | ---: | ---: | ---: | ---: | ---: |
| Llama, 3 runs | 124 | 32 (batches of 4) | 14,203 | 4,915 | 154.7 s total, 4.84 s/call |
| Jev, 3 runs | 121 | 9 (up to 16 items) | 24,225 | 1,766 | 1.79 s total, 0.20 s/call |

Llama spends about 154 tokens per scored item and generates a short free-text reason, so about 26% of its scoring tokens are output. Jev spends about 215 tokens per item, almost all input: each call sends up to 16 items plus the three-level rubric, and the reply is a compact score. Jev output is 7% of its scoring tokens.

Local Llama generation speed on the scoring runs was 45.3, 45.0, and 34.7 completion tokens per second. On the Jev runs, the single planning call still generated at 43–45 tokens per second. The slower 34.7 tok/s run is the data-engineer Llama pass, which also had the longest score stage (59.6 s) and the most prompt-eval time (14.9 s).

## Cost

At Groq `llama3-8b-8192` rates for every Llama token, and the project’s Jev rates for Jev scoring:

| | Llama pipeline (3 runs) | Jev pipeline (3 runs) |
| --- | ---: | ---: |
| End-to-end cost | $0.001139 | $0.001053 |
| Scoring only | $0.001104 | $0.001018 |
| Planning only | $0.000035 | $0.000035 |
| Mean cost per run | $0.000380 | $0.000351 |
| Scoring cost per item | $0.0000089 | $0.0000084 |

The two pipelines land within about 8% of each other at these rates. Jev sends more input tokens, and its input price ($0.042 / million) is close to Llama’s ($0.05 / million). Llama pays for generated reasons at $0.08 / million. Jev’s configured output price is $0, which offsets the larger prompt.

That near-tie is specific to the cheap Llama 3 8B rate. Together’s hosted 8B instruct price is $0.18 per million input and $0.18 per million output (listed for Llama 3.1 8B). At that rate the same three Llama runs would cost about $0.00355 end to end, roughly 3.4× the Jev pipeline, because Llama’s long scoring prompts and generated JSON would all be billed at $0.18.

## Latency

| | Llama mean | Jev mean |
| --- | ---: | ---: |
| Wall clock | 81.6 s | 24.3 s |
| Score stage | 51.6 s | 0.60 s |
| Retrieve stage | 27.2 s | 21.8 s |
| Score share of the run | 63% | 2.5% |

Jev runs finished in about 30% of the Llama wall-clock time. The score stage is the gap: 32 sequential local generations versus 9 short HTTP calls. Retrieval (OpenAlex, arXiv, Semantic Scholar, Brave) is 17–30 s either way and is the largest stage once scoring is Jev. HTTP retries were 8 on five runs and 12 on the Jev AI-engineer run. Those retries sit in retrieve time and are independent of the scorer.

## Match quality

Both scorers filled the targets. Papers are kept by rank with no minimum score, so a weak tail still gets written until 15 papers exist. Blogs must score at least 70.

Llama spreads scores. Written papers ran from 40 to 90. It rejected 22 blogs across three runs (7, 5, and 10). Several saved papers are labeled `direct` at score 60, and one AI-engineer paper is labeled `weak` at score 70 (`LLMaaS: Serving Large-Language Models on Trusted Serverless Computing Platforms`). The band and the number are produced independently, and they disagree on the low end of `direct` and the high end of `weak`. Reasons are specific to the title, capped at 12 words.

Jev places each item on a three-point rubric (weak, adjacent, direct) and maps that position to 0–100. Written papers therefore cluster at the top: means 98.7, 97.4, and 88.9. It rejected 2 blogs (scores 63 and 65, both `adjacent`). Saved blogs were all 100 and `direct`. The data-engineer run is the one where Jev separated the tail: three `adjacent` papers at 51, 51, and 72, against `direct` papers from 77 to 100. Reasons are the rubric sentence itself (`Matches the user's domain and research interests` or `Neighboring topic that is not the stated focus`), so they do not say why a particular paper matched.

Search plans for the software-engineer pair were identical, and the data-engineer pair was identical, because planning temperature is 0. On that shared candidate pool:

- Software engineer: 12 of 15 papers and 4 of 5 blogs were the same documents.
- Data engineer: 9 of 15 papers and 2 of 5 blogs were the same documents.

The AI-engineer plans diverged by a few words (`Retrieval-augmented generation in AI systems` versus `in LLMs`, and similar wording on the agent and PyTorch queries). Only 4 of 15 papers overlapped, so that pair mixes scorer differences with retrieval differences.

On the shared software-engineer pool, the three papers only Llama kept included a graph-database query paper at 40 (`adjacent`) and a browsing-habits paper at 60 (`adjacent`). The three only Jev kept included a real distributed-database paper at 99 and a paper whose title is a journal masthead (`© 2024 IJNRD | Volume 9, Issue 3 March 2024...`) scored 95 `direct`. On the shared data-engineer pool, Llama’s unique papers include dark-energy cosmology, virtual colonoscopy, and warehouse robots, scored 40–60 and still written. Jev’s unique papers include two ETL-pipeline papers at 100 and three loosely related papers it marked `adjacent` at 51–72.

So Llama’s numeric range makes weak papers obvious, and its reasons say something about the item, while its band labels are loose and it still saves papers down to 40. Jev is calibrated to its rubric and rarely rejects a blog, while its 90–100 cluster hides rank among “direct” hits and its reason text does not distinguish one direct paper from another.

## Bottom line

For these three personas, Jev is the faster scorer by about 86× on the score stage and about 3.4× on the full run, at essentially the same dollar cost as Groq’s Llama 3 8B API when Jev output is unbilled. Llama 3 8B remains the planner in both pipelines; that call is about 2 seconds and well under a hundredth of a cent. Llama scoring spends fewer tokens per item, writes a usable reason, and spreads scores enough to reject off-topic blogs, at the cost of a minute of local generation and occasional band/score mismatches. Jev scoring spends more input tokens, returns in a fraction of a second, and labels the rubric consistently, with most accepted items piled near 100.
