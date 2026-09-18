# Project Progress Log

Running log of every change made to this repository, newest entries appended at the bottom.
Update this file whenever anything is created, edited, or deleted.

---

## 2026-08-23 — Step 1: Scaffold + synthetic dataset

**Goal:** create the project scaffold and synthetic dataset only. No agent logic, no tools, no
LangGraph. `requirements.txt` deliberately untouched.

### Setup check (before any change)
- Repo already had the scaffold run once: every file existed but was **0 bytes**.
- `requirements.txt` already populated (langchain, langgraph, faiss-cpu, sentence-transformers,
  streamlit, pandas, python-dotenv) — left untouched as instructed.
- `.env.example` (`GOOGLE_API_KEY=`) and `.gitignore` already had correct content — left as-is.
- Virtualenv `myenv/` present, Python 3.14.6.

### Changed: `templete.py`
Rewrote the scaffold script so it matches the Step 1 spec instead of the full blueprint layout.

| Before | After |
|---|---|
| Created `src/tools/policy_search.py`, `call_lookup.py`, `qa_scorer.py`, `src/agent/state.py`, `graph.py`, `src/ui/app.py` | Removed — those belong to later build steps |
| Created `.env`, `requirements.txt`, `README.md` | Removed — `requirements.txt` must not be touched |
| `src/ui/` only created implicitly via `app.py` | Added explicit `PROJECT_DIRS` list so `src/ui/` exists as an empty directory |
| Default target `call-center-agent` | Default target `.` (current repo root) |
| — | Added `data/README_DATA.md` to the file list |

`touch(exist_ok=True)` is still used, so re-running never truncates an existing file.

### Created: 5 policy files in `data/policies/`
Plain text, numbered sections, fictional but realistic. All rule values here are the ground truth
the QA scorer will later check transcripts against.

- `replacement_policy.txt` — 90-day eligibility window, proof of purchase required, 3-5 business day
  dispatch, one replacement per order, misuse damage excluded.
- `repair_sla.txt` — 24-hour acknowledgement, 7 business day standard SLA, up to 14 for complex
  repairs, SMS update at each stage, free temporary replacement if SLA exceeded.
- `logistics_guidelines.txt` — prepaid return label by email, original packaging where possible,
  tracking number shared with customer, refund within 5-7 business days of receipt, lost-in-transit
  claims within 30 days.
- `device_support.txt` — support Mon-Sat 9am-6pm, remote screen share for premium customers,
  troubleshooting guide emailed on first contact, hardware issues escalated to repair team.
- `escalation_policy.txt` — triggers (2 unresolved contacts / manager request / SLA breach), senior
  agent assigned within 2 hours, customer notified by email + SMS, 24-hour escalation SLA.

### Created: `data/calls.csv` — 30 rows
Columns: `call_id, date, agent_name, call_type, direction, duration_mins, transcript, channel`.
Generated deterministically with Python's `csv` module (`QUOTE_MINIMAL`) so transcripts containing
commas and newlines are quoted correctly.

- CALL-1001 to CALL-1030, 20 good / 10 bad.
- 6 rows per agent (Rahul, Priya, Amit, Sara, James).
- Types: replacement 7, repair 6, logistics 6, device 6, escalation 5.
- Dates 2026-07-25 to 2026-08-23; durations 3-18 minutes.

### Created: `data/README_DATA.md`
One-paragraph explanation of what makes the good calls good and the bad calls bad, plus a
ground-truth answer-key table listing every bad `call_id` and its intended failure.

### Fix during the same step
First generation produced 13-17 line transcripts, outside the required 8-12. All transcripts were
rewritten in condensed form and re-validated to 11-12 lines each.

### Validation run
Contiguous non-duplicate call_ids, transcripts 8-12 lines with every line prefixed
`Agent:`/`Customer:`, durations 3-18, dates inside the last 30 days, legal enum values for
`direction`/`call_type`/`channel`, and a clean `pandas.read_csv` round-trip.

### Left in place (not part of Step 1)
Six 0-byte stubs from the earlier scaffold run remain on disk and will be filled in later steps:
`src/tools/policy_search.py`, `src/tools/call_lookup.py`, `src/tools/qa_scorer.py`,
`src/agent/state.py`, `src/agent/graph.py`, `src/ui/app.py`.

---

## 2026-08-23 — Dataset expansion: 30 -> 50 calls

Added 20 more calls (CALL-1031 to CALL-1050), 13 good / 7 bad, keeping the original ~2:1 ratio.

**New totals**
- 50 rows: 33 good, 17 bad.
- 10 rows per agent (4 added each).
- Types: replacement 11, repair 10, logistics 10, device 10, escalation 9 (4 added each).
- 553 dialogue lines, 8,691 words; directions 43 inbound / 7 outbound;
  channels 32 phone / 13 chat / 5 email.

**New bad calls**

| call_id | agent | call_type | intended failure |
|---|---|---|---|
| CALL-1032 | Sara | repair | no greeting |
| CALL-1035 | Amit | escalation | no identity verification |
| CALL-1038 | James | device | no proper closure (ends chat mid-question) |
| CALL-1041 | Priya | device | dismissive tone |
| CALL-1044 | Rahul | logistics | no greeting + no proper closure |
| CALL-1047 | Sara | replacement | no identity verification + policy violation |
| CALL-1050 | Amit | replacement | dismissive tone + no proper closure |

CALL-1047 is a second policy-compliance trap alongside CALL-1026: it approves a replacement about
five months after purchase (outside the 90-day window), skips proof of purchase, and promises a
48-hour dispatch instead of 3-5 business days. Two such calls give the QA scorer more signal when
testing whether it actually reads the retrieved policy text.

`data/README_DATA.md` was updated with the new counts and the seven new answer-key rows.
CALL-1047 was trimmed from 13 to 11 lines to stay inside the 8-12 line rule, then everything was
re-validated.

**Full bad-call answer key (17):** CALL-1006, 1010, 1013, 1016, 1020, 1022, 1026, 1028, 1029, 1030,
1032, 1035, 1038, 1041, 1044, 1047, 1050.

---

## 2026-08-23 — Committed and pushed Step 1

Staged all Step 1 work and pushed to `origin/main` as commit `aeb4e75`
(`Add synthetic dataset and policy docs for call-center agent`), 9 files, 854 insertions:
the 5 policy documents, `data/calls.csv`, `data/README_DATA.md`, `progress.md`, and the rescoped
`templete.py`.

Verified before committing that `.env` and `myenv/` were excluded by `.gitignore`, so no secrets or
virtualenv files reached the remote.

---

## 2026-08-24 — Tool 1: Policy Search (LangChain hybrid retrieval + LLM answers)

Built `src/tools/policy_search.py`, `src/config.py`, `config.json`, and
`notebooks/test_policy_search.ipynb`. Scope: Tool 1 only — no agent, other tools, or UI.

**Pipeline (LangChain throughout):**
1. Load + chunk — the 5 policy `.txt` files are split with `RecursiveCharacterTextSplitter`
   into LangChain `Document`s tagged `{chunk_id, source_file, call_type}`.
2. `route_query_to_call_type(query)` — keyword table, first match wins, `None` when nothing
   matches (pure, no LLM). `None` searches across all docs instead of one policy.
3. Per call_type (plus a `None`/all-docs bucket): a `FAISS` vector store
   (`HuggingFaceEmbeddings`, MiniLM) + a `BM25Retriever`, combined in an `EnsembleRetriever`
   (reciprocal-rank fusion, `c=rrf_k`). Built once at import; `rebuild_indexes()` rebuilds
   them after a runtime chunking change.
4. The fused top-k chunks (`config.retrieval.top_k_chunks`) become the LLM context.
5. `get_llm_client(config)` returns `generate(prompt)->str` backed by a LangChain chat model
   selected by `active_provider` (`ChatGoogleGenerativeAI` / `ChatOpenAI` — also used for
   local_lmstudio — / `ChatAnthropic`). The prompt answers ONLY from the retrieved context,
   otherwise it states the policy documents do not cover the question.

**Public API**
- `search_policy(query) -> str` — routed hybrid retrieval, returns the generated answer.
- `search_policy_with_context(query, call_type=None) -> {answer, chunks_used, routed_call_type}`
  — for Tool 3; an explicit known call_type skips routing.

**Config / loading**
- `config.json` is the source of truth for chunking, `embedding_model`, retrieval
  (`rrf_k`, `top_k_chunks`), and per-provider LLM settings.
- `src/config.py` loads `.env` + `config.json` once and exposes `CONFIG` + `REPO_ROOT` so every
  module shares one loader.

**Notebook** `notebooks/test_policy_search.ipynb`: (a) config + active-LLM check, (b) routing on
6 queries, (c) `search_policy` on 5 queries, (d) `search_policy_with_context` showing raw chunks
vs answer, (e) change `chunk_size` and reindex to show its effect on retrieval.

## 2026-08-24 — FAISS index persistence

Tool 1 now persists its FAISS indexes to `data/faiss_index/` (gitignored) instead of
re-embedding on every import.

- On startup each scope's index is loaded from disk when a saved manifest matches the current
  corpus fingerprint — a SHA-256 over `embedding_model` + chunk_size/overlap + the policy file
  contents. On any mismatch (model, chunking, or a source edit) all indexes are rebuilt and
  re-saved, so stale vectors are never served.
- Layout: one subdir per call_type plus `_all/`, each holding `index.faiss` + `index.pkl`, with
  `manifest.json` recording the fingerprint and build settings.
- BM25 retrievers are still rebuilt in memory (cheap, no embedding cost). `rebuild_indexes()`
  re-checks the fingerprint, so a runtime chunking change rebuilds and re-persists automatically.

---

## 2026-08-25 — Added CLAUDE.md

Created `CLAUDE.md` at the repo root via `/init` to orient future Claude Code sessions. Documents:
the step-by-step build model and which modules are still intentional 0-byte stubs; the workflow
rules (keep `progress.md` current, stay within the current step's scope, leave `requirements.txt`
alone unless a step touches it); the run model (Python 3.14 / `myenv/`, run from repo root so the
`src` package resolves, notebook is the only test harness); `config.json` as source of truth with
the import-time LLM-client gotcha (fails at import on a missing key / unreachable local endpoint);
and the Tool 1 hybrid-RAG architecture, FAISS fingerprint persistence, and the synthetic dataset /
answer key. No source code changed.

---

## 2026-08-25 — Added Tool 2: Call Record Lookup

Implemented `src/tools/call_lookup.py` (previously a 0-byte stub). Public API:
`lookup_calls(query: str) -> str` — parses a natural-language request into
structured filters, applies them to `data/calls.csv` with pandas, and returns
the matching records formatted one per line. Follows Tool 1's conventions:
shared config via `src.config`, provider-agnostic chat model from `config.json`,
dev logs under a `[call_lookup]` prefix. The tool **always returns a string** and
never raises.

Two-stage extraction, cheapest first (most queries never hit the LLM):

- **Stage 1 — regex/enum prefilter (no network call):** normalizes call_id
  ("call 1042"/"#1042"/"CALL-1042" → `CALL-1042`), whole-word matches the 5
  agents / 5 call_types / direction / channel, extracts a row limit + sort order
  ("last/top N" → desc, "first N" → asc; a negative lookahead keeps "N days" from
  being read as a limit), and resolves the unambiguous dates ("today",
  "yesterday", "last N days"). Returns only the fields it actually matched.
