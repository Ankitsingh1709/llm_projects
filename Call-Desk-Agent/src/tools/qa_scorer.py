"""Tool 3 — QA Scorer (rubric-based call scoring, LangChain structured output).

Scores a call-center transcript against a fixed 9-parameter binary rubric and
returns a formatted report string. Eight parameters are judged by the LLM; the
9th, ``sla_met``, is deterministic — read from the call record, never judged.
Every parameter is PASS/FAIL. The overall score is a WEIGHTED total out of 100
(per-category weights from ``data/qa_weights.csv``) and the PASS/FAIL verdict are
computed in Python, never self-reported by the LLM.

Design mirrors Tool 1 / Tool 2:

  * Provider-agnostic chat model from config.json (same provider switch), bound
    with ``.with_structured_output(QAResult)`` so a Pydantic schema enforces a
    valid result — no JSON hand-parsing, no markdown-fenced JSON.
  * The structured-output client is built ONCE at module load (like Tool 1's LLM
    client). The weights table and the call-record index are loaded once via
    ``lru_cache`` (like Tool 2's DataFrame).
  * Every path returns a string — the tool never raises.

Two parameters are NOT trusted to the LLM's own knowledge:
  * policy_compliance — judged ONLY against policy text retrieved via Tool 1's
    ``search_policy_with_context`` (never from the LLM's training knowledge). If
    retrieval fails or returns nothing relevant, that fact is stated in the
    prompt AND policy_compliance is forced to FAIL with a "no policy context
    available" note.
  * sla_met — read from the call record (``sla_met == "Yes"`` -> PASS), keyed by
    ``call_id``. If the record isn't available (no/unknown call_id) it FAILs with
    a "no SLA data available" note. The LLM never sees or judges this field.

Weighting (data/qa_weights.csv): each parameter carries a weight that depends on
the call's category. Category is: "email" for email-channel rows regardless of
direction (email rows carry no meaningful inbound/outbound distinction), else the
row's ``direction`` ("inbound"/"outbound"). When the call record is unknown the
weights default to the "inbound" column. Each category's weights sum to 100, so
the weighted score reads directly as a percentage; PASS requires >= 60%. A FAIL on
a gating parameter (``professional_tone``) caps the overall verdict at FAIL
regardless of the score — a high score can't excuse rude handling.

Public API:
    score_call(transcript, call_id="", policy_context="") -> str
"""

from __future__ import annotations

import logging

from functools import lru_cache

import pandas as pd
from pydantic import BaseModel, Field

# Shared loader: imports .env (API keys) and config.json exactly once.
from src.config import CONFIG, REPO_ROOT
from src.tools.policy_search import search_policy_with_context

log = logging.getLogger(__name__)

# --------------------------------------------------------------------------- #
# Rubric. The 8 LLM-judged parameters (in report order), plus the deterministic
# sla_met appended as the 9th. PARAM_NAMES is the single source of truth for the
# full set, its order, and the keys used against the weights table.
# --------------------------------------------------------------------------- #

LLM_RUBRIC: list[tuple[str, str]] = [
    ("greeting", "Greeted the customer within the first 3 turns."),
    ("identity_verification", "Asked for a name / account / order ID to verify identity."),
    ("problem_acknowledgement", "Explicitly acknowledged the customer's issue."),
    ("call_classification", "Correctly identified the call type (replacement / repair / "
                            "logistics / device / escalation)."),
    ("solution_offered", "Offered a resolution or a concrete next step."),
    ("policy_compliance", "Response matches the retrieved policy context ONLY — judged "
                          "solely from the provided policy text, never general knowledge."),
    ("professional_tone", "No rude, dismissive, or unprofessional language."),
    ("proper_closure", "Summarized and closed the call politely."),
]

SLA_PARAM = "sla_met"  # deterministic 9th parameter, read from the call record.

# Full rubric order (must match the parameters present in data/qa_weights.csv).
PARAM_NAMES: list[str] = [name for name, _ in LLM_RUBRIC] + [SLA_PARAM]

PASS_FRACTION = 0.60  # weighted-score fraction required to PASS (>= 60 of 100).
# Gating parameters: a FAIL on any of these caps the overall verdict at FAIL,
# regardless of the weighted score — a high score can't excuse rude handling.
GATING_PARAMS: tuple[str, ...] = ("professional_tone",)
NO_POLICY_NOTE = "no policy context available"
NO_SLA_NOTE = "no SLA data available"

WEIGHTS_CSV = REPO_ROOT / "data" / "qa_weights.csv"
CALLS_CSV = REPO_ROOT / "data" / "calls.csv"
_CATEGORY_COLUMNS = {
    "inbound": "weight_inbound",
    "outbound": "weight_outbound",
    "email": "weight_email",
}
_DEFAULT_CATEGORY = "inbound"  # weighting fallback when the call record is unknown.


