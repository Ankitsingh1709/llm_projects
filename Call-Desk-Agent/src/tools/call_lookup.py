"""Tool 2 — Call Record Lookup (structured filtering over data/calls.csv).

Turns a natural-language request into structured filters, applies them to the 50
synthetic call records with pandas, and returns a formatted string of matches.

Two-stage extraction, cheapest first — most lookups never touch the network:

  STAGE 1  regex/enum prefilter (no LLM). Resolves everything matchable
           deterministically: call_id, agent_name, call_type, direction,
           channel, a row limit + sort order ("last/top/first N"), and the
           unambiguous dates ("today", "yesterday", "last N days").
  STAGE 2  LangChain structured-output LLM fallback. Invoked ONLY when the query
           uses fuzzy date language regex can't safely resolve ("this week",
           "last month", "recent") OR the regex stage matched nothing at all.
           The chat model is bound with ``.with_structured_output(CallFilters)``,
           so a Pydantic schema + real Enums enforce a valid result — no JSON
           hand-parsing, no out-of-vocabulary values. The regex-resolved fields
           are passed in and always win on merge; the LLM only fills gaps. Any
           failure logs and falls back to the regex-only result.

The chat client (provider-agnostic, from config.json — same providers as Tool 1)
is built once via lru_cache. The DataFrame is loaded once, also via lru_cache.
Every path returns a string — the tool never raises.

Public API:
    lookup_calls(query) -> str
"""

from __future__ import annotations

import logging

import re
from datetime import date, timedelta
from enum import Enum
from functools import lru_cache
from typing import Optional

import pandas as pd
from pydantic import BaseModel, Field, field_validator

# Shared loader: imports .env (API keys) and config.json exactly once.
from src.config import CONFIG, REPO_ROOT

log = logging.getLogger(__name__)

CALLS_CSV = REPO_ROOT / "data" / "calls.csv"
MAX_LIMIT = 50  # never return more than the whole (50-row) dataset

# Fuzzy date phrases regex cannot resolve safely — the trigger for Stage 2.
_FUZZY_DATE_RE = re.compile(
    r"\b(this week|last week|this month|last month|recent)\b", re.IGNORECASE
)


# --------------------------------------------------------------------------- #
# Closed vocabularies as Enums — used by the Pydantic schema so out-of-vocab
# values are structurally impossible, not merely discouraged in the prompt.
# --------------------------------------------------------------------------- #

class AgentName(str, Enum):
    rahul = "Rahul"
    priya = "Priya"
    amit = "Amit"
    sara = "Sara"
    james = "James"


class CallType(str, Enum):
    replacement = "replacement"
    repair = "repair"
    logistics = "logistics"
    device = "device"
    escalation = "escalation"


class Direction(str, Enum):
    inbound = "inbound"
    outbound = "outbound"


class Channel(str, Enum):
    phone = "phone"
    chat = "chat"
    email = "email"


class SortOrder(str, Enum):
    asc = "asc"
    desc = "desc"


class CallFilters(BaseModel):
    """Structured query shared by both stages; every field but sort_order is
    optional (None = don't filter on it)."""

    call_id: Optional[str] = None
    agent_name: Optional[AgentName] = None
    call_type: Optional[CallType] = None
    direction: Optional[Direction] = None
    channel: Optional[Channel] = None
    date_from: Optional[str] = Field(default=None, description="inclusive, YYYY-MM-DD")
    date_to: Optional[str] = Field(default=None, description="inclusive, YYYY-MM-DD")
    limit: Optional[int] = Field(default=None, description=f"max rows, capped at {MAX_LIMIT}")
    sort_order: SortOrder = SortOrder.desc

    @field_validator("limit", mode="before")
    @classmethod
    def _clamp_limit(cls, v: Optional[int]) -> Optional[int]:
        # Clamp (not reject) so an over-eager LLM value degrades gracefully.
        if v is None:
            return None
        return max(1, min(int(v), MAX_LIMIT))

    @field_validator("date_from", "date_to", mode="before")
    @classmethod
    def _normalize_date(cls, v: Optional[str]) -> Optional[str]:
        # LLMs often return a full datetime ("2026-08-15T00:00:00Z"); keep only
        # the YYYY-MM-DD part so string comparison against the CSV dates is exact.
        if v is None:
            return None
        m = re.match(r"(\d{4}-\d{2}-\d{2})", str(v))
        return m.group(1) if m else None

    def describe(self) -> str:
        parts = [
            f"{k}={v.value if isinstance(v, Enum) else v}"
            for k, v in self.model_dump().items()
            if v is not None and k != "sort_order"
        ]
        parts.append(f"sort_order={self.sort_order.value}")
        return ", ".join(parts)


