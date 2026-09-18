"""Step 7 — LangGraph supervisor graph wiring the three tools together.

A single supervisor LLM decides which tool(s) a user request needs, and a small
StateGraph routes the request through them (Step 7 wired three tools; the
customer-facing ``order`` tool was added later as a fourth), threading everything via the
``AgentState`` TypedDict (see ``state.py``).

Design notes / consistency with the tools:

  * The supervisor chat client mirrors ``qa_scorer._build_chat_model`` exactly
    (same provider switch, same ``**common`` kwargs) but uses a plain
    ``.invoke(prompt)`` — no structured output. It is built ONCE at import,
    guarded by Tool 1's ``_require_env_key`` / ``_check_reachable`` (copied here),
    so a bad/unreachable provider fails fast at import — consistent with Tool 1
    and Tool 3.
  * Every DATA-FETCHING node appends exactly one entry to ``tool_trace`` as it
    runs (the supervisor is not a data tool, so it appends nothing). Because
    ``tool_trace`` / ``call_records`` / ``qa_scores`` carry no reducer, a node
    that appends returns ``state.get(field, []) + [new]``; only ``messages`` has
    the ``add_messages`` reducer.

Routing:
  * ``route_decision`` reads ``next_tool`` (the supervisor's first choice).
  * ``route_after_lookup`` chains scoring after a lookup when
    ``pending_tools[0] == "score"``.

Public API:
    build_graph() -> compiled LangGraph app
"""

from __future__ import annotations

import logging

import os
import re
import urllib.request
from typing import Optional

from langchain_core.messages import AIMessage
from langchain_core.runnables import RunnableConfig
from langgraph.graph import END, StateGraph

# Shared loader: imports .env (API keys) and config.json exactly once.
from src.config import CONFIG
from src.agent.state import AgentState
from src.tools.call_lookup import _FUZZY_DATE_RE, _regex_filters, lookup_calls
from src.tools.policy_search import search_policy_with_context
from src.tools.order_lookup import focus_order_id, lookup_orders
from src.tools.qa_scorer import score_call

log = logging.getLogger(__name__)


# --------------------------------------------------------------------------- #
# Supervisor LLM client (built once at import — fails fast on a bad provider)
# --------------------------------------------------------------------------- #

# Copied verbatim from Tool 1 (policy_search.py) so the supervisor client fails
# fast on a missing key / unreachable local endpoint at import, exactly like
# Tool 1 and Tool 3. Kept local (rather than imported) per the Step 7 decision.
def _require_env_key(provider: str, api_key_env: str) -> str:
    """Return the API key from the env, or raise clearly at load time."""
    key = os.environ.get(api_key_env)
    if not key:
        raise RuntimeError(
            f"Active provider '{provider}' requires environment variable "
            f"'{api_key_env}', but it is not set. Add it to .env or export it "
            f"before importing agent.graph."
        )
    return key


def _check_reachable(provider: str, base_url: str) -> None:
    """Fail clearly at load time if a local OpenAI-compatible server is down."""
    probe = base_url.rstrip("/") + "/models"
    try:
        with urllib.request.urlopen(probe, timeout=3) as resp:  # noqa: S310
            if resp.status >= 500:
                raise RuntimeError(f"HTTP {resp.status}")
    except Exception as exc:  # noqa: BLE001 - surface any failure as one clear error
        raise RuntimeError(
            f"Active provider '{provider}' endpoint {base_url} is not reachable "
            f"({exc}). Start the local server (e.g. LM Studio) and load a model "
            f"first."
        ) from exc