- **Stage 2 — LangChain structured-output LLM fallback:** invoked *only* when the
  query uses fuzzy date language regex can't safely resolve ("this week", "last
  month", "recent") **or** the regex stage matched nothing at all. The chat model
  is bound with `.with_structured_output(CallFilters)`, so a Pydantic schema
  drives extraction — no JSON hand-parsing, no fence stripping. Every
  closed-vocabulary field (agent_name, call_type, direction, channel, sort_order)
  is a real Python `Enum`, making out-of-vocabulary values structurally
  impossible. The regex-resolved fields are passed into the prompt and, on merge,
  **always take precedence** — the LLM only fills gaps.

Schema (`CallFilters`, shared by both stages): call_id, agent_name, call_type,
direction, channel, date_from, date_to, limit (clamped to ≤50 via a `mode=before`
validator so an over-eager value degrades instead of erroring), sort_order
(default `desc`).

Caching: the structured-output client is built once via `lru_cache` (lazily, on
first Stage-2 use); the DataFrame is loaded once via `lru_cache`. Error handling:
any LLM failure (network, rate limit, malformed/empty structured response) is
logged and falls back to the regex-only result; any pandas/filtering failure is
caught and returned as a plain-English message. Output line format:
`[CALL_ID] date — agent — call_type (direction, channel, N min)`; empty results
return `"No matching call records found."`

Scope: Tool 2 only (no agent/LangGraph/UI wiring). Manually verified in
`notebooks/test_call_lookup.ipynb` and ad-hoc: Stage-1 parsing + `_needs_llm`
decisions, deterministic full output, limit clamping (999→50) and enum coercion,
asc/desc sorting, empty-result message, Stage-2 merge precedence (regex field
survives an LLM override), and graceful fallback when the LLM is unavailable or
returns an unusable structured response. No changes to `policy_search.py`,
`config.py`, `data/calls.csv`, or `requirements.txt`.

---

## 2026-08-25 — Tool 2: configurable structured-output method

Made Tool 2's structured-output binding method configurable. `config.json` gains an optional
per-provider `structured_output_method` (`"json_schema"` / `"json_mode"` / `"function_calling"`);
`_structured_llm()` reads it and passes `method=` to `.with_structured_output(CallFilters, ...)`,
falling back to LangChain's default when the key is absent. Set `local_lmstudio.structured_output_method`
to `"json_schema"`.

Finding while testing against the live LM Studio server: the default local model `qwen/qwen3.8-27b`
is a *reasoning* model and does not produce usable structured output under any method — `json_schema`
returns empty content (grammar-constrained decoding collides with the model's `<think>` phase; even
`/no_think` and `enable_thinking=False` didn't help — it reasoned to the token limit), and LM Studio
rejects `json_mode` (`json_object` unsupported) and forced `function_calling` (`tool_choice` object
unsupported). A plain (unconstrained) call to the same model *does* return clean JSON, confirming the
issue is the structured-output path, not the model or server. Tool 2's error handling already covers
this: Stage 2 fails, it logs, and falls back to the regex-only result. To actually exercise Stage 2,
switch `active_provider` to a cloud model or load a non-reasoning instruct model locally. Documented
the option + caveat in CLAUDE.md. Scope: Tool 2 config only; no other modules touched.

---

## 2026-08-25 — Tool 2: dedicated Stage-2 extraction model + date normalization

Made Tool 2's Stage-2 extraction work against the local provider by pinning it to a small
non-reasoning instruct model, instead of the reasoning main model that couldn't emit structured
output (see prior entry).

- `config.json`: added optional per-provider `structured_output_model`; set
  `local_lmstudio.structured_output_model` to `qwen2.5-coder-1.5b-instruct` (kept
  `structured_output_method: json_schema`). The heavy `qwen/qwen3.8-27b` remains the provider's main
  `model`.
- `call_lookup.py`: `_build_chat_model(config, model=None)` now takes an optional model override;
  `_structured_llm()` passes `structured_output_model` so Stage 2 runs on the light model while the
  rest of the config is unchanged. Omitting the key reuses the main model; cloud providers need
  neither key.
- Bug fix: the instruct model returns dates as full datetimes (e.g. `2026-08-15T00:00:00Z`), which
  broke the lexical string comparison against the CSV's `YYYY-MM-DD` dates (a call exactly on
  `date_from` would be wrongly excluded). Added a `mode="before"` field validator on
  `date_from`/`date_to` that truncates any value to its leading `YYYY-MM-DD` (garbage → None).

Verified live: `"repair calls from this month"` now consistently resolves to
`date_from=2026-08-01, date_to=2026-08-31` and returns the 8 August repair calls across repeated
runs; the date validator normalizes datetimes and rejects garbage. Deterministic Stage-1 paths
unchanged. Scope: Tool 2 config + code only.

---

## 2026-08-25 — Tool 2: notebook updated for Stage-2 config + date fix

Refreshed `notebooks/test_call_lookup.ipynb` to test the latest Tool 2 behavior:
- Cell (a) now prints the Stage-2 `structured_output_method` and `structured_output_model` alongside
  the provider's main model, so it's clear which model does the extraction.
- Cell (e) adds a check for the `date_from`/`date_to` validator (full datetime → `YYYY-MM-DD`,
  unparseable → None).
- Cell (f) runs two real fuzzy-date Stage-2 queries ("...from this month", "...this week") on the
  configured instruct model and surfaces the resolved dates via the `filters -> ...` dev log.

All cells execute cleanly; both live queries resolved their fuzzy dates correctly
(this month → 2026-08-01..08-31; this week → 2026-08-16..08-31). Notebook only; no code changes.

---

## 2026-08-25 — Tool 2: notebook cell (f) shows per-field filter source

Rewrote cell (f) of `notebooks/test_call_lookup.ipynb` to identify, per query, where each resolved
filter came from. It now prints: Stage 1 (regex/fuzzy) output, whether Stage 2 (the LLM) was called,
and the final filters with each field tagged `[regex/fuzzy]`, `[LLM]`, or `[default]` (comparing the
regex dict against the merged `CallFilters`). Internal dev logs are suppressed for readability, and a
deterministic query is included so an all-`[regex/fuzzy]`, no-LLM case is visible for contrast.
Verified live: fuzzy-date queries show `date_from`/`date_to` tagged `[LLM]` while enum fields stay
`[regex/fuzzy]`. Notebook only; no code changes.

---

## 2026-08-25 — Tool 3: QA Scorer (`src/tools/qa_scorer.py`) implemented

Filled in the previously 0-byte `src/tools/qa_scorer.py` stub with Tool 3, following the Tool 1 /
Tool 2 conventions (config via `src.config`, provider-agnostic chat model, structured output via
`.with_structured_output()` bound to a Pydantic model, string-only returns).

- Public API: `score_call(transcript, call_id="", policy_context="") -> str`. Scores a transcript
  against a fixed 8-parameter binary rubric (greeting, identity_verification,
  problem_acknowledgement, call_classification, solution_offered, policy_compliance,
  professional_tone, proper_closure) and returns a readable plain-text scorecard for the UI/demo.
- Structured output: `QAResult` (a `ParamResult{passed: bool, justification: str}` per parameter),
  bound with `.with_structured_output(QAResult)`. The `RUBRIC` list is the single source of truth for
  the parameters, their report order, and their descriptions.
- Score is computed in Python, never self-reported by the LLM: overall = count of PASS params (X/8);
  overall verdict = PASS iff score >= 6 (`PASS_THRESHOLD`).
- Hard dependency on Tool 1: when the caller passes no `policy_context`, `score_call` calls
  `search_policy_with_context(transcript)` itself and uses the retrieved chunks as the ONLY basis for
  `policy_compliance`. The prompt forbids judging param 6 from general knowledge. call_type isn't a
  param here (the graph will pass `policy_context` directly when it knows the exact call_type), so
  routing is done on the transcript.
- policy_compliance can never pass without policy context: if retrieval raises or returns no chunks,
  scoring proceeds with an explicit "NO POLICY CONTEXT AVAILABLE" marker in the prompt AND
  `policy_compliance` is force-set to FAIL in code with a "no policy context available" note — so a
  hallucinated PASS can't slip through.
- Error handling / robustness: retrieval failure is caught (scores without context, forces param 6
  FAIL); an LLM/structured-output failure is caught and returned as a plain-English message; empty
  transcript returns a clear message. Every path returns a string — never a stack trace.
- Client lifecycle: the structured-output scorer is built ONCE at module load (mirrors Tool 1), and
  honors the active provider's `structured_output_method` / `structured_output_model` (so the local
  reasoning model pins the small instruct model, same as Tool 2).

Verified: `python -c "from src.tools.qa_scorer import score_call"` imports cleanly (module-load
client builds without error), and the empty-transcript guard returns its message. Scope: Tool 3 only
— no LangGraph, agent wiring, or "score N calls" chaining (that lives in the graph, a later step).
`policy_search.py`, `call_lookup.py`, `config.py`, and `data/calls.csv` were not touched.

---

## 2026-08-25 — Data: `sla_met` column + `data/qa_weights.csv` (rubric weights)

Groundwork for a future 9th QA rubric parameter (`sla_met`). Data-only change — `qa_scorer.py` was
NOT modified; wiring the weights + new parameter into the scorer is a separate later step.

- `data/calls.csv`: added a binary `sla_met` column (Yes/No) as the last column. Fabricated, and
  aligned with the dataset's documented bad calls — the 17 known-bad call_ids are `No`, the other 33
  are `Yes` — so a QA-failing call also reads as an SLA miss. Rewritten via pandas with
  QUOTE_MINIMAL, so the multi-line quoted transcripts are preserved unchanged (still 50 rows).
  Violations by channel: phone 11, chat 5, email 1.
- `data/qa_weights.csv` (new): per-category rubric weights, columns
  `parameter, weight_inbound, weight_outbound, weight_email`, one row per rubric parameter (9 rows,
  the 8 existing + `sla_met`). Each category column sums to exactly 100 (asserted in the build script
  before writing). Weighting rationale: `identity_verification` is higher on outbound (customer
  didn't initiate contact → higher impersonation risk); `policy_compliance` and `sla_met` are higher
  on email (written, auditable channel where breaches are unambiguous and costly).
- Category assumption (flagged, not buried): `inbound`/`outbound` apply to phone and chat rows via
  the `direction` column, while `email` is its own category regardless of direction — email rows here
  carry no meaningful inbound/outbound distinction. This assumption is documented in the build
  script's docstring.

Build script lives in the session scratchpad (not committed). Verified: both files reread cleanly,
`calls.csv` is 50×9 with 33 Yes / 17 No, and all three weight columns sum to 100. Scope: data only —
no code touched.

---

## 2026-08-25 — Tool 3: wired `sla_met` (9th parameter) + per-category weights

Extended `src/tools/qa_scorer.py` from an 8-parameter unweighted rubric to a 9-parameter WEIGHTED
one, consuming the data added earlier (`data/calls.csv` `sla_met` column, `data/qa_weights.csv`).

- 9th parameter `sla_met` is DETERMINISTIC, not LLM-judged: read from the call record for `call_id`
  (`sla_met == "Yes"` -> PASS). It is deliberately excluded from the `QAResult` structured-output
  schema and the scoring prompt — the LLM never sees or judges it. Mirrors the "data/arithmetic
  belongs in Python, not the LLM" rule already applied to the overall score. If the record is
  unavailable (no `call_id`, id not found, or missing value) `sla_met` FAILs with a
  "no SLA data available" note — same defensive pattern as policy_compliance's "no policy context".
- Weighting: `data/qa_weights.csv` is loaded once (lru_cache) into `{category: {parameter: weight}}`.
  The overall score is now the sum of the PASSED parameters' weights out of 100 (each category sums
  to 100, so it reads as a percentage). PASS requires >= 60% (`PASS_FRACTION`), replacing the old
  "6 of 8" count. Score/verdict still computed in Python.
