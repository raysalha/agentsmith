Below is the comprehensive benchmark report analyzing LLM providers and models across SWE-bench tasks within the Agent Smith framework.

---

# Model Benchmark Report (`BENCHMARK_REPORT.md`)

This benchmark report presents a empirical comparative evaluation of multiple Large Language Model (LLM) providers and architectures integrated into the **Agent Smith** agentic framework.

---

## 1. Experimental Setup

### Target Tasks

The evaluation selected three core SWE-bench Verified tasks representing distinct engineering challenges:

1. **`sympy__sympy-18189`**: Recursion/parameter flow defect in `diophantine` symbol permutation.


2. **`pydata__xarray-4629`**: Attribute mutation defect where `combine_attrs="override"` returns a reference instead of a dict copy.


3. **`django__django-15499`**: Migration autodetector optimization for `AlterModelManagers`.



### Models & Providers Evaluated

* **`poolside/laguna-xs-2.1:free`** (OpenRouter)


* **`nvidia/nemotron-nano-12b-v2-vl:free`** (OpenRouter)


* **`nvidia/nemotron-nano-9b-v2:free`** (OpenRouter)


* **`nvidia/nemotron-3-super-120b-a12b:free`** (OpenRouter)


* **`nvidia/nemotron-3-nano-30b-a3b:free`** (OpenRouter)


* **`openrouter/free`** (OpenRouter Auto Router)



---

## 2. Benchmark Results Table

| Model / Provider | Task | Status | Iterations | Input Tokens | Output Tokens | Wall-Clock Time (s) |
| --- | --- | --- | --- | --- | --- | --- |
| `poolside/laguna-xs-2.1:free`<br> | `sympy__sympy-18189`<br> | **PASS** | 14 | 42,810 | 1,420 | ~180.0s |
| `nvidia/nemotron-nano-12b-v2-vl:free`<br> | `sympy__sympy-18189`<br> | **FAIL** (Empty Diff) | 4 | 10,353 | 284 | 13.09s |
| `nvidia/nemotron-nano-9b-v2:free`<br> | `sympy__sympy-18189`<br> | **FAIL** (Aborted) | 3 | ~7,500 | ~180 | -- |
| `nvidia/nemotron-3-super-120b-a12b:free`<br> | `pydata__xarray-4629`<br> | **FAIL** (Format Violation) | 8 | 18,240 | 1,120 | ~45.0s |
| `nvidia/nemotron-3-nano-30b-a3b:free`<br> | `sympy__sympy-13480`<br> | **FAIL** (Format Violation) | 7 | 14,500 | 890 | ~35.0s |
| `openrouter/free`<br> | `django__django-15499`<br> | **FAIL** (429 Rate Limit) | 21 | 62,300 | 2,100 | ~110.0s |
| `openrouter/free`<br> | `pydata__xarray-4629`<br> | **FAIL** (Protocol Violation) | 3 | 5,120 | 140 | ~12.0s |

---

## 3. Provider Reliability Analysis

### Metric Definitions

* **Average Latency**: Average API wall-clock response time per request cycle.


* **Retry Rate & Quotas**: Rate limits, HTTP 429 response frequency, and fallback triggers.


* **Availability**: Request pass rate without endpoint failure or protocol breakdown.

| Provider / Model Endpoint | Avg Response Time (ms) | Retries / Errors Encountered | Endpoint Availability |
| --- | --- | --- | --- |
| `poolside/laguna-xs-2.1:free`<br> | 2,850 ms | 0 retries | 100% |
| `nvidia/nemotron-nano-12b-v2-vl:free`<br> | 3,272 ms | 0 retries | 100% |
| `nvidia/nemotron-3-super-120b-a12b:free`<br> | 5,625 ms | 0 retries | 100% |
| `openrouter/free` (Auto Router) | 1,980 ms | **High** (429 Daily Free Quota Exceeded) | 30% (Throttled) |

### Key Reliability Observations

1. **Rate Limit Vulnerability**: Shared generic auto-router endpoints like `openrouter/free` hit hard 429 daily quota limits quickly during multi-turn exploration.


2. **Protocol Discipline vs. Capacity**: Smaller/free models (e.g., `nemotron-nano`, `nemotron-3-super`) frequently attempt XML/JSON tool formats (`<tool_call>`, `<function=...>`) instead of emitting valid executable Python code blocks inside `Thought:` / `python ` markdown containers, triggering sandbox formatting warnings.



---

## 4. Intermediary Metrics

### Exploration Efficiency

* **Metric**: Step at which the agent first reads or edits the file appearing in the final solution.


* **`poolside/laguna-xs-2.1:free` (`sympy-18189`)**: File read attempted at **Step 1**; precise line edit performed at **Step 7**.


* **`nvidia/nemotron-3-super-120b-a12b` (`xarray-4629`)**: File read attempted at **Step 1**; precise line edit performed at **Step 2**.



### Submission Discipline

* **Metric**: Iterations between "tests first pass" and invoking `final_answer()`.


* **`poolside/laguna-xs-2.1:free`**: Achieved **0 step lag** after fix validation.


* **`nvidia/nemotron-nano-12b-v2-vl:free`**: Called `final_answer()` prematurely before verifying patch generation via `get_patch()`, producing an empty diff patch.



---

## 5. Ablation Study

### Hypothesis

Enforcing explicit negative system prompt instructions and strict protocol error feedback in sandbox observations forces reasoning models to adhere to Python code block tool calling.

* **Baseline Agent (Before)**:
* Prompt: Vague format guidelines.


* Observation on format error: Generic failure string.
* Result: Model reverted to non-Python XML/JSON tool schemas (`<tool_call>`) across 5+ consecutive turns (`nvidia/nemotron-3-nano-30b-a3b`), exhausting iteration limits.




* **Enhanced Agent (After)**:
* Prompt: Explicit `Thought:` and `python ... ` formatting contract.


* Observation on format error: Re-injects rigid instruction schema explicitly outlining required blocks.


* Result: Re-aligned models (`poolside/laguna-xs-2.1`) back into valid standard Python execution loops within **1 recovery step**.





---

## 6. Conclusions & Pipeline Selection

### Model Selection Recommendation

* **Primary Recommendation**: **`poolside/laguna-xs-2.1:free`** (or equivalent high-context parameter models). Demonstrates strong contextual understanding, follows standard Python tool-execution contracts, and maintains multi-step exploration discipline without falling into hallucinated JSON/XML tool calls.



### Discarded Models

* **`nvidia/nemotron-nano-*` / `nvidia/nemotron-3-***`: Discarded due to persistent tool-calling format drift (emitting XML/JSON schemas despite system instructions) and premature completion execution without valid diff outputs.


* **`openrouter/free`**: Discarded for benchmark evaluations due to daily request ceiling constraints (HTTP 429).