def _build_chat_model(config: dict, model: str | None = None):
    """Provider-agnostic chat model from config.json — mirrors
    ``qa_scorer._build_chat_model`` exactly (same provider switch, same
    ``**common`` kwargs), with Tool 1's fail-fast guards added so a bad/missing
    key or unreachable local endpoint raises here, at import."""
    provider = config["active_provider"]
    pconf = config["providers"][provider]
    common = {"model": model or pconf["model"], "temperature": pconf["temperature"]}

    if provider == "gemini":
        _require_env_key(provider, pconf["api_key_env"])
        from langchain_google_genai import ChatGoogleGenerativeAI

        return ChatGoogleGenerativeAI(max_output_tokens=pconf["max_output_tokens"], **common)
    if provider in ("openai", "local_lmstudio"):
        from langchain_openai import ChatOpenAI

        if provider == "openai":
            _require_env_key(provider, pconf["api_key_env"])
            return ChatOpenAI(max_tokens=pconf["max_tokens"], **common)
        base_url = pconf["base_url"].rstrip("/")
        if not base_url.endswith("/v1"):
            base_url += "/v1"
        _check_reachable(provider, base_url)
        return ChatOpenAI(
            max_tokens=pconf["max_tokens"], base_url=base_url, api_key="not-needed", **common
        )
    if provider == "anthropic":
        _require_env_key(provider, pconf["api_key_env"])
        from langchain_anthropic import ChatAnthropic

        return ChatAnthropic(max_tokens=pconf["max_tokens"], **common)

    raise ValueError(f"Unknown active_provider '{provider}' in config.json")


# Built once at module load (mirrors Tool 1 / Tool 3) — a bad provider fails here.
_SUPERVISOR_LLM = _build_chat_model(CONFIG)


# --------------------------------------------------------------------------- #
# Supervisor prompt + defensive tool-word parsing
# --------------------------------------------------------------------------- #

_VALID_TOOLS: tuple[str, ...] = ("policy", "lookup", "order", "score", "answer")

# --------------------------------------------------------------------------- #
# Cooperative cancellation (used by the Streamlit "Stop" button)
# --------------------------------------------------------------------------- #
# The caller passes its OWN threading.Event per turn as
# ``config={"configurable": {"cancel": event}}`` to ``graph.invoke``; LangGraph
# hands that config to any node declaring a ``config`` parameter. Per-turn (not a
# module global) so one browser session's Stop cannot halt another's run — the
# compiled graph is a shared, cached singleton in the UI. Checked between LLM
# calls, so a Stop halts at the next call boundary rather than mid-token.
def is_cancelled(config: RunnableConfig | None) -> bool:
    event = ((config or {}).get("configurable") or {}).get("cancel")
    is_set = getattr(event, "is_set", None)
    return bool(is_set and is_set())


# Role-based access control. A customer may ask policy questions and order-status
# questions; call records and QA scores are supervisor-only. Enforced in
# supervisor_node (below) so it is real gating on the routing, not just a UI hint.
#
# ponytail: role gating only, NOT per-customer scoping — there is no identity in
# AgentState, so the `order` tool answers about any of the 40 orders regardless of
# who is asking. Fine for a single-tenant course demo; if this ever faces real
# customers, add a `customer_name` to AgentState and force it into OrderFilters
# in order_node (a filter the LLM cannot widen), rather than trusting the prompt.
CUSTOMER_ALLOWED_TOOLS: tuple[str, ...] = ("policy", "order", "answer")
CUSTOMER_REFUSAL = (
    "I can only help with company policy, product questions, and your order "
    "status. Call records and QA scores are available to supervisors only."
)

SUPERVISOR_PROMPT = (
    "You are the supervisor of a call-center QA assistant. Decide which tool(s) "
    "the user's request needs and reply with ONLY a comma-separated list of the "
    "tool words, in the order they should run. Output nothing else — no "
    "explanation, no sentences.\n\n"
    "Tools:\n"
    "  policy — answer a question about company policy (returns, repairs, "
    "logistics, device setup, escalations, SLAs).\n"
    "  lookup — find or list call records from the call database.\n"
    "  order  — look up an ORDER: its status, where the parcel is, tracking, "
    "delivery date/ETA, cancellation, return or refund.\n"
    "  score  — run the QA rubric scorer on a call transcript.\n"
    "  answer — reply from what was ALREADY shown earlier in this conversation "
    "(a call, scorecard, order or policy answer the user is referring back to), "
    "or plain conversation (greetings, thanks). Fetches nothing new.\n\n"
    "Rules:\n"
    "  - Policy questions -> policy.\n"
    "  - Finding/listing calls -> lookup.\n"
    "  - Questions about an order, a parcel, a delivery, tracking, or a refund "
    "-> order. (An ORDER is a purchase; a CALL is a support conversation — "
    "never use lookup for an order question.)\n"
    "  - Scoring a call REQUIRES its transcript. When the request NAMES which "
    "call(s) to score (a call id, an agent, \"last N\", etc.), the transcript must "
    "be fetched first, so reply exactly: lookup, score\n"
    "  - When the request asks to score calls that were ALREADY looked up earlier "
    "in this conversation (\"score them\", \"score those\", \"score these\"), the "
    "transcripts are already loaded, so reply exactly: score\n"
    "  - A question that refers back to something already discussed (\"the "
    "call\", \"it\", \"that score\", \"why did it fail\") without asking for "
    "new data -> answer.\n"
    "  - If none apply, reply with an empty line.\n\n"
    "Examples:\n"
    "  \"What is the replacement window?\" -> policy\n"
    "  \"Show me call 1042\" -> lookup\n"
    "  \"Where is my order 5031?\" -> order\n"
    "  \"When will ORD-5033 be delivered?\" -> order\n"
    "  \"Has my refund been processed yet?\" -> order\n"
    "  \"Look up call 1042 and score it\" -> lookup, score\n"
    "  \"Score Rahul's last 5 calls\" -> lookup, score\n"
    "  \"score them\" -> score\n"
    "  \"now score those calls\" -> score\n"
    "  \"what was the call about?\" -> answer\n"
    "  \"what was this call about? summarize it\" -> answer\n"
    "  \"why did it fail professional tone?\" -> answer\n"
    "  \"thanks!\" -> answer\n\n"
    "User request: {message}\n\n"
    "Tools:"
)