# --------------------------------------------------------------------------- #
# Stage 1 — regex / enum prefilter (no LLM)
# --------------------------------------------------------------------------- #

def _match_enum(query: str, enum_cls: type[Enum]) -> Optional[str]:
    q = query.lower()
    for member in enum_cls:
        if re.search(rf"\b{re.escape(member.value.lower())}\b", q):
            return member.value
    return None


def _extract_call_id(query: str) -> Optional[str]:
    # "call 1042", "#1042", "CALL-1042" -> "CALL-1042"
    m = re.search(r"\b(?:call[\s#-]*)?#?(\d{4})\b", query, re.IGNORECASE)
    return f"CALL-{int(m.group(1)):04d}" if m else None


def _extract_limit_and_order(query: str) -> tuple[Optional[int], Optional[str]]:
    # "first N" -> earliest N (asc); "last/top N" -> most recent N (desc).
    # A number followed by "day(s)" is a date range, not a row limit.
    m = re.search(r"\b(last|top|first)\s+(\d+)\b(?!\s+days?\b)", query, re.IGNORECASE)
    if not m:
        return None, None
    order = "asc" if m.group(1).lower() == "first" else "desc"
    return int(m.group(2)), order


def _extract_simple_dates(query: str) -> tuple[Optional[str], Optional[str]]:
    # Only the unambiguous relative dates; anything fuzzy is left to the LLM.
    q = query.lower()
    today = date.today()
    if re.search(r"\btoday\b", q):
        iso = today.isoformat()
        return iso, iso
    if re.search(r"\byesterday\b", q):
        iso = (today - timedelta(days=1)).isoformat()
        return iso, iso
    m = re.search(r"\blast\s+(\d+)\s+days?\b", q)
    if m:
        return (today - timedelta(days=int(m.group(1)))).isoformat(), today.isoformat()
    return None, None


def _regex_filters(query: str) -> dict:
    """Stage 1: return only the fields regex resolved (absent keys = unmatched)."""
    limit, order = _extract_limit_and_order(query)
    date_from, date_to = _extract_simple_dates(query)
    candidates = {
        "call_id": _extract_call_id(query),
        "agent_name": _match_enum(query, AgentName),
        "call_type": _match_enum(query, CallType),
        "direction": _match_enum(query, Direction),
        "channel": _match_enum(query, Channel),
        "date_from": date_from,
        "date_to": date_to,
        "limit": limit,
        "sort_order": order,
    }
    return {k: v for k, v in candidates.items() if v is not None}


def _needs_llm(query: str, regex_fields: dict) -> bool:
    # Escalate on fuzzy date language, or when regex resolved nothing at all.
    return bool(_FUZZY_DATE_RE.search(query)) or not regex_fields


# --------------------------------------------------------------------------- #
# Stage 2 — LangChain structured-output LLM fallback (client cached once)
# --------------------------------------------------------------------------- #

def _build_chat_model(config: dict, model: Optional[str] = None):
    # Provider-agnostic chat model from config.json; mirrors Tool 1's provider
    # switch. Only the active provider's LangChain package is imported. `model`
    # overrides the provider's default model when given (Stage 2 uses this to run
    # extraction on a lighter structured-output-friendly model).
    provider = config["active_provider"]
    pconf = config["providers"][provider]
    common = {"model": model or pconf["model"], "temperature": pconf["temperature"]}

    if provider == "gemini":
        from langchain_google_genai import ChatGoogleGenerativeAI

        return ChatGoogleGenerativeAI(
            max_output_tokens=pconf["max_output_tokens"], **common
        )
    if provider in ("openai", "local_lmstudio"):
        from langchain_openai import ChatOpenAI

        if provider == "openai":
            return ChatOpenAI(max_tokens=pconf["max_tokens"], **common)
        base_url = pconf["base_url"].rstrip("/")
        if not base_url.endswith("/v1"):
            base_url += "/v1"
        return ChatOpenAI(
            max_tokens=pconf["max_tokens"],
            base_url=base_url,
            api_key="not-needed",
            **common,
        )
    if provider == "anthropic":
        from langchain_anthropic import ChatAnthropic

        return ChatAnthropic(max_tokens=pconf["max_tokens"], **common)

    raise ValueError(f"Unknown active_provider '{provider}' in config.json")


