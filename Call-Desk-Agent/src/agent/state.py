"""Step 6 — LangGraph shared state (AgentState).

The single TypedDict threaded through every node of the supervisor graph in
``src/agent/graph.py``. Only ``messages`` carries a reducer (``add_messages``,
so returned messages are appended, not replaced); every other field is a plain
value, so a node that wants to *append* to a list must return the concatenation
of the current value and its new entries (see the nodes in ``graph.py``).

Fields:
  * messages        — the running chat history (LangChain messages). The
                      ``add_messages`` reducer appends whatever a node returns.
  * call_records    — [{call_id, transcript}] fetched by the lookup node; the
                      scorer node reads these to know what to score.
  * qa_scores       — the QA scorecard report string(s) produced by the scorer.
  * role            — who is asking: "supervisor" (full access: policy, lookup,
                      order, score) or "customer" (policy + order status). The
                      supervisor node reads this to gate which tools a request may
                      use; a customer request for call records or QA scores is
                      refused, not routed. NOTE: this gates which TOOLS a role may
                      reach, not which ROWS it sees — there is no per-customer
                      identity in this state, so the customer role can ask about
                      any order. See the ponytail note in graph.py.
  * next_tool       — the tool the supervisor routed to first (route_decision).
  * pending_tools   — tools still queued after the first (route_after_lookup
                      checks ``pending_tools[0] == "score"`` to chain scoring
                      after a lookup).
  * tool_trace      — one dict appended by each data-fetching node as it runs,
                      recording which tool ran, its data source, and whether the
                      LLM step degraded, e.g.
                      ``{"tool": "lookup", "call_ids": [...],
                         "source_file": "data/calls.csv",
                         "llm_degraded": False}``. Every entry names the calls the
                      tool touched ON the entry itself, so Step 8 never has to
                      cross-reference other state fields: the lookup entry (one
                      per run, spanning N calls) carries a plural ``call_ids``
                      list; each score entry (one per call scored) carries a
                      singular ``call_id``. The policy node touches no call, so it
                      carries neither key — read them with ``.get(...)``. This is
                      Step 8 (the Streamlit UI)'s future data source for "show
                      which tool was used for each response" — captured now so
                      Step 8 needs no change to node logic later.
"""

from __future__ import annotations

from typing import Annotated, TypedDict

from langgraph.graph.message import add_messages


class AgentState(TypedDict):
    messages: Annotated[list, add_messages]
    call_records: list
    qa_scores: list
    role: str  # "supervisor" (full access) or "customer" (policy + order only);
               # gates which TOOLS the supervisor node routes to — not which rows
               # the tool returns (there is no per-customer identity here).
    next_tool: str
    pending_tools: list
    tool_trace: list  # NEW — each node appends one dict as it runs, e.g.
                      # {"tool": "lookup", "source_file": "data/calls.csv",
                      #  "llm_degraded": False}
                      # This is Step 8 (Streamlit UI)'s future data source for
                      # "show which tool was used for each response" — captured
                      # now so Step 8 doesn't need to touch node logic later.