# --------------------------------------------------------------------------- #
# Structured output schema (LLM-judged parameters only — sla_met is excluded).
# --------------------------------------------------------------------------- #

class ParamResult(BaseModel):
    """One rubric parameter's verdict: passed True/False plus a short reason."""

    passed: bool
    justification: str = Field(default="", description="one short sentence of evidence")


class QAResult(BaseModel):
    """The LLM's per-parameter verdicts. sla_met is NOT here (it is read from the
    call record) and the overall score is NOT here (it is computed in Python)."""

    greeting: ParamResult
    identity_verification: ParamResult
    problem_acknowledgement: ParamResult
    call_classification: ParamResult
    solution_offered: ParamResult
    policy_compliance: ParamResult
    professional_tone: ParamResult
    proper_closure: ParamResult


# --------------------------------------------------------------------------- #
# Weights + call-record index (loaded once, cached — mirrors Tool 2's _load_df)
# --------------------------------------------------------------------------- #

@lru_cache(maxsize=1)
def _weights() -> dict[str, dict[str, int]]:
    # {category: {parameter: weight}} from data/qa_weights.csv. On any load
    # failure, fall back to uniform weights so scoring degrades instead of
    # crashing. Missing parameters default to weight 0.
    try:
        df = pd.read_csv(WEIGHTS_CSV)
        table: dict[str, dict[str, int]] = {cat: {} for cat in _CATEGORY_COLUMNS}
        for row in df.itertuples(index=False):
            for cat, col in _CATEGORY_COLUMNS.items():
                table[cat][row.parameter] = int(getattr(row, col))
        for cat in _CATEGORY_COLUMNS:
            for name in PARAM_NAMES:
                table[cat].setdefault(name, 0)
        return table
    except Exception as exc:  # noqa: BLE001 - never let a bad weights file crash scoring
        log.warning(f"[qa_scorer] could not load weights ({exc}); using uniform weights")
        uniform = round(100 / len(PARAM_NAMES))
        return {cat: {name: uniform for name in PARAM_NAMES} for cat in _CATEGORY_COLUMNS}


@lru_cache(maxsize=1)
def _call_index() -> dict[str, dict[str, str]]:
    # {call_id: {direction, channel, sla_met}} for deterministic sla_met + the
    # weighting category. Only the needed columns are read (skips the transcripts).
    try:
        df = pd.read_csv(
            CALLS_CSV, dtype=str, usecols=["call_id", "direction", "channel", "sla_met"]
        )
    except Exception as exc:  # noqa: BLE001 - sla_met simply becomes unavailable
        log.warning(f"[qa_scorer] could not load call index ({exc}); sla_met unavailable")
        return {}
    return {
        r.call_id: {"direction": r.direction, "channel": r.channel, "sla_met": r.sla_met}
        for r in df.itertuples(index=False)
    }


def _category(direction: str | None, channel: str | None) -> str:
    # Email is its own category regardless of direction (email rows carry no
    # meaningful inbound/outbound distinction); otherwise the row's direction.
    if (channel or "").strip().lower() == "email":
        return "email"
    direction = (direction or "").strip().lower()
    return direction if direction in ("inbound", "outbound") else _DEFAULT_CATEGORY


def _sla_result_and_category(call_id: str) -> tuple[ParamResult, str]:
    # sla_met is a data fact, not an LLM judgment: PASS iff the record says "Yes".
    # Also returns the weighting category derived from the same record.
    row = _call_index().get(call_id) if call_id else None
    if row is None:
        if call_id:
            log.warning(f"[qa_scorer] call_id {call_id!r} not in call records; sla_met unavailable")
        note = f"{NO_SLA_NOTE} (call record not found)" if call_id else f"{NO_SLA_NOTE} (no call_id)"
        return ParamResult(passed=False, justification=note), _DEFAULT_CATEGORY

    category = _category(row.get("direction"), row.get("channel"))
    value = (row.get("sla_met") or "").strip().lower()
    if value == "yes":
        return ParamResult(passed=True, justification="SLA met per call record"), category
    if value == "no":
        return ParamResult(passed=False, justification="SLA not met per call record"), category
    return ParamResult(passed=False, justification=f"{NO_SLA_NOTE} (missing value)"), category


# --------------------------------------------------------------------------- #
# LLM client (provider-agnostic, built once at module load)
# --------------------------------------------------------------------------- #