- Category selection (drives which weight column applies): "email" for email-channel rows regardless
  of direction; otherwise the row's `direction` (inbound/outbound). Derived from the same call-record
  lookup that yields `sla_met`. When the record is unknown, weighting defaults to the `inbound`
  column (documented in the module docstring / `_DEFAULT_CATEGORY`).
- Data loads are cached and defensive: the call index reads only the 4 needed columns (skips the
  transcripts); a missing/broken weights file degrades to uniform weights; a missing call index makes
  `sla_met` unavailable — none of these raise. Every path still returns a string.
- Report now prints the call's category, a `(wNN)` weight next to each parameter, and a
  `Weighted score: earned/100 (NN%) — PASS/FAIL` footer. `RUBRIC` was renamed `LLM_RUBRIC` (the 8
  judged params); `PARAM_NAMES` is the full 9-in-order source of truth against the weights table.

Verified (deterministic paths, no LLM server needed): all three weight categories sum to 100 and
cover every rubric parameter; category logic correct (email overrides direction); `sla_met` resolves
Yes/No per record and FAILs-with-note for unknown/empty call_id; and a rendered outbound scorecard
computes 70/100 (identity_verification w20 + sla_met w10 failing) -> PASS. The full LLM-judged path
still requires the configured provider/server to be up. Scope: `qa_scorer.py` only; no data, config,
or other tools touched.

---

## 2026-08-25 — Config: local_lmstudio structured-output model -> qwen/qwen3-4b-2507

Changed `providers.local_lmstudio.structured_output_model` in `config.json` from
`qwen2.5-coder-1.5b-instruct` to `qwen/qwen3-4b-2507` (per user), to improve the quality of Stage-2
structured-output judgments used by Tool 2 (call_lookup) and Tool 3 (qa_scorer). Motivation: a live
end-to-end Tool 3 run on the 1.5B model produced weak judgments (wrongly PASSed professional_tone on
a clearly rude call; wrongly reported "no policy available" when policy context was in fact
retrieved) — the deterministic wiring was correct, but the tiny model's nuance was the bottleneck.
`structured_output_method` stays `json_schema`; the main reasoning model (`qwen/qwen3.8-27b`) and all
other providers are unchanged. No code touched. Not yet tested — the user will confirm when to re-run
the end-to-end scoring.

---

## 2026-08-25 — Tool 3: verified on qwen3-4b-2507, tone weight raised, notebook + docs

Follow-up to the model swap and the `sla_met`/weights wiring.

- Verified end-to-end on the new `qwen/qwen3-4b-2507` structured-output model (LM Studio, Instruct
  variant loaded). Clean call CALL-1001 -> 100/100 PASS with accurate transcript-quoted
  justifications; known-bad rude call CALL-1016 -> the model now correctly FAILs `professional_tone`
  (dismissive language) and `proper_closure` (abrupt close) — both of which the old 1.5B model wrongly
  passed — plus the deterministic `sla_met` FAIL. Weighted arithmetic confirmed. This is a clear
  quality jump over `qwen2.5-coder-1.5b-instruct`.
- `data/qa_weights.csv`: raised `professional_tone` from 10 -> 15 in all three category columns so
  rude handling costs more, offset by lowering the more mechanical `call_classification` 10 -> 5 to
  keep every category summing to exactly 100 (verified). Note: this alone does not flip CALL-1016
  below the 60% bar — with tone=15 it fails tone(15)+closure(5)+sla(10)=30 -> 70/100, still PASS. To
  make "rude but procedurally complete" calls FAIL overall would need a higher threshold or a gating
  rule (a future decision, not done here).
- `notebooks/test_qa_scorer.ipynb` (new): manual test harness for Tool 3, matching the other
  notebooks' style. Cells (a)-(g) are deterministic (no scoring LLM call): config/rubric, schema shape
  (asserts `sla_met` is excluded from `QAResult` yet is the 9th `PARAM_NAMES` entry), weights-sum-to-
  100 + tone==15 checks, category selection (email overrides direction), `sla_met` lookup (Yes/No/
  unknown/blank), weighted-score arithmetic (100/100 and the 70/100 rude-call case), and the empty-
  transcript + no-policy-marker guards. Cell (h) is the optional SLOW live end-to-end score on a good
  + a bad call. All deterministic cells were executed and their asserts pass. Import caveat documented
  in the notebook: importing `qa_scorer` pulls in `policy_search`, which probes its client at import,
  so for `local_lmstudio` even the deterministic cells need the server reachable to import (only cell
  (h) makes scoring calls).
- `CLAUDE.md`: marked Tool 3 implemented (stubs now only state.py/graph.py/app.py); added the
  "Architecture — Tool 3 (QA Scorer)" section; updated the structured-output config note to
  `qwen/qwen3-4b-2507` and why the 1.5B was replaced; added Tool 3 to the client-lifecycle section
  (built at import like Tool 1; weights + call index lru_cached like Tool 2); documented the new
  `data/calls.csv` `sla_met` column and `data/qa_weights.csv` (columns, sum-to-100 invariant,
  weighting rationale incl. the tone bump) in the Data section; listed the new notebook.

Scope: `data/qa_weights.csv`, `CLAUDE.md`, `progress.md`, and the new notebook. No tool source code
changed in this step (the earlier `config.json` model swap and `qa_scorer.py` wiring stand).

---

## 2026-08-25 — Tool 3: professional_tone is now a gating parameter

Added a hard gate to `src/tools/qa_scorer.py`: a FAIL on any parameter in the new `GATING_PARAMS`
tuple (currently just `professional_tone`) caps the overall verdict at FAIL regardless of the
weighted score — a high score can no longer excuse rude handling. The verdict in `_format_report` is
now `PASS iff (earned >= 60% of total AND no gating parameter failed)`; when a gate trips, the footer
appends `[professional_tone FAIL → automatic FAIL]` so the reason is visible next to a passing-looking
percentage. Motivation: raising the tone weight to 15 alone still left the rude CALL-1016 at 70/100
PASS; the gate is what actually makes "rude but procedurally complete" calls FAIL.

- Docstrings (module + `score_call`) updated to state the gate.
- `notebooks/test_qa_scorer.ipynb` cell (f) rewritten to demonstrate it: scenario 2 fails ONLY
  professional_tone → 85/100 but overall FAIL (asserts the "automatic FAIL" note); scenario 3 fails a
  NON-gating param (proper_closure) → 95/100 still PASS. Cell (a) now also prints `GATING_PARAMS`.
- `CLAUDE.md` Tool 3 section point 4 documents the gate.

Verified: `qa_scorer.py` compiles; notebook JSON valid with the gating scenario; and the gating
verdict logic checked in isolation (tone FAIL@85 → FAIL; non-gating@95 → PASS; all-pass → PASS;
tone-pass@55 → FAIL). NOTE: the notebook's deterministic cells could not be executed end-to-end this
time because the LM Studio server was down — and importing `qa_scorer` probes the endpoint at import
(the documented caveat), so import itself fails while the server is off. Re-run cells (a)-(g) once the
server is back up to confirm against the live `_format_report`. Scope: `qa_scorer.py`, the notebook,
`CLAUDE.md`, `progress.md`.

---

## 2026-08-26 — Tool 2 (call_lookup): additive `resolve_filters_with_status()`

