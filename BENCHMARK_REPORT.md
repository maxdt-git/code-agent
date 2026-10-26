# Benchmark Report

> **Status: in progress.** Sections marked **TODO** need SWE-bench runs that
> have not been done yet. Every number below comes from a real run; nothing
> is estimated.

## 1. Setup

### Models and providers

All providers are used on their free tier only, with keys loaded from `.env`.

| Provider | Base URL | Models considered |
|---|---|---|
| Groq | `https://api.groq.com/openai/v1` | `qwen/qwen3.8-27b`, `openai/gpt-oss-120b`, `openai/gpt-oss-20b` |
| Google AI Studio (Gemini) | `https://generativelanguage.googleapis.com/v1beta/openai/` | `gemini-3.6-flash`, `gemini-3.5-flash-lite`, `gemini-3.5-flash` |
| OpenRouter | `https://openrouter.ai/api/v1` | `cohere/north-mini-code:free`, `recursive/flint-v1.0:free`, `poolside/laguna-s-2.1:free`, `nvidia/nemotron-3-ultra-550b-a55b:free` |

**TODO:** final list of the 5+ models actually benchmarked on SWE-bench.

### Tasks

**TODO:** 3+ SWE-bench Verified tasks. Planned starting set, recommended by
the subject as the simplest ones:

- `sympy__sympy-14711`
- `sympy__sympy-13480`
- `pydata__xarray-4629`

**TODO:** explain why these tasks were kept.

## 2. Results (SWE-bench)

**TODO:** one row per model × task.

| Model | Provider | Task | Pass | Iterations | Input tokens | Output tokens | Time (s) |
|---|---|---|---|---|---|---|---|
| | | | | | | | |

## 3. Provider reliability

### Free-tier limits that decide what each provider can do

Measured from Groq response headers (`x-ratelimit-limit-tokens`,
`x-ratelimit-limit-requests`) on 2026-10-23:

| Groq model | Input tokens per minute | Requests per day |
|---|---|---|
| `qwen/qwen3.8-27b` | 8,000 | 1,000 |
| `openai/gpt-oss-120b` | 8,000 | 1,000 |
| `openai/gpt-oss-20b` | 8,000 | 1,000 |
| `allam-2-7b` | 6,000 | 7,000 |

A per-minute token limit also caps the size of **one** request. This rules
Groq out for SWE-bench: on `sympy__sympy-14711`, the agent was stopped by
`HTTP 413 ... input tokens per minute (ITPM): Limit 7000, Requested 7088`
as soon as its history (files read, search results) grew past this size.
Groq remains the best fit for MBPP (see section 7), where a whole task needs
about 1,400 input tokens.

### Response time on a large request

One request of about 10,000 input tokens (source code plus a question),
`max_tokens=400`, sent once per model on 2026-10-23:

| Provider | Model | Result | Time (s) |
|---|---|---|---|
| Gemini | `gemini-3.6-flash` | OK | 5.3 |
| Gemini | `gemini-3.5-flash-lite` | OK | 12.2 |
| Gemini | `gemini-3.5-flash` | OK | 44.7 |
| Gemini | `gemini-3.7-flash` | timeout (90 s) | — |
| Gemini | `gemini-3.8-flash` | timeout (90 s) | — |
| Gemini | `gemini-2.5-pro` | HTTP 404, model retired | — |
| OpenRouter | `cohere/north-mini-code:free` | OK | 1.9 |
| OpenRouter | `recursive/flint-v1.0:free` | OK | 2.0 |
| OpenRouter | `poolside/laguna-s-2.1:free` | OK | 3.8 |
| OpenRouter | `nvidia/nemotron-3.5-super-vl:free` | OK | 3.4 |
| OpenRouter | `dots-studio/dots-3-note-preview:free` | OK | 4.4 |
| OpenRouter | `nvidia/nemotron-3-ultra-550b-a55b:free` | OK | 7.8 |
| OpenRouter | `nvidia/nemotron-3.5-lightning:free` | empty text (reasoning used the whole budget) | 1.7 |
| OpenRouter | `google/gemma-4-26b-a4b-it:free`, `google/gemma-4-31b-it:free`, `xingchen-agi/xing4.0-29b-a4b:free` | HTTP 429, provider saturated | — |
| OpenRouter | `thinkingmachines/inkling:free`, `inkling-small:free` | HTTP 403, needs a paid account | — |