def _build_chat_model(config: dict, model: str | None = None):
    """Provider-agnostic chat model from config.json; mirrors Tool 1 / Tool 2's
    provider switch. Only the active provider's LangChain package is imported.
    ``model`` overrides the provider's default (used to run scoring on a
    structured-output-friendly model where the main model can't emit one)."""
    provider = config["active_provider"]
    pconf = config["providers"][provider]
    common = {"model": model or pconf["model"], "temperature": pconf["temperature"]}

    if provider == "gemini":
        from langchain_google_genai import ChatGoogleGenerativeAI

        return ChatGoogleGenerativeAI(max_output_tokens=pconf["max_output_tokens"], **common)
    if provider in ("openai", "local_lmstudio"):
        from langchain_openai import ChatOpenAI

        if provider == "openai":
            return ChatOpenAI(max_tokens=pconf["max_tokens"], **common)
        base_url = pconf["base_url"].rstrip("/")
        if not base_url.endswith("/v1"):
            base_url += "/v1"
        return ChatOpenAI(
            max_tokens=pconf["max_tokens"], base_url=base_url, api_key="not-needed", **common
        )
    if provider == "anthropic":
        from langchain_anthropic import ChatAnthropic

        return ChatAnthropic(max_tokens=pconf["max_tokens"], **common)

    raise ValueError(f"Unknown active_provider '{provider}' in config.json")


def _build_scorer():
    # Bind the schema the same way Tool 2 does: honor the active provider's
    # structured_output_method / structured_output_model (the local reasoning
    # model can't emit structured output, so it pins a small instruct model).
    pconf = CONFIG["providers"][CONFIG["active_provider"]]
    method = pconf.get("structured_output_method")
    kwargs = {"method": method} if method else {}
    model = _build_chat_model(CONFIG, model=pconf.get("structured_output_model"))
    return model.with_structured_output(QAResult, **kwargs)


# Built once at module load (mirrors Tool 1) — a bad/missing provider fails here.
_SCORER = _build_scorer()


# --------------------------------------------------------------------------- #
# Prompt (the LLM judges the 8 LLM_RUBRIC parameters only)
# --------------------------------------------------------------------------- #

_RUBRIC_BLOCK = "\n".join(f"  {i}. {name} — {desc}" for i, (name, desc) in enumerate(LLM_RUBRIC, 1))

_SCORING_INSTRUCTION = (
    "You are a strict call-center QA reviewer. Evaluate the transcript below "
    "against each of these 8 binary parameters and decide PASS or FAIL for each, "
    "with one short sentence of justification citing evidence from the transcript:\n\n"
    f"{_RUBRIC_BLOCK}\n\n"
    "Rules:\n"
    "- Judge every parameter ONLY from the transcript, except policy_compliance.\n"
    "- For policy_compliance, judge ONLY against the POLICY CONTEXT provided below. "
    "Never use your own general knowledge of what a policy might say. If the policy "
    f"context says no policy is available, policy_compliance MUST FAIL with the note "
    f"\"{NO_POLICY_NOTE}\".\n"
    "- Do not compute an overall score; only return the per-parameter verdicts."
)


def _retrieve_policy_context(transcript: str) -> tuple[str, bool]:
    # Self-serve Tool 1 when the caller gave no policy_context. Route on the
    # transcript (call_type is not known inside this tool; the graph passes
    # policy_context directly when it knows the exact call_type). Returns the
    # retrieved policy text and whether anything relevant came back.
    try:
        # generate_answer=False: we only need the retrieved chunks for
        # policy_compliance, not a written answer — skips a wasted (slow on a
        # local reasoning model) LLM generation call.
        result = search_policy_with_context(transcript, generate_answer=False)
    except Exception as exc:  # noqa: BLE001 - retrieval must never crash scoring
        log.warning(f"[qa_scorer] policy retrieval failed, scoring without context: {exc}")
        return "", False

    chunks = result.get("chunks_used") or []
    if not chunks:
        log.info("[qa_scorer] policy retrieval returned no relevant chunks")
        return "", False
    return "\n\n".join(chunks), True


def _build_prompt(transcript: str, policy_context: str, policy_available: bool) -> str:
    context = policy_context.strip() if policy_available else (
        f"NO POLICY CONTEXT AVAILABLE ({NO_POLICY_NOTE})."
    )
    return (
        f"{_SCORING_INSTRUCTION}\n\n"
        f"POLICY CONTEXT (the ONLY basis for policy_compliance):\n{context}\n\n"
        f"TRANSCRIPT:\n{transcript}\n\n"
        "Return the per-parameter verdicts."
    )


# --------------------------------------------------------------------------- #
# Report formatting (weighted score computed here, in Python)
# --------------------------------------------------------------------------- #

def _md_cell(text: str) -> str:
    """Make a justification safe for a single Markdown table cell: collapse any
    newlines to spaces and escape pipes so they don't split the row."""
    return " ".join(text.split()).replace("|", "\\|").strip()