**Change to a tool marked complete in a prior step** (per CLAUDE.md's workflow rule, flagging it):
added ONE new public function to `src/tools/call_lookup.py` for the Step 7 agent graph. Purely
additive — `_resolve_filters`'s signature and behavior are untouched, so every existing caller
(`lookup_calls`, the notebook) is unaffected.

- `resolve_filters_with_status(query) -> tuple[CallFilters, bool]`: same resolution as
  `_resolve_filters`, but also returns `llm_degraded` — True when Stage 2 was NEEDED but did not
  yield a usable result (either `_llm_filters` raised, or it returned None via its own catch-and-log
  / a needed-but-unavailable provider), so the answer fell back to regex-only. False when Stage 1
  alone sufficed (`_needs_llm` was False) or Stage 2 succeeded. `graph.py`'s `lookup_node` uses this
  to warn the user when a lookup silently degraded to keyword-only matching.
- It wraps the `_llm_filters` call in its own try/except HERE (in addition to `_llm_filters`'s
  internal catch) so a raise and a None result both map to `llm_degraded=True`.
- **Deliberate duplication:** the function mirrors `_resolve_filters`'s orchestration by hand
  (Stage-1 prefilter, `_needs_llm` decision, regex-wins merge). No shared helper was extracted
  because `_resolve_filters`'s signature was kept stable on purpose (the Step 7 decision). A
  header comment states this and points here; the two MUST be kept in sync by hand.
- `notebooks/test_call_lookup.ipynb` new cell (g): the drift guard. For a regex-only query AND a
  fuzzy-date query it asserts `resolve_filters_with_status()` returns the same `CallFilters` as
  `_resolve_filters()` (`.model_dump()` equality), with Stage 2 mocked deterministically so the
  fuzzy-date comparison tests the shared orchestration, not LLM run-to-run determinism; a third
  check asserts `llm_degraded=True` on a needed-but-raising Stage 2.

Verified: regex-only parity, fuzzy-date parity (mocked), and the degrade flag all pass; `lookup_calls`
and the existing notebook cells are unchanged in behavior. Scope: `src/tools/call_lookup.py`, the
notebook, `progress.md`.

---

## 2026-08-26 — Step 6 + Step 7: agent state + supervisor LangGraph (`state.py`, `graph.py`)

Filled the two remaining agent stubs (were 0-byte). `src/ui/app.py` stays a stub (Step 8).

**`src/agent/state.py`** — `AgentState` TypedDict with exactly: `messages`
(`Annotated[list, add_messages]`), `call_records`, `qa_scores`, `agent_name`, `next_tool`,
`pending_tools`, and the NEW `tool_trace`. Only `messages` carries a reducer; the other list fields
are plain, so appending nodes return `state.get(field, []) + [new]`. `tool_trace` records one dict
per data-fetching node (`{"tool", "source_file", "llm_degraded"}`) — captured now so Step 8's
Streamlit UI ("which tool was used for each response") needs no node-logic changes later.

**`src/agent/graph.py`** — the supervisor graph over the three tools:
- **Supervisor LLM**: `_build_chat_model` mirrors `qa_scorer._build_chat_model` exactly (same
  provider switch, same `**common` kwargs) with Tool 1's `_require_env_key` / `_check_reachable`
  guards copied in, so the client is built ONCE at import and fails fast on a bad/unreachable
  provider — consistent with Tool 1 and Tool 3. Plain `.invoke(prompt)`, no structured output.
- **Parsing**: `_parse_tools` reads a comma-separated tool list defensively (strip, lower, strip a
  trailing "."), keeps only `{policy, lookup, score}`, drops dupes. `_clean_content` strips the local
  reasoning model's `<think>...</think>` so its reasoning text can't be misread as tool choices.
- **Nodes** (each data-fetching node appends exactly one `tool_trace` entry): `supervisor_node` sets
  `next_tool`/`pending_tools` (no trace — not a data tool); `policy_node` runs `search_policy`
  (`llm_degraded` always False); `lookup_node` runs `lookup_calls` for display AND
  `resolve_filters_with_status` + `_apply_filters(_load_df(), filters)` to build `call_records`
  (`{call_id, transcript}`), resolving the transcript column defensively (no hardcoded `"transcript"`;
  raises if none found), and prepends a plain-language note to the shown message when
  `llm_degraded`; `scorer_node` scores each `call_records` entry via `score_call` and (decision noted
  here) appends **one `tool_trace` entry per call scored** so the trace row-count matches the number
  of reports — if `call_records` is empty nothing ran, so it returns a "look up a call first" nudge
  with NO trace entry.
- **Routing**: `route_decision` reads `next_tool` (→ policy/lookup/score/END); `route_after_lookup`
  chains scoring only when `pending_tools[0] == "score"`. `build_graph()` wires
  `StateGraph(AgentState)`: entry `supervisor` → conditional to the three tool nodes/END; `policy` →
  END; `lookup` → conditional (score/END); `score` → END.

Verified live against the reachable `local_lmstudio` server (`python -m src.agent.graph`, exit 0):
"What is the replacement window?" → policy → correct answer, one trace entry; "show me call 1042" →
lookup → the record, one trace entry; "look up call 1016 and score it" → supervisor emits
`lookup, score` → lookup then scorer, `tool_trace` accumulates BOTH entries, and the QA scorecard
correctly gates CALL-1016 to FAIL on `professional_tone` (70/100). Supervisor + routing were tested
in isolation first (parser unit checks incl. `<think>`-stripping, then the three routings), then the
tool nodes end-to-end, per the incremental Step 7 plan.

Notes/caveats:
- `requirements.txt` was NOT touched. Its `langgraph>=0.2,<0.3` pin is **stale** — the installed
  `langgraph` is 1.2.11 and the code works against it; flagging here rather than editing the pin (it
  was not in this step's scope).
- Importing `graph` pulls in `qa_scorer`/`policy_search`, which probe the LM Studio endpoint at
  import, so the server must be up to import (and to run the supervisor). The server was confirmed
  reachable before testing.

Scope: `src/agent/state.py`, `src/agent/graph.py`, `progress.md`.

---

## 2026-08-26 — Step 7 follow-up: per-call `tool_trace` score entries now carry `call_id`

Refinement to the just-added `scorer_node`. It appends one `tool_trace` entry per call scored, but
the entries were identical (`{"tool": "score", "source_file": ..., "llm_degraded": False}`) — so a
chained `lookup -> score` turn that scored N calls produced N indistinguishable entries, and Step 8
(the Streamlit UI) could not tell which entry belongs to which call when showing "which tool produced
this per message." Fixed by stamping each score entry with its `call_id`
(`{"tool": "score", "call_id": record["call_id"], ...}`).

- The `call_id` key is present ONLY on per-call tool entries; `policy`/`lookup` nodes are one-per-run
  and omit it, so consumers read it with `.get("call_id")`. `state.py`'s `tool_trace` doc now states
  this contract.
- Verified: a 3-call `scorer_node` run yields three score entries with distinct call_ids
  (CALL-1035 / CALL-1005 / CALL-1039) alongside the prior lookup entry (which has no `call_id`).

Scope: `src/agent/graph.py`, `src/agent/state.py`, `progress.md`.

---

## 2026-08-26 — Step 7 closeout: live degrade test, lookup `call_ids`, `<think>` provenance

Three verification/consistency items to close out Step 7.

**1. Live degrade-path test (previously unrun — the open verification item).** Exercised the
`lookup_node` degrade note with a REAL runtime failure (no mock of the note logic):
- Imported `graph` with the server up (fail-fast guards pass), then repointed the `local_lmstudio`
  `base_url` at a dead port and cleared `call_lookup._structured_llm`'s cache, so Stage 2's
  `.invoke()` made a real HTTP call that returned `Connection error.` — socket-equivalent to the
  server being down. (Used an unreachable endpoint rather than terminating the user's LM Studio, to
  avoid leaving their model unloaded; connection-refused is the same failure at the client.)
- Result: `_llm_filters` caught the real error → `resolve_filters_with_status` returned
  `llm_degraded=True` → `lookup_node` prepended the plain-language note. The note is TRUTHFUL: for
  "repair calls from this month", the degraded run fell back to keyword-only `call_type=repair` and
  returned 10 records (incl. July's CALL-1025/1027), vs. the 8 the working date-filter gives — i.e.
  the "this month" filter genuinely was not applied, exactly what the note warns about.
- **Important nuance found and confirmed:** a *fully*-down endpoint never reaches this note. Because
  `graph` imports `qa_scorer`/`policy_search`, which probe the endpoint AT import, a dead endpoint
  makes `import src.agent.graph` raise the fail-fast `RuntimeError` ("... endpoint ... is not
  reachable ...") — verified. So the degrade note only fires when the graph imported (server up at
  import) and Stage 2 fails at RUNTIME (endpoint drops mid-session, or the structured-output model
  returns invalid/empty output → `_llm_filters` returns None). Both are real, reachable paths; a
  cold-start with no server is a clean import error, not a silent degrade.

**2. `tool_trace` lookup entry now carries `call_ids`.** The score entries were given a singular
`call_id` last change; the lookup entry still forced Step 8 to cross-reference `call_records` to learn
which calls it touched — an inconsistent "read it off the trace for score, but not for lookup"
pattern. Fixed: the lookup entry now carries a plural `call_ids` list (one lookup entry spans N
calls; score entries stay one-per-call with singular `call_id`). Rationale: `tool_trace` exists so
Step 8 describes what a tool did WITHOUT reaching into other state — leaving lookup out defeated that.
The policy node touches no call and carries neither key (`.get(...)`). `state.py`'s `tool_trace` doc
updated to the full contract. Verified live in test 1 above: the lookup entry listed all 10 fetched
call_ids.

**3. `<think>`-stripping provenance: PRECAUTIONARY, not reactive.** `_clean_content` (strips the local
reasoning model's `<think>...</think>` before parsing tool words) was added defensively, reasoning
from config (the main model `qwen/qwen3.8-27b` is a reasoning model that CAN emit `<think>`), NOT in
response to an observed parse failure. In the Step 7 live tests the supervisor's raw output was clean
every time (`'\n\npolicy'`, `'\n\nlookup'`, `'\n\nlookup, score'` — no think-tags). Logging it
explicitly (rather than folding it into "defensive parsing") so the record is honest. Residual risk:
under other prompts/models the reasoning block could leak and, absent stripping, its prose could be
misread as tool words — hence the guard stays; but it is untested against a real think-tag leak, so if
the supervisor ever misroutes, this is the first thing to re-examine.

Scope: `src/agent/graph.py`, `src/agent/state.py`, `progress.md`. (`config.json` was NOT modified —
the dead-endpoint tests mutated the in-memory `CONFIG` dict only; verified the file still points at
`127.0.0.1:1234`.)

---

## 2026-08-26 — Step 8: Streamlit chat UI with threaded memory + summarization

Filled the last 0-byte stub, `src/ui/app.py`, with the Streamlit chat interface — the project's final
functional deliverable (only the Step 9 README/polish pass remains). Per the user's request the UI is
not a plain per-turn invoke: it adds **threaded conversation memory** and **memory management**
(summarization), which required small, surgical edits to `graph.py` as well (flagged below as changes
to a completed step, per the workflow rule).

**`src/ui/app.py` (new):**
- Chat over the compiled supervisor graph, built ONCE via `@st.cache_resource` (Streamlit reruns
  don't rebuild the LLM client). A graph-import/provider failure renders as a friendly `st.error` +
  `st.stop()`, never a traceback.
- **Threaded memory:** one `AgentState` lives in `st.session_state.agent_state` and is threaded
  through every turn — `messages` accumulate, `call_records` (the calls *in focus*) persist. Each
  turn appends a `HumanMessage`, clears `tool_trace` (so the returned trace is exactly this turn's,
  and stays bounded), invokes the graph, and stores the returned state back. A separate
  `st.session_state.display` list holds the rendered transcript so the FULL conversation stays on
  screen even after the agent's memory is compacted.
- **Tool visibility:** each assistant turn shows a `🔧 Tool(s) used: …` caption from that turn's
  `tool_trace`, plus a degraded-lookup warning when any entry's `llm_degraded` is true.
- **Memory management:** after each turn, if the conversation reaches `SUMMARY_TURN_THRESHOLD` (6)
  user turns, `_maybe_summarize` replaces the older messages with a single `SystemMessage` summary
  (via `graph.summarize_history`) and keeps the last `KEEP_RECENT_MESSAGES` (4) verbatim; a one-time
  "🗂️ Earlier conversation summarized to manage memory" note is rendered and stored in `display`.
  Keeping the recent tail then re-summarizing only when it regrows naturally throttles how often this
  fires.
- Sidebar: the blueprint §15 sample queries as buttons (set `pending_input`, consumed on the next
  run), the active provider/model from `src.config.CONFIG`, and a "Clear conversation" reset.

**`src/agent/graph.py` (surgical edits to a completed step):**
- `SUPERVISOR_PROMPT`: added one rule + examples so a follow-up that scores ALREADY-looked-up calls
  ("score them / those / these") routes to `score` alone, while naming which calls to score
  ("Score Rahul's last 5 calls") still routes to `lookup, score`. Other rules unchanged.
- `lookup_node`: now **replaces** `call_records` with the current lookup instead of appending, so the
  retained records are always the latest lookup (the "calls in focus"). This is what lets a threaded
  "score them" score exactly the last lookup rather than re-scoring stale records; within a single
  chained `lookup, score` turn it is behavior-identical.
- New `summarize_history(messages) -> str`: compresses a message list to a short summary, reusing the
  import-time `_SUPERVISOR_LLM` (no new client) and never raising (falls back to a minimal note).

**Honesty note (kept in code + plan):** the supervisor routes on the *last* user message only, so
summarization's real benefit is **bounding stored memory** + demonstrating the concept — it does not
change routing. Full history is intentionally NOT fed into the keyword router, to keep routing stable.

`state.py`, the three tools, `config.json`, and `requirements.txt` were untouched.

**Verification:** `graph.py` + `app.py` compile. Live against the reachable `local_lmstudio` server:
single-turn routings unregressed (policy / lookup); threaded lookup→"score them" routes to `score`
alone and scores exactly the retained `call_records` (no re-lookup); `summarize_history` returns a
usable summary. Full UI run: `streamlit run src/ui/app.py` from the repo root (LM Studio must be up —
importing the graph probes the endpoint at import).

---

## 2026-08-26 — Step 9 (partial): README.md

Wrote the project `README.md` at the repo root (was a 0-byte file), the graded documentation
deliverable and the last outstanding build step. Follows the blueprint §13 section order (title,
problem, solution, architecture, tech stack, structure, setup, env vars, how-to-run, samples, design
decisions, limitations, future work), but grounded in what the code **actually** does today rather
than the blueprint's simplified early spec:

- Rubric documented as **9 parameters, weighted** with a `professional_tone` hard gate (not 8
  unweighted); `sla_met` called out as deterministic (read from the record, never LLM-judged).
- Retrieval documented as **hybrid FAISS + BM25** (`EnsembleRetriever`, RRF), not dense-only.
- Dataset as **50 calls** (33 good / 17 bad); providers selected via `config.json` `active_provider`
  (default `local_lmstudio`), with the import-time fail-fast client noted.
- ASCII architecture diagram reflects the real `graph.py` wiring — supervisor → conditional →
  policy/lookup/score, plus the `lookup → pending_tools → score` chaining edge.
- The three worked samples use **real data**: Rahul's actual last-3 calls (CALL-1001/1034/1006) and
  the CALL-1016 scorecard (70/100 FAIL via the tone gate), verified against `data/calls.csv`.

**Scoping decisions (with the user):** kept the existing `print("[tool] …")` dev logs (no migration to
the `logging` module this step — listed under Future improvements instead); error handling was already
thorough, so nothing added there.

Scope: `README.md`, `progress.md`. No source code, config, or data changed. **Still outstanding**
(deferred, not part of this step): committing the uncommitted Steps 6–8 work, refreshing the stale
`CLAUDE.md` (still calls `state.py`/`graph.py`/`app.py` 0-byte stubs), the `feature/tool-3-qa-scorer`
branch-name mismatch, and tracking `call_center_agent_blueprint.md`.

---

## 2026-08-26 — Role-based access control (Supervisor vs Customer) + role-aware UI

**Change to completed steps 6/7/8** (flagged per the workflow rule). Added a role toggle so the app
can be demoed as either a **Supervisor** (full access) or a **Customer** (policy questions only),
with the restriction enforced in the graph — not just hidden in the UI.

- **`src/agent/state.py`:** added a `role` field to `AgentState` (`"supervisor"` | `"customer"`).
  Documented in the field list.
- **`src/agent/graph.py`:** `supervisor_node` now reads `state["role"]`. New `CUSTOMER_ALLOWED_TOOLS`
  (`("policy",)`) and `CUSTOMER_REFUSAL` message. For a customer, parsed tools are filtered to the
  allowed set; if the customer's request routed to a disallowed tool (lookup/score) the node **emits
  the refusal `AIMessage` and ends the turn** (rather than silently ending with no answer). Supervisor
  behavior is unchanged (all three tools). Role read defensively with `.get`/default `"supervisor"`,
  so pre-existing callers and the `__main__` smoke test still work.
- **`src/ui/app.py`:** a **View as** radio (Supervisor / Customer) at the top of the sidebar, above
  "Try a sample", with a caption stating each role's access. `SAMPLE_QUERIES` became
  `SAMPLE_QUERIES_BY_ROLE` so the sample buttons swap per role (supervisor: lookup/score/policy mix;
  customer: policy questions only). The selected role is stamped onto `agent_state["role"]` each turn
  before `graph.invoke`, and `_fresh_agent_state` seeds `"role": "Supervisor"`.

Verified end-to-end through the compiled graph (headless, LM Studio up): customer + policy question →
policy runs and answers; customer + "show me call 1042" → DENIED with the refusal (no lookup);
customer + "score call CALL-1016" → DENIED with the refusal (no score); supervisor + "show me call
1042" → lookup runs and returns CALL-1042. Streamlit app restarted on :8501 with the new code.

Scope: `src/agent/state.py`, `src/agent/graph.py`, `src/ui/app.py`, `progress.md`. No config, data, or
tool source changed.

---

## 2026-08-26 — Tool 3: scorecard rendered as a Markdown table

**Change to completed Tool 3** (flagged per the workflow rule). The QA scorecard was a wall of
plain-text `[PASS] param (wNN) — long justification` lines, which in the Streamlit chat rendered as an
unreadable block. `qa_scorer._format_report` now emits a **Markdown table** so `st.markdown` shows a
real table (and it still reads fine as text in notebooks/CLI). User chose the "Why column" layout.

- Table columns: **Parameter | Result | Weight | Why**, Result as `✅ PASS` / `❌ FAIL`. Heading
  `#### QA Scorecard — CALL-XXXX` + a `*Category: … — weights sum to 100*` subline, then a bold
  `**Weighted score: earned/100 (NN%) — PASS/FAIL**` footer; a gating trip adds
  `⚠️ _professional_tone FAIL → automatic FAIL_` on its own line.
- New `_md_cell()` helper makes each justification table-safe (collapses whitespace/newlines, escapes
  `|`). The weighted-score arithmetic, gating logic, and `PARAM_NAMES` ordering are unchanged.
- Footer intentionally keeps the `— PASS` / `— FAIL` / `automatic FAIL` substrings the Tool 3 notebook
  asserts on (`test_qa_scorer.ipynb`), so those checks still pass; no notebook edit needed.

Verified: (a) `_format_report` on a constructed results dict renders a valid table with an escaped
pipe in a justification; (b) live end-to-end through the graph — `score call CALL-1016` (supervisor)
→ lookup → score → a rendered table, 70/100 FAIL with the gating note and correct FAILs on
professional_tone / proper_closure / sla_met. Streamlit app restarted on :8501.

Scope: `src/tools/qa_scorer.py`, `progress.md`. No other tool, the graph, the UI, config, or data
changed.

---

## 2026-08-26 — Config: switch active provider to Gemini (+ token bump)

Switched `config.json` `active_provider` from `local_lmstudio` to **`gemini`** (user pasted a working
`GOOGLE_API_KEY`; verified with a live `models/gemini-2.5-flash` invoke). This removes the LM Studio
dependency — the whole agent now runs on cloud Gemini (faster, sharper judgments).

- Also raised `providers.gemini.max_output_tokens` **500 → 2000**. At 500, Gemini's structured output
  for Tool 3 truncated after the first parameter (`{"greeting": {"passed": true}}` → 7 missing-field
  validation errors → "scoring could not be completed"). 2000 gives the 8-parameter `QAResult` room;
  policy answers are unaffected (it's a ceiling). Cloud providers need no `structured_output_method` /
  `structured_output_model` — LangChain's default binding works.
- Note: the **running Streamlit process caches its LLM client at import**, so changing `active_provider`
  only takes effect after an app restart (this was the "why is it still using local?" symptom).

Verified end-to-end on Gemini through the graph: a policy question answers correctly; `score call
CALL-1016` → lookup → score renders the full 9-parameter table (60/100 FAIL, professional_tone gate
fires). Scope: `config.json`, `progress.md`.

---

## 2026-08-26 — UI: Stop button (cooperative cancellation) + threaded turns

**Change to completed steps 7/8** (flagged). Added a **Stop generating** button to the Streamlit UI,
which required running each turn on a background thread (Streamlit can't process a click while a
synchronous callback blocks) and a cooperative cancel flag in the graph.

- **`src/agent/graph.py`:** a process-wide `threading.Event` (`_CANCEL`) with `request_cancel()` /
  `reset_cancel()` / `is_cancelled()`. `scorer_node` checks `is_cancelled()` **between** calls in its
  per-call loop: on a Stop it breaks, returns whatever it scored so far, and appends
  `_⏹ Scoring stopped — the remaining calls were not scored._`. So Stop takes effect at the next call
  boundary (its main value is halting a multi-call score like "score Rahul's last 5 calls"), not
  mid-token within a single call.
- **`src/ui/app.py`:** `_run_turn` replaced by `_start_turn` (spawns a daemon thread running
  `graph.invoke`, writing only into a plain `result_box` dict — never `st.session_state` from the
  worker; `add_script_run_ctx` attached, guarded import) + `_finalize_turn` (runs in the main thread
  once done: stores state, appends the assistant entry + any summary note). `main()` now has a
  **running/polling branch**: while a turn runs it shows "💭 Thinking…" + the Stop button and reruns
  every `POLL_SECONDS` (0.3s); Stop calls `request_cancel()`; sample-button clicks are ignored
  mid-turn. `reset_cancel()` is called at the start of each turn.

Verified: all three files compile; graph cancel helpers import and toggle; full Gemini turn (policy,
and lookup→score) runs through the new threaded path and renders correctly. The interactive
click-during-generation behavior of the Stop button was not automatable from here (headless), so it
should be eyeballed in the browser — e.g. run "score Rahul's last 5 calls" and click Stop; it should
halt after the current call with the "stopped" note. App restarted on :8501 (Gemini).

Scope: `src/agent/graph.py`, `src/ui/app.py`, `progress.md`.

---

## 2026-08-26 — Perf: QA scorer skips the wasted policy-answer generation

**Change to completed Tools 1 & 3** (flagged). `qa_scorer` only needs the retrieved policy *chunks*
for `policy_compliance`, but `search_policy_with_context` also ran `_GENERATE(...)` to produce a
written answer that the scorer threw away — a wasted LLM call, and on the local *reasoning* model
(qwen3.8-27b, with its `<think>` phase) the slow one that dominated each score.

- `policy_search.search_policy_with_context(query, call_type=None, generate_answer=True)` — new
  `generate_answer` flag; when False it skips `_GENERATE` and returns `answer=""`. Default True, so
  `search_policy` and every other caller are unchanged.
- `qa_scorer._retrieve_policy_context` now calls it with `generate_answer=False`. Net effect: each
  `score_call` drops from 2 LLM calls to 1 (scoring only), which is what made the validation run below
  actually complete on local (the prior 2-call version didn't finish a single call in 7 min).

Scope: `src/tools/policy_search.py`, `src/tools/qa_scorer.py`, `progress.md`.

---

## 2026-08-26 — Eval: QA scorer validation harness ("trust metric") + first results

Added `src/eval/validate_scorer.py` (+ `src/eval/__init__.py`) — the project's first *validation* (as
opposed to smoke-test) harness. It scores calls and measures the scorer against the documented ground
truth in `data/README_DATA.md`, turning an unfalsifiable score into a checkable claim. Reports:
(1) overall verdict accuracy (bad→FAIL, good→PASS), (2) defect-detection recall — did the LLM FAIL the
*specific* parameter each bad call is supposed to fail (sla_met excluded as deterministic), and
(3) false param-alarms on good calls. Ground truth (expected-FAIL params per bad call) is hand-encoded
from the answer key so it doesn't depend on fragile text parsing. Run:
`python -m src.eval.validate_scorer [--limit N] [--all]`; results parsed back from the scorecard
Markdown table via `_parse_report`.

**First run (local qwen3-4b-2507 structured output, 8-call balanced sample = 4 bad + 4 good):**
- Overall verdict accuracy **5/8 (62%)** — false alarms on good calls **0**; but **3 bad calls scored
  PASS** (CALL-1006 no-greeting, CALL-1010 no-identity, CALL-1013 no-closure).
- Defect recall **3/4 (75%)** — at the *parameter* level the LLM did FAIL identity_verification (1010)
  and proper_closure (1013); it only missed greeting on 1006. False param-alarms on good calls
  **3/32 (9%)**.
- **Key finding the metric surfaced:** the LLM judgments are decent, but the **PASS/FAIL policy is too
  lenient** — only `professional_tone` gates, so a call correctly flagged as missing identity
  verification or closure still clears 60% and PASSes overall. Catching a defect at the param level
  doesn't change the verdict unless it's the gating param or breaches the weight threshold. Actionable
  lever (not yet applied): make the compliance-critical params (identity_verification, proper_closure,
  policy_compliance) gating too, or raise the threshold.
- Caveat: n=8 is a small, directional sample. Provider left on **`local_lmstudio`** (config reverted
  from gemini) because Gemini's free-tier rate limit stalled the run (7-min hang, no call completed).

Scope: `src/eval/` (new), `config.json` (provider reverted to local), `progress.md`.

---

## 2026-08-26 — UI: page title/header follow the selected role

The page was always titled "Call Center QA Agent" regardless of role. Now the browser tab title,
header, and subtitle switch with the **View as** toggle: Supervisor → "📞 Call Center QA Agent"
(the internal QA tool); Customer → "💬 Customer Care Agent" (the customer-facing help view).

- New `ROLE_UI` map in `src/ui/app.py` holds each role's `icon` / `title` / `caption`.
- The role radio now uses `key="role"` (instead of a manual `index=` + `st.session_state.role = role`
  assignment). Because keyed-widget state is restored into `st.session_state` *before* the script
  body runs, `main()` can read the role at the very top and set `st.set_page_config(page_title=…)` +
  `st.title(…)` from it — so the title updates on the **same rerun** the role changes, no one-turn
  lag. `_init_state` seeds a default `role` before the widget is created.

Verified: app compiles and restarts clean on :8501. Scope: `src/ui/app.py`, `progress.md`.

---

## 2026-09-08 — Tool 4 (Order Lookup) + customer agent mode over orders

The Customer role could only ask policy questions, so the customer-facing half of the app had
nothing real to answer. Added **Tool 4 — Order Lookup** (`src/tools/order_lookup.py`) and wired it
into the supervisor graph as a customer-allowed tool, so the Customer view now answers the questions
a customer actually asks: *where is my order, what's its status, when will it arrive, did my refund
go through*.

**Data — three new standalone tables** (`data/orders.csv` 40 rows `ORD-5001`–`ORD-5040`,
`data/shipments.csv` 33 rows, `data/returns.csv` 8 rows), joined on `order_id`. Deliberately **not**
linked to `calls.csv` — their own 12 customers, no `call_id` column — so the QA dataset and the order
dataset stay independent and neither constrains the other. Dates run `2026-08-02` → `2026-09-07`.
Every customer's **first name is unique**, which is what lets Stage-1 regex resolve "Neha's orders"
with no LLM. Columns, closed vocabularies, and the demo-worthy orders (each exercising a different
join shape — order-only, in-transit, all-three-tables, denied refund) are documented in
`data/README_DATA.md`.

**The tool** is a deliberate structural copy of Tool 2 — same two-stage extraction, so the two tools
behave identically and only their vocabularies differ:

- **Stage 1** (regex/enum, no LLM) resolves `order_id` (`order 5012` / `#5012` / `ORD-5012`),
  customer (full name **or** first name), `status`, `category`, `carrier`, `payment_status`,
  `refund_status`, a row limit + sort order, and the unambiguous dates. `_match_enum` gained one
  change over Tool 2's copy: underscored enum values are matched against natural spacing too
  (`re.escape(value).replace("_", "[ _]")`), so "out for delivery" resolves `out_for_delivery`.
- **Stage 2** escalates only on fuzzy dates or a total Stage-1 miss, binds `OrderFilters` via
  `.with_structured_output(...)`, and **regex always wins the merge**.
- The client is **lazy** (`lru_cache`), like Tool 2 and unlike Tools 1/3 — a plain `order 5031`
  lookup must work with the provider down, and importing the module never touches the network.
  Verified: the whole deterministic suite passes with LM Studio stopped.
- `_build_chat_model` was **imported from `call_lookup`** rather than copied a fourth time
  (`policy_search`, `qa_scorer`, and `graph` each still carry their own). The import is free —
  `call_lookup`'s client is lazy too, so `import order_lookup` still builds nothing.
- `_load_df()` left-joins the three CSVs, reads everything as `str` and `fillna("")`, so the
  formatter tests optional shipment/return blocks with a plain truthiness check instead of NaN
  handling. Output is a header line per order plus a `Shipment:` and/or `Return:` line, present only
  when that table has a row.
- **`DEFAULT_LIMIT = 10`** is applied when a request resolves *no* filters at all ("show me my
  orders") so an unfiltered question returns a recent slice instead of dumping all 40 rows.

**Graph wiring** (`src/agent/graph.py`): new `order` tool word in `_VALID_TOOLS`, a new `order_node`
(one `tool_trace` entry, `source_file` naming all three CSVs), an edge straight to `END`, and
`CUSTOMER_ALLOWED_TOOLS` widened to `("policy", "order")`. The supervisor prompt gained the tool line,
a rule that spells out the distinction the model would otherwise get wrong (*an ORDER is a purchase;
a CALL is a support conversation — never use `lookup` for an order question*), and three examples.
`CUSTOMER_REFUSAL` was reworded — call records and QA scores remain supervisor-only.

`order_node` reports `llm_degraded: False` unconditionally: Tool 4 has **no**
`resolve_filters_with_status` twin. That degraded-flag pattern requires hand-syncing two copies of the
same orchestration (see the standing NOTE in `call_lookup.py`), and it was not worth duplicating for
a tool whose Stage-2 path is rarer still. If the "keyword-only matching" warning turns out to matter
for orders, that is the lever to add.

**UI** (`src/ui/app.py`): `order` added to `TOOL_LABELS`, the Customer sample queries replaced with
four order questions plus two policy ones, and the Customer role caption/help updated from "policy
questions only" to policy **and** order status. `src/agent/state.py`'s `role` docstring updated to
match.

Verified (LM Studio down, so this is the fail-soft path): `python -m src.tools.order_lookup` across
six queries; the new `notebooks/test_order_lookup.ipynb` cells (a)–(e) executed clean — Stage-1
parsing, `_needs_llm` decisions, end-to-end output, and asserts pinning **regex-wins-the-merge**, the
**LLM-outage fallback**, the `DEFAULT_LIMIT` cap, and the empty-result string. Graph wiring checked
structurally against a stub `/v1/models` endpoint: `order` is a compiled node, `route_decision` routes
to it, `CUSTOMER_ALLOWED_TOOLS == ("policy", "order")`, and `order_node` returns a message plus
exactly one trace entry. Cell (f) (live Stage 2) is untested — it needs the provider up.

Scope: `src/tools/order_lookup.py` (new), `data/orders.csv` / `data/shipments.csv` /
`data/returns.csv` (new), `notebooks/test_order_lookup.ipynb` (new), `src/agent/graph.py`,
`src/agent/state.py`, `src/ui/app.py`, `data/README_DATA.md`, `progress.md`.

---

## 2026-09-08 — UI: liquid-glass theme + fix `streamlit run` from the repo root

Two changes to `src/ui/app.py`.

**1. `streamlit run src/ui/app.py` was broken from the repo root.** It died at
`from src.config import CONFIG` with `ModuleNotFoundError: No module named 'src'` — Streamlit puts the
*script's* directory (`src/ui/`) on `sys.path`, not the directory it was launched from, so the
documented command never worked without an explicit `PYTHONPATH`. Fixed inside the app: a three-line
bootstrap puts `Path(__file__).resolve().parents[2]` (the repo root) on `sys.path` before the first
`src.` import — the same trick the test notebooks already use. Verified by relaunching with **no**
`PYTHONPATH` set. (The `# noqa: E402` on the following import is deliberate: it must come after.)

**2. Apple-style liquid-glass theme.** New module-level `GLASS_CSS` constant, injected once per rerun
via `st.markdown(..., unsafe_allow_html=True)` right after `st.set_page_config`. Streamlit exposes no
theming hook for translucent materials, so this is plain CSS over its `data-testid` hooks. The design
rules it follows (Apple HIG / *Designing Fluid Interfaces*), each of which is a comment in the block:

- **Glass needs something to blur**, so the app sits on a static ambient gradient and every panel is a
  translucent layer floating on *that* — never glass stacked on glass, which collapses legibility.
  The gradient is static on purpose: a slow looping background is a reduced-motion hazard.
- **Material weight encodes hierarchy** — the sidebar is the heaviest surface (structural), chat cards
  lighter, buttons lightest (interactive). Each carries a brighter top border, the edge where light
  catches the material.
- **Dense data goes on a solid-ish layer** — scorecard tables and code blocks inside a chat card get
  `--glass-bg-strong` rather than a second sheet of translucency (the vibrancy rule); captions get a
  little extra weight and tracking for the same reason.
- **Feedback on pointer-down, not release** — buttons take `transform: scale(0.97)` on `:active` over
  100ms.
- **Type** — the platform system font, negative tracking on headings (`-0.028em` on h1), near-zero on
  body.
- **Three accessibility fallbacks, all real:** `prefers-reduced-transparency` frosts the glass solid
  and drops every blur; `prefers-contrast: more` goes to near-solid surfaces with a defined border;
  `prefers-reduced-motion` keeps the material but removes the press transform. Light and dark palettes
  are both defined as tokens, switched by `prefers-color-scheme`.

**Selector check against Streamlit 1.62** (the pinned version): `stAppViewContainer`, `stHeader`,
`stSidebar`, `stChatMessage`, `stChatMessageAvatarUser`, `stChatInput`, `stBottomBlockContainer`,
`stAlert`, `stCaptionContainer` and `stButton` all still exist in the shipped frontend bundle.
`baseButton-primary` / `baseButton-secondary` do **not** — they were renamed — so the primary-button
rule was rewritten as `.stButton > button[data-testid="stBaseButton-primary"]`. Worth re-running that
grep against `streamlit/static` after any Streamlit upgrade; a renamed testid fails silently.

Verified: the app boots and serves HTTP 200 with no `PYTHONPATH` and no `ModuleNotFoundError`, and
every targeted testid was confirmed present in the installed bundle. **Not** visually verified — the
browser screenshot tooling timed out repeatedly against the Streamlit page, so the appearance itself
is unreviewed. Run `streamlit run src/ui/app.py` from the repo root (with the provider up) to judge it.

Scope: `src/ui/app.py`, `progress.md`.

---

## 2026-09-08 — Code review follow-up: three Tool 4 fixes

`/code-review` on the branch returned 8 findings. Three were mine and are fixed; the rest are
pre-existing and are recorded below rather than changed.

**1. (High) An explicit order id no longer picks up the words around it.** `_regex_filters` applied
every enum matcher unconditionally, so `"When will ORD-5033 be delivered?"` resolved
`{order_id: ORD-5033, status: delivered}` — and ORD-5033 is `out_for_delivery`, so the two filters
contradicted and the answer was **"No matching orders found."** That exact sentence was a Customer
sample query in the sidebar, so the shipped demo was broken. Fixed: a resolved `order_id` now returns
**alone** — it identifies exactly one row, so every other word in the sentence is the question, not a
filter.

**2. (Medium) An order id now requires its `ord`/`order`/`#` prefix.** The prefix was optional, so a
bare `\d{4}` claimed anything four digits long: `"orders after 2026-09-01"` → `ORD-2026`,
`"my 7999 headphones"` → `ORD-7999`. Worse, **any** regex match makes `_needs_llm` False, so Stage 2
never got the chance to resolve the date it had just stolen. A bare number now falls through to
Stage 2, which is what Stage 1 is meant to do with anything ambiguous. (Tool 2 carries the same
optional-prefix regex; it is less harmful there because call dates are not four digits, but it is the
same latent bug — not touched here, since Tool 2 was out of scope.) One subtlety worth remembering:
the `\b` has to live **inside** the `ord` branch — `#` is a non-word character, so a leading `\b`
never holds before it and `"#5012"` silently stopped matching until that was fixed.

Related: a status word sitting next to fuzzy date language is now dropped from Stage 1 (`"orders
placed this week"` is about the week, not `status=placed`). Stage 2 runs on fuzzy dates anyway, so
the LLM judges it instead of a hardcoded wrong answer.

**3. (Medium) The "their own orders" claim was false, and the sidebar demoed it.** `state.py` said the
customer role gets "policy + **their own** orders", but there is no identity anywhere in `AgentState`,
`lookup_orders` has no per-customer scoping, and the Customer sidebar's own sample query was *"Show me
Neha Gupta's orders"* — returning another person's email, items and amounts. Role gating controls which
**tools** a role reaches, never which **rows** a tool returns. Fixed by making the docs say that
(`state.py`, `graph.py`), replacing the sample query with "Which orders are out for delivery?", and
marking the ceiling with a `ponytail:` comment naming the upgrade path: put `customer_name` in
`AgentState` and force it into `OrderFilters` inside `order_node`, as a filter the LLM cannot widen.

**Test fixture that had to change.** Cell (e)'s merge-precedence assert used `"recent shipped orders"`
— under the new fuzzy-date rule `status` is no longer resolved there, so there was nothing for the
mocked LLM to fail to override and the test proved nothing (it failed loudly, which is the good
outcome). Rewritten to use a **carrier** (`"recent BlueDart orders"`), which the rule does not drop.
Four new asserts cover both fixes.

**Findings NOT fixed — all pre-existing, none touched by Tool 4:**

- `graph.py` `lookup_node` resolves the query **twice** (`lookup_calls` then
  `resolve_filters_with_status`), so a fuzzy-date lookup makes two independent structured-output calls
  at non-zero temperature. If they disagree, the user sees one set of calls while the chained scorer
  scores a different set. Also doubles latency on the slow path.
- `graph.py` `lookup_node` can **raise** (the missing-transcript-column `RuntimeError`, and an
  unguarded `_apply_filters`), breaking the every-path-returns-a-string contract the tools maintain.
- `app.py` renders only `messages[-1]`: a turn that routes nowhere echoes the **user's own message**
  back as the assistant's answer, and in a chained `lookup → score` turn the call listing (plus the
  degraded-extraction note) is never shown.
- `graph.py` `_CANCEL` is a process-wide `threading.Event` while `get_graph()` is `@st.cache_resource`
  — with two browser sessions, one user's Stop cancels the other's run.
- `eval/validate_scorer.py` `_parse_report` scans the whole report for `"— PASS"`, so LLM-authored
  justification text can flip a FAIL to PASS and **inflate** the trust metric.

Verified: all 13 Stage-1 cases assert-checked, notebook cells (a)–(e) clean.

Scope: `src/tools/order_lookup.py`, `src/agent/graph.py`, `src/agent/state.py`, `src/ui/app.py`,
`notebooks/test_order_lookup.ipynb`, `CLAUDE.md`, `progress.md`.

---

## 2026-09-08 — First live end-to-end run of Tool 4 + the customer agent mode

Ran the whole stack locally against the configured provider (LM Studio, `qwen/qwen3.8-27b` as the
supervisor + `qwen/qwen3-4b-2507` for structured output, both loaded via `lms load`). Everything above
had only ever been verified with the provider **down**; this is the first run with a real LLM in the
loop. Six turns through `build_graph().invoke(...)` — the same path the UI takes:

| role | request | routed | result |
|---|---|---|---|
| customer | "Where is my order 5031?" | `order` | ORD-5031, in transit, Ekart, ETA 2026-09-06 |
| customer | "When will ORD-5033 be delivered?" | `order` | ORD-5033, out for delivery — **the query the code review found broken**, now correct |
| customer | "Did my refund for order 5027 go through?" | `order` | RET-7027 approved, refund Rs 7,499 processing |
| customer | "What is the replacement policy?" | `policy` | 90-day window, proof of purchase, one per order |
| customer | "Show me call 1042" | *(denied)* | `CUSTOMER_REFUSAL` — role gating held |
| supervisor | "Show me Rahul's last 2 calls" | `lookup` | CALL-1001, CALL-1034 |

The supervisor model returned a clean single tool word every time (`_clean_content` handled the
reasoning model's leading whitespace/`<think>` output), and all three order queries answered from
Stage 1 alone — no Stage-2 network call.

Streamlit itself boots clean on :8501 with the `sys.path` fix and no `PYTHONPATH`. The glass theme is
**still not visually reviewed**: the browser screenshot tooling times out injecting into the Streamlit
page (tried repeatedly, twice on separate ports, plus a headless Chrome capture — all failed). The
appearance remains the one unverified thing in this branch.

Scope: `progress.md` (verification only — no code changed).

## 2026-09-14 — README synced from the `llm_projects/Call-Desk-Agent` submission copy

`README.md` replaced with the rewritten version (4 tools, Customer role, Mermaid architecture diagram,
full structure, run commands, sample I/O, testing, limitations). Added the files it references that
this copy lacked: `.env.example`, `docs/sample_outputs.md` (captured graph runs), `docs/blueprint.md`
(copy of `call_center_agent_blueprint.md`). NOT synced here: the code changes made in the submission
copy (print → logging, `sources` in policy answers, re-pinned `requirements.txt`) — the README's
"Logging" row and `Sources:` mention describe the submission copy, not this one.

## 2026-09-14 — UI screenshots + ACTIVE_PROVIDER override (mirrored from the submission copy)

- `docs/screenshots/` (5 PNGs) and a README "Screenshots" section, captured from the Streamlit UI on
  the local LM Studio provider.
- `src/config.py`: `ACTIVE_PROVIDER` env var overrides `config.json`'s `active_provider` for one run.
- `src/ui/app.py`: tool output newlines rendered as markdown hard breaks (multi-line lookup/order
  results were collapsing into one paragraph).
- Note: `src/config.py` here now also carries the `logging.basicConfig` from the submission copy;
  the tool modules in this folder still use `print`, which works unchanged.

## 2026-09-16 — Implementation plan: review fixes + mock sign-in

Wrote `docs/superpowers/plans/2026-09-16-review-fixes-and-login.md`: four TDD tasks covering the three
open code-review findings (UI renders only `messages[-1]`; `_CANCEL` is process-global across Streamlit
sessions; `_parse_report` can read a FAIL as PASS) plus a new mock email/password sign-in that grants
Supervisor only to listed accounts (replacing the free sidebar role radio). Tests are stdlib `unittest`
in a new `tests/test_review_fixes.py`, runnable offline by stubbing `policy_search`/`qa_scorer` and
forcing `ACTIVE_PROVIDER=openai` with a dummy key (mechanisms verified on this machine before writing
the plan). No code changed yet.

Scope: `docs/superpowers/plans/` (new), `progress.md`.

## 2026-09-16 — UI renders every reply of a turn (review finding 1)

`app.py` `_finalize_turn` rendered only `messages[-1]`, so a turn that routed nowhere echoed the
user's own message back as the answer, and a chained `lookup → score` turn never showed the call
listing (or its degraded-extraction note). Added `graph.turn_replies(messages)` — every message
after the last human message — and the UI now joins those with a blank line; an empty list renders
`NO_ROUTE_REPLY` instead of the echo. First automated test file: `tests/test_review_fixes.py`
(stdlib unittest, runs offline via stubbed heavy modules + `ACTIVE_PROVIDER=openai`).

Scope: `src/agent/graph.py`, `src/ui/app.py`, `tests/test_review_fixes.py`, `CLAUDE.md`, `progress.md`.

## 2026-09-16 — Stop is per-session (review finding 2)

`graph._CANCEL` was one process-wide `threading.Event` while `get_graph()` is `@st.cache_resource`,
so with two browser sessions one user's Stop cancelled the other's scoring run. The flag is now a
per-turn `Event` the UI creates in `_start_turn`, stores on the job, and passes as
`graph.invoke(state, config={"configurable": {"cancel": event}})`; `scorer_node(state, config)`
reads it through `is_cancelled(config)`. `request_cancel` / `reset_cancel` / `_CANCEL` removed.
Tests cover: no event → scores all; own set event → stops before the first call; another
session's unset event → unaffected.

Scope: `src/agent/graph.py`, `src/ui/app.py`, `tests/test_review_fixes.py`, `progress.md`.

## 2026-09-16 — Validator verdict parsed from the footer only (review finding 3)

`eval/validate_scorer._parse_report` scanned the whole report for `"— PASS"`, so an LLM-written
justification containing that text flipped a FAIL verdict to PASS and inflated the trust metric.
It now reads the verdict only from the `**Weighted score: …**` footer line; no footer → `"?"`.
Per-parameter parsing is unchanged.

Scope: `src/eval/validate_scorer.py`, `tests/test_review_fixes.py`, `progress.md`.

## 2026-09-16 — Mock sign-in gateway replaces the free role radio

Anyone could pick Supervisor in the sidebar, so the customer/supervisor split had no gate. Added
`src/ui/auth.py`: `SUPERVISOR_ACCOUNTS` (a plaintext mock email→password dict, `ponytail:`-marked)
and `resolve_role(email, password)` → `"Supervisor"` only on an exact match (email normalised,
`hmac.compare_digest` on the password), else `"Customer"`. `app.py` now shows a sign-in form until
`st.session_state.user` is set, derives `role` from it (the same value `_start_turn` stamps into
`AgentState.role`, so `supervisor_node` gating is what the login controls), and the sidebar radio
became "Signed in as … / Sign out". Customers are not password-checked (nothing customer-specific to
protect — no per-customer identity in state). Live check: ran headlessly via
`streamlit.testing.v1.AppTest` — first run shows the sign-in form with no chat input; an unknown
email and a wrong password both resolve to Customer; `qa.lead@example.com` / `supervisor123`
resolves to Supervisor and successfully builds the graph (Tool 1's FAISS index loads); Sign out
returns to the form. Chat-turn behavior (sample queries, scoring, `NO_ROUTE_REPLY`) was not driven
through AppTest per the task brief (it loops on `st.rerun()` and would hang headlessly) and was not
separately verified in a browser this session.

Scope: `src/ui/auth.py` (new), `src/ui/app.py`, `README.md`, `tests/test_review_fixes.py`, `progress.md`.

## 2026-09-16 — Fix wave from the whole-plan review: Stop was a no-op, non-ASCII password crash

- `graph.py`: under `from __future__ import annotations`, `config: RunnableConfig | None` is a string
  annotation LangGraph 1.2.11 does not recognise — it warned at `build_graph()` and called `scorer_node`
  with `config=None`, so the per-turn cancel Event never arrived and Stop did nothing. Signature is now
  `config: Optional[RunnableConfig] = None` (injected). New test drives cancel THROUGH the compiled graph
  (supervisor LLM patched to return `score`) and asserts `build_graph()` emits no `UserWarning`.
- `auth.py`: `hmac.compare_digest` on `str` raises on non-ASCII; now compares `.encode()`d bytes, so an
  accented/emoji password resolves to Customer instead of crashing the login form (+ test).
- `is_cancelled` tolerates a non-Event under `configurable["cancel"]`; `turn_replies` moved into the
  message-helpers section; `_fresh_agent_state()` role default → `Customer` (fail-closed, matches
  `_init_state`).

Scope: `src/agent/graph.py`, `src/ui/auth.py`, `src/ui/app.py`, `tests/test_review_fixes.py`, `progress.md`.

## 2026-09-17 — Plan: landing page + supervisor-only sign-in

Added `docs/superpowers/plans/2026-09-17-landing-page.md`. Design agreed with the user: the app
opens on a landing page (two-line headline, blurb, **Continue as a customer** / **Continue as a
supervisor**, 3-column "what it can do" row, existing glass theme). Customer → chat with no
account; Supervisor → the existing sign-in form, which becomes supervisor-only (wrong creds →
error, form stays; ← Back). Three tasks: landing + customer path, supervisor-only form, docs.
Tests via `streamlit.testing.v1.AppTest` in a new `tests/test_ui_flow.py`. No code changed yet.

Scope: `docs/superpowers/plans/2026-09-17-landing-page.md`, `progress.md`.

## 2026-09-17 — Landing page with two entry points (part 1: customer path)

The app opened straight on the sign-in form. It now opens on a landing page (`_render_landing`):
two-line headline, a blurb, **Continue as a customer** / **Continue as a supervisor**, and a
3-column "what it can do" row (`LANDING_FEATURES`), styled with the existing glass CSS. The
customer button signs in as `user="guest"` / `role="Customer"` with no form. A new
`st.session_state.login_requested` flag selects which pre-auth screen renders (landing by
default); Sign out resets it so it returns to the landing page. Tests: new
`tests/test_ui_flow.py` drives the flow headlessly with `streamlit.testing.v1.AppTest`
(landing shows both buttons and no chat input; customer button → Customer chat; sign out →
landing).

Scope: `src/ui/app.py`, `tests/test_ui_flow.py` (new), `progress.md`.

## 2026-09-17 — Sign-in form is supervisor-only (part 2)

The sign-in form is now reached only via **Continue as a supervisor**. Wrong or unknown
credentials show `Invalid email or password.` and keep the form (previously they silently
continued as a Customer — there is no longer any customer path through the form). A **← Back**
button returns to the landing page. `resolve_role` is unchanged; only `_render_login` checks its
result for `"Supervisor"`. Tests added to `tests/test_ui_flow.py`: supervisor button shows the
form; bad creds → error, nobody signed in; a listed account → Supervisor chat; Back → landing.

Scope: `src/ui/app.py`, `src/ui/auth.py` (docstring), `tests/test_ui_flow.py`, `progress.md`.

## 2026-09-17 — Docs for the landing page

README and CLAUDE.md now describe the landing page, the no-account customer path, the
supervisor-only sign-in, and the second test suite (`tests/test_ui_flow.py`).

Scope: `README.md`, `CLAUDE.md`, `progress.md`.

## 2026-09-17 — Supervisor accounts move to a sheet; Forgot-password flow

`SUPERVISOR_ACCOUNTS` (a dict in code) is replaced by **`data/supervisors.csv`** (`email,password`,
plaintext by choice — it's a demo sheet meant to be edited by hand). `src/ui/auth.py` now exposes
`load_accounts()` (re-reads the file each call; `{}` if missing), `resolve_role()` (same contract,
backed by the sheet), `email_exists()` and `set_password()` (rewrites the sheet; `False` for an
unknown email). The sign-in page gains **Forgot password?** → `_render_reset` in `app.py`: step 1
asks for the email (unknown → error), step 2 asks for a new password + confirmation (empty /
mismatch → error) and writes it to the sheet, then returns to the sign-in form with a one-shot
"Password updated" note. Email-only reset, no verification code — `ponytail:`-marked in `auth.py`.
State: `reset_step` (`None`/`"email"`/`"password"`), `reset_account`, one-shot `reset_done`;
`_sign_out` clears `reset_step`. Gotcha hit and fixed: the state var was first named `reset_email`,
colliding with the widget key of the same name (Streamlit forbids assigning a widget's key after it
renders) — renamed to `reset_account`. Tests: `ResolveRole` (+4: seeded accounts, set_password
round-trip, unknown email refused, missing sheet → no supervisors) and a new `ForgotPassword`
AppTest class (+5: email step shown, unknown email, mismatch keeps the sheet, new password written
and signs in, Back) — both patch `auth.SUPERVISORS_CSV` to a temp copy so the real sheet is never
touched. 32/32 pass.

Scope: `data/supervisors.csv` (new), `src/ui/auth.py`, `src/ui/app.py`, `tests/test_review_fixes.py`,
`tests/test_ui_flow.py`, `README.md`, `CLAUDE.md`, `progress.md`.

## 2026-09-17 — Dead-code sweep

Scanned every top-level name in `src/` against all references (src, tests, notebooks) plus an
unused-import pass. Removed: `templete.py` (the Step-1 scaffold script — every file it creates has
existed for months); the unused `AIMessage` import in `src/ui/app.py`; the "Role radio" CSS block
in `GLASS_CSS` (the sidebar radio it styled was replaced by the sign-in flow); and
`AgentState.agent_name` (initialised in three places, never read or written by any node — the
`agent_name` that matters is `CallFilters.agent_name` in Tool 2, untouched). Nothing else was
dead: every other definition has at least one live caller. 32/32 tests pass.

Scope: `templete.py` (deleted), `src/ui/app.py`, `src/agent/state.py`, `src/agent/graph.py`,
`tests/test_review_fixes.py`, `progress.md`.

## 2026-09-18 — Order follow-ups answer about the order in focus

Bug: after "Did my refund for order 5027 go through?", the follow-up "when can I expect the
return" returned ten unrelated orders. Root cause: `order_node` hands `lookup_orders` only the
last user message; a follow-up names no order, so Stage 1 resolves `{}`, Stage 2 yields nothing
usable, `is_empty()` → `DEFAULT_LIMIT = 10` dump. The order the chat was already about was never
consulted. Fix: `order_lookup.focus_order_id(texts)` returns the single order id named in the most
recent message that names any (user "order 5027" / tool "[ORD-5027]"; a list reply naming several
→ `None`, no guessing). `lookup_orders(query, focus_order_id=None)` pins a filter-less request to
that order instead of applying `DEFAULT_LIMIT`; explicit filters in the request still win.
`order_node` computes the focus over `state["messages"]`. `ponytail:`-marked ceiling: "show me all
my orders" after discussing one order returns just that order until a customer/status/date is
named. Tests: new `OrderFocus` class (+5) in `tests/test_review_fixes.py`. 37/37 pass.

Not changed: `lookup_node` has the same shape (a filter-less call follow-up returns all 50 rows),
but supervisors name calls explicitly and "score them" already works via `call_records`.

Scope: `src/tools/order_lookup.py`, `src/agent/graph.py`, `tests/test_review_fixes.py`, `progress.md`.

## 2026-09-18 — `answer` route: reply from conversation memory

Bug: after scoring CALL-1016, "what was the call about?" was not answerable — the graph keeps
`messages` (summarized after 6 turns by the UI), but no node ever *read* them: the supervisor only
routed to the four data tools, each of which sees the last user message alone. (The error in the
screenshot itself — `Model has not started loading/has been unloaded` — was LM Studio auto-unloading
the 27B model, not a code fault.) Fix: a fifth supervisor route **`answer`** → `answer_node`, which
feeds the full transcript (`_transcript`, now shared with `summarize_history`) to the import-time
supervisor client with a "use ONLY the conversation, never invent" prompt. It fetches nothing, so it
appends no `tool_trace` entry (the UI badge is simply absent) and is in `CUSTOMER_ALLOWED_TOOLS`.
Prompt gains the tool, a back-reference rule and three examples; `_SUMMARY_PROMPT` now also asks
to preserve order ids so summarized order follow-ups keep working. Tests: `AnswerFromConversation`
(+3: route valid for customers, node sees prior replies + summary and appends no trace, follow-up
routes to `answer` through the compiled graph). 40/40 pass.

Scope: `src/agent/graph.py`, `tests/test_review_fixes.py`, `CLAUDE.md`, `progress.md`.

## 2026-09-18 — Filter-less lookup with calls loaded → `answer`; answer sees transcripts

Bug: after scoring CALL-1016, "what was this call about?" was routed by the supervisor LLM to
`lookup`, which — with no filters — dumped a page of unrelated calls. Two causes. (1) Routing was
pure LLM judgment and the 27B model misread the back-reference despite the prompt example. Fix: a
deterministic guard in `supervisor_node` — if the first routed tool is `lookup`, `call_records`
is non-empty, and `call_lookup._regex_filters(message)` resolves nothing with no fuzzy date
(`_FUZZY_DATE_RE`), the request is a back-reference to the loaded calls and becomes `answer` (a
trailing `score` is dropped too). Real Stage-1 matches and fuzzy dates still route to `lookup`;
with nothing loaded the LLM's choice stands. Same shape as the order-focus fix. (2) `answer_node`
only saw `messages`, and a call's transcript lives in `call_records`, so it could not actually
summarize the call. Fix: the prompt now includes "Call transcripts currently loaded" from
`call_records` (the latest lookup). Prompt gains a "what was this call about? summarize it"
example. Live check: `show me call 1016` → `what was this call about?` routes to `answer` and
returns a correct one-paragraph summary of the transcript. Tests: +2 in `AnswerFromConversation`
(guard matrix incl. the nothing-loaded case; transcripts reach the prompt). 42/42 pass.

Scope: `src/agent/graph.py`, `tests/test_review_fixes.py`, `progress.md`.

## 2026-09-18 — README rewrite

README rewritten for the current state: a **Supervisor access** section at the top (accounts and
where they live — `data/supervisors.csv`, plaintext, Forgot-password writes back), the `answer`
route in the tool table and the Mermaid graph, a new **Conversation memory** section (summary
after 6 turns; the four places memory is read: `call_records` for "score them", `answer`, the order
focus, and the lookup→answer guard), `tests/` + `auth.py` + `supervisors.csv` in the structure
tree, the offline `unittest` suites in Testing, the LM Studio auto-unload gotcha, a memory
follow-up in Sample outputs, and refreshed design decisions / limitations. Paths now say "repo
root" rather than `Call-Desk-Agent/` (this repo is where the work happens).

Scope: `README.md`, `progress.md`.

## 2026-09-18 — Repo hygiene: no AI attribution, no planning files in git

Per the author's instruction, `Co-Authored-By: Claude` trailers were stripped from every commit,
and `CLAUDE.md` plus `docs/superpowers/` (implementation plans) were removed from the whole
history (`git filter-branch`, the two now-empty "Add implementation plan" commits dropped); both
`main` and `fix/conversation-memory` were force-pushed. The files stay on disk and are now
gitignored (`CLAUDE.md`, `docs/superpowers/`, `.superpowers/`, `.claude/`). README structure tree
no longer lists `CLAUDE.md`. Backup refs of the pre-rewrite history: `backup/main-before-rewrite`,
`backup/pr-before-rewrite` (local only).

Scope: `.gitignore`, `README.md`, `progress.md`, git history.

## 2026-09-18 — Merge the 2026-09-14 Call-Desk-Agent changes back

The submission copy (`llm_projects/Call-Desk-Agent`) had diverged from this repo on 2026-09-14
with changes that never came back here: `print` → `logging` (`log.info` / `log.warning`, root
config already in `src/config.py`) across `graph.py` and the four tools, **policy answers cite
their source files** (`policy_node` uses `search_policy_with_context` and appends `_Sources: …_`),
a pinned `requirements.txt`, `.env.example`, and a `!.env.example` / `output/` gitignore. Rather
than overwrite either side, those files were committed on their common base (`5bc1ec4`) as
`sync/call-desk-agent-0914` and merged into `fix/conversation-memory`; conflicts (imports, the
lookup→answer guard's log line, `lookup_orders`' focus block) resolved keeping both sides. Test
stubs gained `search_policy_with_context`. README: root named `Call-Desk-Agent/`, `.env.example`,
`LOG_LEVEL`. 42/42 pass. From here the merged tree is synced into `llm_projects/Call-Desk-Agent`.

Scope: `src/agent/graph.py`, `src/tools/*.py`, `docs/blueprint.md`, `requirements.txt`,
`.env.example`, `.gitignore`, `tests/*.py`, `README.md`, `progress.md`.