### Availability over time

- Model names change: `llama-3.1-8b-instant` (Groq) and `gemini-2.5-flash`
  (Gemini) answered HTTP 404 in October 2026. The client treats 404 as
  `ModelUnavailableError` and switches to the configured fallback.
- OpenRouter free models are often saturated (HTTP 429), even on the first
  request of the day.
- Latency of the same Gemini model varies a lot: `gemini-3.5-flash-lite`
  took 47.7 s for a 6-token request on 2026-10-03, and 12.2 s for a
  10,000-token request on 2026-10-23.

**TODO:** average response time, retries and availability per model during
the SWE-bench runs (from `request_time_ms` and `retries` in `solution.json`).

## 4. Intermediary metrics

**TODO**, from the SWE-bench `solution.json` files:

- step at which the agent first reads or edits the file of the final patch;
- step at which test failures first decrease versus the baseline;
- iterations between the first passing `run_tests` and `final_answer`.

## 5. Ablation study

**TODO:** a before/after comparison on SWE-bench, same tasks, same model.

The MBPP development history below already shows the method on another
benchmark (same model, `qwen/qwen3.8-27b` on Groq, random MBPP tasks drawn
by `exam_mbpp.sh`):

| Agent version | Change | Tasks | Pass | Avg iterations | Avg input tokens | Max input tokens | Max output tokens | Over limits |
|---|---|---|---|---|---|---|---|---|
| v0 | system prompt = tool manual only | 1 (task 249) | 0/1 | 8 | 8,584 | 8,584 | 1,319 | yes |
| v1 | rules, answer format, worked example, test-then-submit in one block | 20 | 14/20 | 2.25 | 2,060 | 9,403 | 4,096 | 3 tasks |
| v2 | v1 + token budget guard (600 output tokens per step, stop before 90 % of the input limit) | 10 | 9/10 | 1.90 | 1,514 | 5,270 | 1,300 | none |
| v3 | v2 + all code blocks of an answer executed, in order | 20 | 19/20 | 1.95 | 1,392 | 4,248 | 875 | none |

What each change fixed, read from the traces:

- **v0 → v1:** with only the manual, the model never called `run_tests` nor
  `final_answer`, used a wrong function name and invented malformed
  `<tool_call>` blocks. With v1 it solved task 249 in 1 iteration and
  623 input tokens instead of failing after 8,584.
- **v1 → v2:** in v1, one answer could use 2,048 output tokens on reasoning
  alone, and one correct solution was rejected at 9,403 input tokens. The
  guard removed every limit overrun.
- **v2 → v3:** the model sometimes split its answer in two blocks
  (definition, then `final_answer`). Only the first one was executed, so a
  correct answer was never submitted.

The only failure left in v3 is task 461, whose reference solution in the
dataset is itself wrong (it returns inside the loop and only checks the
first character), so its tests cannot be passed by a correct solution.

## 6. Conclusions

**TODO**, based on the SWE-bench results. Current findings:

- **MBPP:** `qwen/qwen3.8-27b` on Groq: 19/20, 1.95 iterations and about
  1,400 input tokens per task on average (23 % of the limit), about 0.5 s
  per request.
- **SWE-bench:** Groq is excluded by its per-request size limit. The first
  candidates are `gemini-3.6-flash` (main) and
  `cohere/north-mini-code:free` (fallback), the fastest models that accepted
  a 10,000-token request.

## Backing data

**TODO:** copy the `solution.json` files used in this report into the
repository (the subject requires them) and list their paths here.