def _clean_content(content: str) -> str:
    # The local main model is a reasoning model that emits <think>...</think>
    # before its answer; keep only what follows the reasoning block so those
    # words can't be mistaken for tool choices.
    if "</think>" in content:
        content = content.rsplit("</think>", 1)[-1]
    content = re.sub(r"<think>.*?</think>", "", content, flags=re.DOTALL)
    return content.strip()


def _parse_tools(raw: str) -> list[str]:
    # Comma-separated tool words, parsed defensively: strip, lower, strip a
    # trailing ".", keep only known tools, and drop duplicates (order preserved).
    tools: list[str] = []
    for token in _clean_content(raw).split(","):
        word = token.strip().lower().rstrip(".").strip()
        if word in _VALID_TOOLS and word not in tools:
            tools.append(word)
    return tools


# --------------------------------------------------------------------------- #
# Message helpers
# --------------------------------------------------------------------------- #

def _msg_content(msg) -> str:
    if isinstance(msg, dict):
        return str(msg.get("content", ""))
    return str(getattr(msg, "content", "") or "")


def _msg_role(msg) -> str | None:
    if isinstance(msg, dict):
        return msg.get("role") or msg.get("type")
    return getattr(msg, "type", None)


def _last_user_message(state: AgentState) -> str:
    """The most recent human/user message text (falls back to the last message)."""
    messages = state.get("messages") or []
    for msg in reversed(messages):
        if _msg_role(msg) in ("human", "user"):
            return _msg_content(msg)
    return _msg_content(messages[-1]) if messages else ""


def turn_replies(messages: list) -> list[str]:
    """Contents of every message after the last human message — i.e. all the
    replies the current turn produced (a chained lookup→score turn yields two).
    Empty when the turn routed to no tool. Used by the UI to render a turn."""
    replies: list[str] = []
    for msg in reversed(messages or []):
        if _msg_role(msg) in ("human", "user"):
            break
        replies.append(_msg_content(msg))
    return replies[::-1]


# --------------------------------------------------------------------------- #
# Conversation memory management (used by the Streamlit UI, Step 8)
# --------------------------------------------------------------------------- #

_SUMMARY_PROMPT = (
    "Summarize the following call-center assistant conversation into a few concise "
    "bullet points. Preserve the concrete facts that later turns may refer back to: "
    "which calls were looked up (their ids), which were scored and their verdicts, "
    "which orders were looked up (their ids) and any policy questions asked. Do not "
    "invent anything. Output only the summary.\n\n"
    "Conversation:\n{conversation}\n\nSummary:"
)


def _transcript(messages: list) -> str:
    """Plain-text 'User: / Assistant:' rendering of a message list (a summary
    SystemMessage renders as Assistant — it is the assistant's own memory)."""
    lines = []
    for msg in messages:
        role = _msg_role(msg) or "?"
        who = "User" if role in ("human", "user") else "Assistant"
        lines.append(f"{who}: {_msg_content(msg)}")
    return "\n".join(lines).strip()


