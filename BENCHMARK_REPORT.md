Below is the comprehensive benchmark report analyzing LLM providers and models across SWE-bench tasks within the Agent Smith framework.

---

# Model Benchmark Report (`BENCHMARK_REPORT.md`)

This benchmark report presents an empirical comparative evaluation of multiple Large Language Model (LLM) providers and architectures integrated into the **Agent Smith** agentic framework. It has been updated with a second, larger batch of runs (`stdout1.log`–`stdout12.log`) obtained through the full `exam_swebench`-style pipeline (agent run + `moulinette_eval validate`), which gives real correctness verdicts rather than the earlier estimated/partial figures.

---

## 1. Experimental Setup

### Target Tasks

The evaluation now spans **six** SWE-bench Verified tasks (well above the 3-task minimum), chosen to cover a spread of difficulty and codebases:

1. **`sympy__sympy-18189`** — recursion/parameter flow defect in `diophantine` symbol permutation.
2. **`pydata__xarray-4629`** — attribute mutation defect where `combine_attrs="override"` returns a reference instead of a dict copy.
3. **`django__django-15499`** — migration autodetector optimization for `AlterModelManagers`.
4. **`django__django-11066`** *(new)* — `RenameContentType._rename()` not saving the content type on the correct database (missing `using=db` on `.save()`).
5. **`sympy__sympy-13480`** *(new)* — typo bug in `hyperbolic.py` (`cotm` vs `cothm`).
6. **`scikit-learn__scikit-learn-13439`** *(new)* — used as a harder/negative-control task.
7. **`sympy__sympy-14711`** *(new)* — used to probe token-budget behavior on a harder task.

Tasks 4–7 were added specifically because the first three had only ever been tried with the *weaker* free models, so no clean picture existed of how the framework performs on a *capable* model run repeatedly. django-11066 and sympy-13480 were each run 3+ times with the same model to measure run-to-run variance, which turned out to be one of the most important findings (see §4 and §6).

### Models & Providers Evaluated

* **`poolside/laguna-s-2.1:free`** (OpenRouter) — *note: earlier drafts of this report referred to this model as `poolside/laguna-xs-2.1:free`; the correct model identifier confirmed from live run logs is `poolside/laguna-s-2.1:free`.*
* **`google/gemma-4-26b-a4b-it:free`** (OpenRouter) *(new)*
* **`nvidia/nemotron-nano-12b-v2-vl:free`** (OpenRouter)
* **`nvidia/nemotron-nano-9b-v2:free`** (OpenRouter)
* **`nvidia/nemotron-3-super-120b-a12b:free`** (OpenRouter)
* **`nvidia/nemotron-3-nano-30b-a3b:free`** (OpenRouter)
* **`openrouter/free`** (OpenRouter Auto Router)

7 distinct models across 7 tasks — comfortably above the 5-model / 3-task minimum.

---

## 2. Benchmark Results Table

### 2a. New validated runs (`stdout1`–`stdout12`, via `moulinette_eval validate`)

These rows come from full pipeline runs where a real correctness check (patch re-applied + tests re-run) was performed, not just the agent's own self-reported `success` flag.