@lru_cache(maxsize=1)
def _structured_llm():
    # Built once, on first Stage-2 use, and cached. Lazy so a deterministic
    # lookup never constructs the client (and never fails when the LLM is down).
    # The active provider may pin how the schema is enforced via
    # `structured_output_method` ("json_schema" / "json_mode" / "function_calling";
    # omit for LangChain's default) and run extraction on a lighter model via
    # `structured_output_model` (omit to reuse the provider's main model). The
    # default local model is a reasoning model that can't emit structured output,
    # so we point Stage 2 at a small instruct model instead.
    pconf = CONFIG["providers"][CONFIG["active_provider"]]
    method = pconf.get("structured_output_method")
    kwargs = {"method": method} if method else {}
    model = _build_chat_model(CONFIG, model=pconf.get("structured_output_model"))
    return model.with_structured_output(CallFilters, **kwargs)


_EXTRACTION_PROMPT = (
    "You extract structured search filters from a call-center record-lookup "
    "request. Fill only the fields you are confident about; leave the rest null. "
    "Resolve any relative or fuzzy dates against the current date. Never guess "
    "values for the closed-vocabulary fields.\n\n"
    "Current date: {today}\n"
    "Already resolved by prior parsing (do NOT change these): {resolved}\n\n"
    "Request: {query}"
)


def _llm_filters(query: str, regex_fields: dict) -> Optional[CallFilters]:
    # Returns a CallFilters from the structured-output model, or None on any
    # failure (logged) so the tool degrades to the regex-only result.
    try:
        prompt = _EXTRACTION_PROMPT.format(
            today=date.today().isoformat(),
            resolved=regex_fields or "nothing",
            query=query,
        )
        result = _structured_llm().invoke(prompt)
        return result if isinstance(result, CallFilters) else None
    except Exception as exc:  # noqa: BLE001 - never let the LLM crash the tool
        log.warning(f"[call_lookup] LLM extraction failed, using regex result: {exc}")
        return None


def _resolve_filters(query: str) -> CallFilters:
    # Run Stage 1, escalate to Stage 2 when needed, and merge with regex winning.
    regex_fields = _regex_filters(query)
    log.info(f"[call_lookup] stage 1 -> {regex_fields or '(no match)'}")

    if not _needs_llm(query, regex_fields):
        log.info("[call_lookup] stage 2 skipped (deterministic answer)")
        return CallFilters(**regex_fields)

    log.info("[call_lookup] stage 2 -> querying structured-output LLM")
    llm_result = _llm_filters(query, regex_fields)
    if llm_result is None:
        return CallFilters(**regex_fields)

    # Merge: LLM fills gaps, regex-confirmed fields always take precedence.
    merged = llm_result.model_dump(mode="json")
    merged.update(regex_fields)
    return CallFilters(**merged)