def summarize_history(messages: list) -> str:
    """Compress a list of chat messages into a short plain-text summary.

    Reuses the import-time supervisor client (no new LLM is built) and always
    returns a string. Used by the UI to bound stored conversation memory once the
    chat runs long; on any failure it returns a minimal, honest fallback rather
    than raising, matching the tools' string-only contract.
    """
    conversation = _transcript(messages)
    if not conversation:
        return ""
    try:
        raw = _SUPERVISOR_LLM.invoke(_SUMMARY_PROMPT.format(conversation=conversation))
        content = _msg_content(raw) if not isinstance(raw, str) else raw
        summary = _clean_content(content)
        return summary or "(earlier conversation summarized)"
    except Exception as exc:  # noqa: BLE001 - never let summarization crash a turn
        log.warning(f"[graph] summarize_history failed: {exc}")
        return "(earlier conversation summarized)"


# --------------------------------------------------------------------------- #
# Nodes — every data-fetching node appends exactly one tool_trace entry
# --------------------------------------------------------------------------- #

def supervisor_node(state: AgentState) -> dict:
    """Ask the supervisor LLM which tools to run; set next_tool + pending_tools.
    Not a data-fetching tool, so it appends NO tool_trace entry."""
    message = _last_user_message(state)
    raw = _SUPERVISOR_LLM.invoke(SUPERVISOR_PROMPT.format(message=message))
    content = _msg_content(raw) if not isinstance(raw, str) else raw
    tools = _parse_tools(content)

    # Role gating: a customer may only reach the policy tool. If a customer's
    # request routed to lookup/score, refuse here (emit the message and end the
    # turn) rather than silently ending with no answer.
    role = (state.get("role") or "supervisor").strip().lower()
    if role == "customer":
        allowed = [t for t in tools if t in CUSTOMER_ALLOWED_TOOLS]
        if tools and not allowed:
            log.warning(f"[graph] supervisor role=customer DENIED tools={tools} message={message!r}")
            return {
                "messages": [AIMessage(content=CUSTOMER_REFUSAL)],
                "next_tool": "end",
                "pending_tools": [],
            }
        tools = allowed

    # A "lookup" that would run with NO filters dumps rows. When calls are already
    # loaded, the request is a back-reference ("what was this call about?") the
    # routing LLM misread — answer from memory instead. Fuzzy dates ("recent")
    # are left to lookup's Stage 2, and a real Stage-1 match stays a real lookup.
    if (
        tools[:1] == ["lookup"]
        and state.get("call_records")
        and not _regex_filters(message)
        and not _FUZZY_DATE_RE.search(message)
    ):
        tools = ["answer"] + [t for t in tools[1:] if t != "score"]

    log.info(f"[graph] supervisor role={role} message={message!r} raw={content!r} -> tools={tools}")

    next_tool = tools[0] if tools else "end"
    pending_tools = tools[1:]
    return {"next_tool": next_tool, "pending_tools": pending_tools}


def policy_node(state: AgentState) -> dict:
    """Answer a policy question via Tool 1; policy_search has no degrade path
    worth surfacing here, so llm_degraded is always False."""
    message = _last_user_message(state)
    result = search_policy_with_context(message)
    # Cite the policy files the answer was grounded in, so the reader can tell
    # retrieved policy text apart from anything the model generated.
    answer = result["answer"]
    if result["sources"]:
        answer += "\n\n_Sources: " + ", ".join(result["sources"]) + "_"
    trace = {"tool": "policy", "source_file": "data/policies/", "llm_degraded": False}
    return {
        "messages": [AIMessage(content=answer)],
        "tool_trace": state.get("tool_trace", []) + [trace],
    }