| # | Model | Task | Iterations | Input Tokens | Output Tokens | Wall-Clock (s) | Correctness | Overall Result |
|---|---|---|---|---|---|---|---|---|
| 1 | `poolside/laguna-s-2.1:free` | `django__django-11066` | 5 / 30 | 26,845 | 698 | 25.0 | PASSED | **PASSED** |
| 2 | `poolside/laguna-s-2.1:free` | `pydata__xarray-4629` | 15 / 30 | 101,457 | 1,626 | 210.8 | PASSED | **PASSED** |
| 3 | `poolside/laguna-s-2.1:free` | `sympy__sympy-13480` | 30 / 30 | 277,732 | 4,467 | 168.2 | FAILED (invalid patch) | **FAILED** |
| 4 | `poolside/laguna-s-2.1:free` | `django__django-11066` | 6 / 30 | 29,765 | 750 | 41.0 | PASSED | **PASSED** |
| 5 | `poolside/laguna-s-2.1:free` | `scikit-learn__scikit-learn-13439` | 20 / 30 | 197,719 | 2,409 | 342.3 | — (no patch submitted) | **FAILED** |
| 6 | `poolside/laguna-s-2.1:free` | `sympy__sympy-13480` | 24 / 30 | 346,157 | 33,715 | 976.6 | Patch looked valid | **FAILED (time limit exceeded, 979s > 900s)** |
| 7 | `poolside/laguna-s-2.1:free` | `django__django-11066` | 23 / 30 | 199,045 | 5,870 | 243.5 | FAILED (invalid patch) | **FAILED** |
| 8 | `google/gemma-4-26b-a4b-it:free` | `sympy__sympy-13480` | 28 / 30 | 211,474 | 2,518 | 877.0 | FAILED (invalid patch) | **FAILED** |
| 9 | `poolside/laguna-s-2.1:free` | `pydata__xarray-4629` | 12 / 30 | 72,925 | 2,057 | 105.4 | PASSED | **PASSED** |
| 10 | `poolside/laguna-s-2.1:free` | `sympy__sympy-13480` | 6 / 30 | 34,459 | 699 | 42.5 | PASSED | **PASSED** |
| 11 | `poolside/laguna-s-2.1:free` | `sympy__sympy-14711` | 30 / 30 | 352,237 (**over 300k limit**) | 10,033 (**over 10k limit**) | 392.9 | FAILED (invalid patch) | **FAILED (metrics + validation)** |
| 12 | `poolside/laguna-s-2.1:free` | `pydata__xarray-4629` | 6 / 30 | 27,743 | 536 | 29.5 | PASSED | **PASSED** |

### 2b. Earlier exploratory runs (self-reported, no full moulinette validation)

Kept for historical comparison against weaker/free models; these figures were taken directly from raw agent transcripts rather than the validated pipeline above.

| Model / Provider | Task | Status | Iterations | Input Tokens | Output Tokens | Wall-Clock Time (s) |
| --- | --- | --- | --- | --- | --- | --- |
| `poolside/laguna-s-2.1:free` | `sympy__sympy-18189` | PASS (self-reported) | 14 | 42,810 | 1,420 | ~180.0 |
| `nvidia/nemotron-nano-12b-v2-vl:free` | `sympy__sympy-18189` | FAIL (empty diff) | 4 | 10,353 | 284 | 13.1 |
| `nvidia/nemotron-nano-9b-v2:free` | `sympy__sympy-18189` | FAIL (aborted) | 3 | ~7,500 | ~180 | — |
| `nvidia/nemotron-3-super-120b-a12b:free` | `pydata__xarray-4629` | FAIL (format violation) | 8 | 18,240 | 1,120 | ~45.0 |
| `nvidia/nemotron-3-nano-30b-a3b:free` | `sympy__sympy-13480` | FAIL (format violation) | 7 | 14,500 | 890 | ~35.0 |
| `openrouter/free` | `django__django-15499` | FAIL (429 rate limit) | 21 | 62,300 | 2,100 | ~110.0 |
| `openrouter/free` | `pydata__xarray-4629` | FAIL (protocol violation) | 3 | 5,120 | 140 | ~12.0 |

---

## 3. Provider Reliability Analysis

### Metric Definitions

* **Avg time/request**: `total_time_seconds / total_requests` for a run. Note this is a *combined* figure — it includes LLM API latency **and** sandbox/tool execution time (file reads, `run_tests`, Docker-bridged commands), since the raw logs do not separate the two. It should be read as "average full round-trip per agent step," not pure model latency.
* **Retry rate & quotas**: rate limits, HTTP 429 frequency, and API-key fallback triggers observed in logs.
* **Pass rate**: validated correctness rate (PASSED / total attempts), computed only from the §2a runs that went through full `moulinette_eval validate`.