def _format_report(results: dict[str, ParamResult], call_id: str, category: str) -> str:
    """Render the scorecard as a Markdown table (Parameter / Result / Weight /
    Why) with a heading and a bold weighted-score footer. Markdown so the
    Streamlit chat (st.markdown) shows a real table instead of a wall of text;
    it also renders fine as plain text in notebooks/CLI."""
    weights = _weights()[category]
    title = f"QA Scorecard — {call_id}" if call_id else "QA Scorecard"

    earned = 0
    total = sum(weights[name] for name in PARAM_NAMES)

    rows: list[str] = []
    for name in PARAM_NAMES:
        pr = results[name]
        weight = weights[name]
        if pr.passed:
            earned += weight
        result = "✅ PASS" if pr.passed else "❌ FAIL"
        why = _md_cell(pr.justification) or "—"
        rows.append(f"| {name} | {result} | {weight} | {why} |")

    pct = round(100 * earned / total) if total else 0
    # A failed gating parameter forces FAIL even when the score clears the bar.
    gating_failed = [p for p in GATING_PARAMS if not results[p].passed]
    verdict = "PASS" if (earned >= PASS_FRACTION * total and not gating_failed) else "FAIL"

    footer = f"**Weighted score: {earned}/{total} ({pct}%) — {verdict}**"
    if gating_failed:
        footer += f"  \n⚠️ _{'/'.join(gating_failed)} FAIL → automatic FAIL_"

    lines = [
        f"#### {title}",
        f"*Category: {category} — weights sum to {total}*",
        "",
        "| Parameter | Result | Weight | Why |",
        "|:--|:--:|:--:|:--|",
        *rows,
        "",
        footer,
    ]
    return "\n".join(lines)


# --------------------------------------------------------------------------- #
# Public API
# --------------------------------------------------------------------------- #

def score_call(transcript: str, call_id: str = "", policy_context: str = "") -> str:
    """Score a call transcript against the 9-parameter QA rubric and return a
    readable, weighted report string.

    Eight parameters are judged by the LLM; ``sla_met`` (the 9th) is read from the
    call record for ``call_id`` (PASS iff ``sla_met == "Yes"``), not judged. If
    ``policy_context`` is empty this calls Tool 1 (``search_policy_with_context``)
    to retrieve the relevant policy text; parameter 6 (policy_compliance) is judged
    ONLY from that text and is forced to FAIL when it is unavailable. The overall
    score is a weighted total out of 100 (per-category weights from
    ``data/qa_weights.csv``), computed in Python; PASS requires >= 60% AND a PASS on
    every gating parameter (``professional_tone`` — a FAIL there forces overall
    FAIL regardless of score). Always returns a string, even on failure.
    """
    if not transcript or not transcript.strip():
        return "Cannot score: no transcript was provided."

    supplied = bool(policy_context and policy_context.strip())
    if supplied:
        policy_available = True
    else:
        policy_context, policy_available = _retrieve_policy_context(transcript)

    prompt = _build_prompt(transcript, policy_context, policy_available)
    try:
        llm_result = _SCORER.invoke(prompt)
    except Exception as exc:  # noqa: BLE001 - return a message, never a stack trace
        log.warning(f"[qa_scorer] scoring LLM failed: {exc}")
        return f"Sorry, QA scoring could not be completed: {exc}"

    if not isinstance(llm_result, QAResult):
        log.warning(f"[qa_scorer] unexpected structured-output type: {type(llm_result)!r}")
        return "Sorry, QA scoring could not be completed: the model returned no valid result."

    results: dict[str, ParamResult] = {
        name: getattr(llm_result, name) for name, _ in LLM_RUBRIC
    }

    # policy_compliance can NEVER pass without policy context — enforce in code so
    # a hallucinated PASS can't slip through regardless of what the LLM returned.
    if not policy_available:
        results["policy_compliance"] = ParamResult(passed=False, justification=NO_POLICY_NOTE)

    # sla_met is deterministic (from the call record), and gives the weight category.
    sla_result, category = _sla_result_and_category(call_id)
    results[SLA_PARAM] = sla_result

    log.info(
        f"[qa_scorer] scored call_id={call_id or '(none)'} category={category} "
        f"policy_context={'yes' if policy_available else 'no'} "
        f"sla_met={'yes' if sla_result.passed else 'no'}"
    )
    return _format_report(results, call_id, category)


if __name__ == "__main__":  # manual smoke test — run from the repo root
    demo = (
        "Agent: Hi, thanks for calling support, my name is Priya. How can I help?\n"
        "Customer: My replacement phone screen is cracked and I want it swapped.\n"
        "Agent: I'm sorry to hear that. Can I have your order ID to pull up the case?\n"
        "Customer: It's ORD-8842.\n"
        "Agent: Thank you. Since it's within the replacement window, I'll arrange a swap "
        "and email you a prepaid label. Anything else?\n"
        "Customer: No, that's all.\n"
        "Agent: Great, I've logged the replacement. Have a good day!"
    )
    print(score_call(demo, call_id="CALL-1001"))