def lookup_node(state: AgentState) -> dict:
    """Look up call records via Tool 2, and build call_records ({call_id,
    transcript}) for a possible downstream scorer. Surfaces whether Stage-2 LLM
    extraction degraded to keyword-only matching (both in tool_trace and, when
    degraded, as a plain-language note prepended to the user-facing message)."""
    message = _last_user_message(state)
    display = lookup_calls(message)  # the formatted, user-facing result

    # Re-resolve with status so we can (a) report degradation and (b) rebuild the
    # matching rows to extract transcripts for the scorer.
    from src.tools.call_lookup import resolve_filters_with_status, _apply_filters, _load_df

    filters, llm_degraded = resolve_filters_with_status(message)
    rows = _apply_filters(_load_df(), filters)

    # Resolve the transcript column defensively (don't hardcode "transcript").
    transcript_col = next((c for c in rows.columns if "transcript" in c.lower()), None)
    if transcript_col is None:
        raise RuntimeError(
            f"lookup_node: no transcript-like column found; columns were: {list(rows.columns)}"
        )

    call_records = [
        {"call_id": row["call_id"], "transcript": row[transcript_col]}
        for _, row in rows.iterrows()
    ]

    if llm_degraded:
        note = (
            "(Note: some filters may not have been fully understood — the AI "
            "extraction step was unavailable, so this used keyword-only matching.)\n\n"
        )
        display = note + display

    # Carry the fetched call_ids ON the entry (not just in call_records) so Step 8
    # reads "which calls did this tool touch" off tool_trace for lookup exactly as
    # it does for score — no reaching into other state fields. Plural here (one
    # lookup entry spans N calls); score entries are one-per-call and use singular
    # call_id.
    trace = {
        "tool": "lookup",
        "call_ids": [record["call_id"] for record in call_records],
        "source_file": "data/calls.csv",
        "llm_degraded": llm_degraded,
    }
    log.info(f"[graph] lookup_node matched {len(call_records)} record(s), llm_degraded={llm_degraded}")
    return {
        "messages": [AIMessage(content=display)],
        # REPLACE (not append) so call_records is always "the calls currently in
        # focus" = the latest lookup. This lets a threaded follow-up ("score them")
        # score exactly the last lookup instead of re-scoring stale records from
        # earlier turns. Within a single chained "lookup, score" turn this is
        # behavior-identical to appending onto an empty list.
        "call_records": call_records,
        "tool_trace": state.get("tool_trace", []) + [trace],
    }


def order_node(state: AgentState) -> dict:
    """Answer an order/delivery/refund question via Tool 4. Tool 4 swallows its
    own Stage-2 failures (falling back to regex-only filters) and exposes no
    degraded flag, so llm_degraded is always False here."""
    message = _last_user_message(state)
    # The tool sees only this message, so a follow-up ("when can I expect the
    # return?") must be told which order the conversation is already about.
    focus = focus_order_id([_msg_content(m) for m in state.get("messages") or []])
    answer = lookup_orders(message, focus_order_id=focus)
    trace = {
        "tool": "order",
        "source_file": "data/orders.csv + shipments.csv + returns.csv",
        "llm_degraded": False,
    }
    return {
        "messages": [AIMessage(content=answer)],
        "tool_trace": state.get("tool_trace", []) + [trace],
    }


_ANSWER_PROMPT = (
    "You are a call-center QA assistant. Answer the user's LAST message using ONLY "
    "the conversation below — it is your memory of what was looked up, scored and "
    "answered so far. Be concise. If the conversation does not contain what is "
    "needed, say so and suggest what to look up; never invent calls, orders, "
    "scores or policy.\n\n{transcripts}Conversation:\n{conversation}\n\nAnswer:"
)


def answer_node(state: AgentState) -> dict:
    """Reply from conversation memory (the accumulated — and, past 6 turns,
    summarized — `messages`). Fetches no data, so like the supervisor it appends
    NO tool_trace entry. Reuses the import-time supervisor client."""
    # The calls in focus (latest lookup) carry their full transcripts in
    # call_records, not in messages — include them so "summarize the call" can
    # actually read the call rather than the scorecard's quotes of it.
    loaded = "".join(
        f"[{r['call_id']}]\n{r['transcript']}\n\n" for r in state.get("call_records") or []
    )
    transcripts = f"Call transcripts currently loaded:\n{loaded}" if loaded else ""
    raw = _SUPERVISOR_LLM.invoke(
        _ANSWER_PROMPT.format(
            transcripts=transcripts, conversation=_transcript(state.get("messages") or [])
        )
    )
    content = _msg_content(raw) if not isinstance(raw, str) else raw
    answer = _clean_content(content) or "I don't have anything in this conversation to answer that from."
    return {"messages": [AIMessage(content=answer)]}