| Provider / Model | Runs (validated) | Pass Rate | Avg time/request (s) | Retries / Errors Observed |
| --- | --- | --- | --- | --- |
| `poolside/laguna-s-2.1:free` | 11 | **6 / 11 (55%)** | 13.5 | Frequent `"Rate limit exceeded; switching API key"` events (handled by key rotation, no run failures caused by this) |
| `google/gemma-4-26b-a4b-it:free` | 1 | 0 / 1 (0%) | 20.9 | None observed beyond high request count (42 requests for 28 iterations) |
| `openrouter/free` (Auto Router) | 2 (earlier, unvalidated) | 0% | ~5.5 | High — hit daily 429 quota exhaustion mid-run |
| `nvidia/nemotron-*` family | 4 (earlier, unvalidated) | 0% | n/a (not logged) | Frequent tool-call format drift, not provider errors per se |

### Key Reliability Observations

1. **`poolside/laguna-s-2.1:free` is the only model in this batch that reliably produces syntactically valid, applicable patches** — every failure in §2a for this model was either a real logic failure (invalid patch content) or a budget overrun (time/tokens), never a formatting/protocol violation. This is a meaningful step up from the nemotron/gemma family, which frequently drifted into non-Python tool-call formats (see the earlier `output*.log` transcripts referenced in §5).
2. **Significant run-to-run variance on the same task.** `sympy__sympy-13480` was attempted 3 times with the identical model and tool configuration: one clean pass in 6 iterations (run #10), one full 30-iteration failure producing an invalid patch (run #3), and one run that produced what looked like a valid fix but blew the 900s time budget after 24 iterations (run #6, 976.6s). This is the single most important reliability finding in this update — **the same model/task pair can swing from best-case to worst-case behavior**, which has direct implications for exam-day pass-rate expectations (recall the exam only samples 3 SWE-bench tasks and requires 2/3 to pass).
3. **`django__django-11066` is comparatively stable**: 2 of 3 runs passed cleanly in 5–6 iterations; the one failure (run #7) took a markedly different, much longer path (23 iterations, ~8x the tokens) before producing an invalid patch — consistent with the model occasionally "getting lost" during exploration rather than a systematic flaw in the fix itself.
4. **`pydata__xarray-4629` was the most reliable task/model pairing observed**: all 3 `poolside` runs passed (6, 12, and 15 iterations respectively), suggesting this bug is well within the model's reach regardless of exploration path taken.
5. **Rate-limit vulnerability persists for shared/free endpoints.** `openrouter/free` (the auto-router alias, distinct from a specific model) continues to be unusable for benchmark purposes due to hard daily quota limits (HTTP 429), independent of the model-selection improvements above.

---

## 4. Intermediary Metrics

### Exploration Efficiency

*Step at which the agent first reads/edits the file that ends up in the final patch.*

* **`poolside` / `django-11066` (run #1, fastest pass)**: file read at step 1 (`django/contrib/contenttypes/management/__init__.py`), edit applied by step 3, tests passing and patch submitted by step 5.
* **`poolside` / `django-11066` (run #7, failure)**: by contrast, this run took until roughly step 10+ before touching the correct file, spending its early iterations on broader repository exploration — a concrete, measurable difference between the fast/successful and slow/failed runs of the *same* task.
* **`poolside` / `sympy-13480` (run #10, fastest pass)**: located and fixed `hyperbolic.py` within the first 2–3 steps, verified via `run_tests()`, and submitted by step 6.

### Submission Discipline

*Iterations between "tests first pass" and calling `final_answer()`.*

* **`poolside` / `xarray-4629` (all 3 runs)**: consistently near-zero lag — `final_answer(get_patch())` was called essentially immediately once `run_tests()` reported a pass, across all three independent runs (6, 12, and 15 total iterations respectively).
* **`poolside` / `sympy-13480` (run #6)**: this is the clearest *negative* example of discipline — the model appears to have reached a working fix but continued iterating (re-reading files, re-running tests) long enough to burn through the full 900s time budget, converting what should have been a pass into a hard time-limit failure. This directly motivates the ablation in §5.

### Token Budget Pressure (additional metric worth tracking given the new data)

* **`sympy__sympy-14711` (run #11)** is a clear case of a harder task pushing the model into its maximum iteration budget (30/30) *and* exceeding both token ceilings (352k/300k input, 10k/10k output) simultaneously — the agent never converges on a valid patch and instead keeps exploring/re-reading large files until every limit trips at once. This suggests `sympy-14711` is a poor choice for exam-style validation with this model unless prompting is tightened specifically around read-size discipline (e.g. tighter `read_file` line ranges).

---

## 5. Ablation Study

### Hypothesis

Enforcing an explicit `Thought:` + single-Python-code-block contract, with the sandbox re-injecting the exact required format on violation, prevents reasoning-style models from drifting into non-Python tool-call schemas (`<tool_call>`, `<function=...>`, JSON action objects) that the sandbox cannot execute.

* **Baseline agent (earlier `output2.log`/`output6.log` runs, §2b)**: vague format guidance, generic failure string on violation. Result: `nvidia/nemotron-3-nano-30b-a3b` and `nvidia/nemotron-3-super-120b-a12b` repeatedly emitted XML/JSON-style tool calls (`<tool_call>...`, `<function=search_code>...`) across 5+ consecutive turns, none of which were extracted as executable code, exhausting the iteration budget without making progress.
* **Enhanced agent (current prompt + explicit re-injected protocol error, §2a)**: same violation type still occurs occasionally with weaker models (e.g. `google/gemma-4-26b-a4b-it:free` and even `poolside` intermittently reverted to `<tool_call>`/JSON formats in transcripts not shown above), but recovery is now reliable — the very next turn after a protocol violation message consistently returns to a valid `Thought:` + ```python``` block. No run in the new batch was lost purely to unrecoverable format drift; all failures in §2a were logic/budget failures, not protocol failures.

### Secondary ablation candidate identified by this data (not yet run, recommended next step)

The `sympy-13480` variance (§3, point 2) strongly suggests that **submission-discipline** is currently under-constrained: the model is never explicitly told to stop investigating once `run_tests()` reports success. A natural next ablation: add an explicit prompt rule *"call `final_answer(get_patch())` immediately after the first successful `run_tests()` — do not continue investigating"* and re-run `sympy-13480` ≥5 times with `poolside/laguna-s-2.1:free` to see whether this collapses the 6-to-30-iteration spread observed here into a narrower, more predictable range.

---

## 6. Conclusions & Pipeline Selection

### Model Selection Recommendation

**Primary recommendation: `poolside/laguna-s-2.1:free`.** Across 11 validated runs spanning 5 distinct tasks, it is the only model that (a) reliably produces syntactically valid, applicable git patches, (b) recovers cleanly from occasional format violations, and (c) solves at least one task (`xarray-4629`) with 3/3 perfect reliability. Its overall 55% validated pass rate across a genuinely mixed difficulty set is markedly better than every other model tested, none of which produced a single validated pass in this batch.

However, this recommendation comes with an important caveat that did not appear in the earlier draft of this report: **`poolside` is not uniformly reliable** — the same task (`sympy-13480`) produced a clean pass, an invalid-patch failure, and a time-limit failure across three otherwise-identical runs. Given the exam samples only 3 SWE-bench tasks and requires 2/3 to pass, this run-to-run variance is a real risk that should be mitigated before relying on a single run's outcome — see the submission-discipline ablation proposed in §5.

### Discarded Models

* **`google/gemma-4-26b-a4b-it:free`**: produced no validated pass in this batch; took 42 requests to reach 28 iterations (unusually high retry/request overhead relative to iteration count) and still ended in an invalid patch after 877s.
* **`nvidia/nemotron-nano-*` / `nvidia/nemotron-3-*` family**: discarded due to persistent tool-calling format drift (emitting XML/JSON schemas despite explicit system instructions) and, where format was correct, premature/invalid completions.
* **`openrouter/free`**: discarded for benchmark purposes due to hard daily request-quota exhaustion (HTTP 429), independent of underlying model quality.

### Overall Pipeline Note

The addition of the `insert_after` MCP tool (present in most, but not all, of the new runs) did not show a clear, consistent effect on iteration count or pass rate in this batch — e.g. `django-11066` runs both with (#1, 5 iters, PASS) and without (#4, 6 iters, PASS) `insert_after` performed similarly. No strong conclusion is drawn about this tool's impact; it is left in the toolset since it did not measurably hurt performance and may help on tasks requiring multi-line insertions not exercised by the current task set.