# NOTE: resolve_filters_with_status deliberately DUPLICATES _resolve_filters's
# orchestration (Stage-1 regex prefilter, the _needs_llm decision, and the
# regex-wins merge). The two MUST be kept in sync BY HAND. No shared helper was
# extracted because _resolve_filters's own signature was deliberately kept stable
# so existing callers stay unaffected (agent/graph.py relies on it).
# The parity cell in notebooks/test_call_lookup.ipynb guards
# against the two implementations silently drifting apart.
def resolve_filters_with_status(query: str) -> tuple[CallFilters, bool]:
    """Same resolution as _resolve_filters, but also reports whether Stage-2 LLM
    extraction was attempted and failed (degraded to regex-only).

    Returns ``(filters, llm_degraded)``. ``llm_degraded`` is True only when
    Stage 2 was NEEDED but did not yield a usable result — either _llm_filters
    raised, or it returned None (its own catch-and-log, or a needed-but-
    unavailable provider) — so the answer fell back to the regex-only filters.
    It is False when Stage 1 alone was sufficient (``_needs_llm`` was False) or
    when Stage 2 succeeded.
    """
    regex_fields = _regex_filters(query)
    log.info(f"[call_lookup] stage 1 -> {regex_fields or '(no match)'}")

    if not _needs_llm(query, regex_fields):
        log.info("[call_lookup] stage 2 skipped (deterministic answer)")
        return CallFilters(**regex_fields), False

    log.info("[call_lookup] stage 2 -> querying structured-output LLM")
    # Wrap here in ADDITION to _llm_filters's own internal catch: a raise OR a
    # None result both mean Stage 2 was needed but unavailable -> degraded.
    try:
        llm_result = _llm_filters(query, regex_fields)
    except Exception as exc:  # noqa: BLE001 - degrade, never crash the caller
        log.warning(f"[call_lookup] stage 2 raised, degraded to regex-only: {exc}")
        llm_result = None

    if llm_result is None:
        return CallFilters(**regex_fields), True

    # Merge: LLM fills gaps, regex-confirmed fields always take precedence.
    merged = llm_result.model_dump(mode="json")
    merged.update(regex_fields)
    return CallFilters(**merged), False


# --------------------------------------------------------------------------- #
# Data + filtering (pandas)
# --------------------------------------------------------------------------- #

@lru_cache(maxsize=1)
def _load_df() -> pd.DataFrame:
    # Loaded once and cached; date kept as ISO string (lexical == chronological).
    df = pd.read_csv(CALLS_CSV, dtype={"date": str})
    df["duration_mins"] = pd.to_numeric(df["duration_mins"], errors="coerce").fillna(0).astype(int)
    return df


def _apply_filters(df: pd.DataFrame, f: CallFilters) -> pd.DataFrame:
    mask = pd.Series(True, index=df.index)
    if f.call_id:
        mask &= df["call_id"] == f.call_id
    if f.agent_name:
        mask &= df["agent_name"] == f.agent_name.value
    if f.call_type:
        mask &= df["call_type"] == f.call_type.value
    if f.direction:
        mask &= df["direction"] == f.direction.value
    if f.channel:
        mask &= df["channel"] == f.channel.value
    if f.date_from:
        mask &= df["date"] >= f.date_from
    if f.date_to:
        mask &= df["date"] <= f.date_to

    out = df[mask].sort_values(
        ["date", "call_id"], ascending=f.sort_order == SortOrder.asc
    )
    if f.limit is not None:
        out = out.head(f.limit)
    return out


def _format_results(rows: pd.DataFrame) -> str:
    if rows.empty:
        return "No matching call records found."
    lines = [
        f"[{r.call_id}] {r.date} — {r.agent_name} — {r.call_type} "
        f"({r.direction}, {r.channel}, {r.duration_mins} min)"
        for r in rows.itertuples(index=False)
    ]
    return "\n".join(lines)


# --------------------------------------------------------------------------- #
# Public API
# --------------------------------------------------------------------------- #

def lookup_calls(query: str) -> str:
    """Parse a natural-language request into structured filters, apply them to
    the call records, and return matching rows formatted one per line.

    Stage 1 (regex/enum) answers most queries with no network call; the
    structured-output LLM (Stage 2) is consulted only for fuzzy dates or when
    regex matched nothing. Always returns a string — on any failure it logs and
    returns either the regex-only result or a plain-English error message.
    """
    filters = _resolve_filters(query)
    log.info(f"[call_lookup] filters -> {filters.describe()}")
    try:
        rows = _apply_filters(_load_df(), filters)
    except Exception as exc:  # noqa: BLE001 - surface as a message, never a trace
        log.warning(f"[call_lookup] filtering failed: {exc}")
        return f"Sorry, the call lookup could not be completed: {exc}"
    log.info(f"[call_lookup] query={query!r} matched {len(rows)} record(s)")
    return _format_results(rows)


if __name__ == "__main__":  # manual smoke test — run from the repo root
    for q in (
        "show me call 1042",
        "last 3 escalation calls by Priya",
        "inbound chat calls",
        "calls from this month",
    ):
        print("\n" + "=" * 70 + f"\nQUERY: {q}\n" + "=" * 70)
        print(lookup_calls(q))