def scorer_node(state: AgentState, config: Optional[RunnableConfig] = None) -> dict:
    """Score every call_record via Tool 3, one report each. Appends one
    tool_trace entry PER call scored (chosen over once-per-batch so the trace
    row-count matches the number of reports). If there are
    no call_records, nothing ran: return a nudge and append no trace entry."""
    call_records = state.get("call_records") or []
    if not call_records:
        return {
            "messages": [
                AIMessage(
                    content="Please look up a call first — I need a call record to score."
                )
            ]
        }

    reports: list[str] = []
    traces: list[dict] = []
    stopped = False
    for record in call_records:
        # Cooperative stop: if the UI asked to cancel, stop before the next
        # (expensive) score_call rather than mid-generation.
        if is_cancelled(config):
            stopped = True
            log.warning(f"[graph] scorer_node cancelled after {len(reports)} of {len(call_records)} call(s)")
            break
        reports.append(score_call(record["transcript"], call_id=record["call_id"]))
        # Stamp each per-call entry with its call_id so Step 8 can tell N score
        # entries apart (a chained lookup->score turn can score many calls). The
        # call_id key is present only on per-call tool entries — other nodes omit
        # it, so consumers should read it with .get("call_id").
        traces.append(
            {
                "tool": "score",
                "call_id": record["call_id"],
                "source_file": "data/calls.csv + data/policies/",
                "llm_degraded": False,
            }
        )

    joined = "\n\n".join(reports)
    if stopped:
        note = "_⏹ Scoring stopped — the remaining calls were not scored._"
        joined = (joined + "\n\n" + note) if joined else note
    log.info(f"[graph] scorer_node scored {len(reports)} call(s){' (stopped early)' if stopped else ''}")
    return {
        "messages": [AIMessage(content=joined)],
        "qa_scores": state.get("qa_scores", []) + reports,
        "tool_trace": state.get("tool_trace", []) + traces,
    }


# --------------------------------------------------------------------------- #
# Routing
# --------------------------------------------------------------------------- #

def route_decision(state: AgentState) -> str:
    """Route on the supervisor's first choice (next_tool); END when none."""
    nxt = (state.get("next_tool") or "").strip().lower()
    return nxt if nxt in _VALID_TOOLS else END


def route_after_lookup(state: AgentState) -> str:
    """Chain scoring after a lookup only when pending_tools[0] == 'score'."""
    pending = state.get("pending_tools") or []
    return "score" if pending and pending[0] == "score" else END


# --------------------------------------------------------------------------- #
# Graph assembly
# --------------------------------------------------------------------------- #

def build_graph():
    """Build and compile the supervisor StateGraph over AgentState."""
    graph = StateGraph(AgentState)

    graph.add_node("supervisor", supervisor_node)
    graph.add_node("policy", policy_node)
    graph.add_node("lookup", lookup_node)
    graph.add_node("order", order_node)
    graph.add_node("score", scorer_node)
    graph.add_node("answer", answer_node)

    graph.set_entry_point("supervisor")
    graph.add_conditional_edges(
        "supervisor",
        route_decision,
        {
            "policy": "policy",
            "lookup": "lookup",
            "order": "order",
            "score": "score",
            "answer": "answer",
            END: END,
        },
    )
    graph.add_edge("policy", END)
    graph.add_edge("order", END)
    graph.add_edge("answer", END)
    graph.add_conditional_edges("lookup", route_after_lookup, {"score": "score", END: END})
    graph.add_edge("score", END)

    return graph.compile()


if __name__ == "__main__":  # manual smoke test — run from the repo root
    from langchain_core.messages import HumanMessage

    app = build_graph()
    for user_msg in (
        "What is the replacement window?",   # -> policy
        "show me call 1042",                 # -> lookup
        "look up call 1016 and score it",    # -> lookup, score
        "where is my order 5031?",           # -> order
    ):
        print("\n" + "=" * 72 + f"\nUSER: {user_msg}\n" + "=" * 72)
        result = app.invoke(
            {
                "messages": [HumanMessage(content=user_msg)],
                "call_records": [],
                "qa_scores": [],
                "next_tool": "",
                "pending_tools": [],
                "tool_trace": [],
            }
        )
        print("FINAL MESSAGE:\n", _msg_content(result["messages"][-1]))
        print("TOOL TRACE:", result["tool_trace"])
