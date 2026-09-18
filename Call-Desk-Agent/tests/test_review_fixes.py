"""Offline unit checks for the code-review fixes and the mock sign-in.

Run from the repo root:

    myenv/bin/python -m unittest tests/test_review_fixes.py -v

Importing ``src.agent.graph`` normally builds every tool's LLM client and Tool 1's
FAISS index at import. This file stubs the two heavy modules (policy_search,
qa_scorer) in ``sys.modules`` and forces the ``openai`` provider with a dummy key
(``ChatOpenAI`` constructs without a network call), so it runs with no provider up.
"""

from __future__ import annotations

import os
import shutil
import sys
import tempfile
import threading
import types
import unittest
import warnings
from unittest.mock import patch

# Must happen before src.config is imported (it reads these at import).
os.environ["ACTIVE_PROVIDER"] = "openai"
os.environ.setdefault("OPENAI_API_KEY", "test-key")

_policy = types.ModuleType("src.tools.policy_search")
_policy.search_policy = lambda query: "policy answer"
_policy.search_policy_with_context = lambda query, call_type=None: {
    "answer": "policy answer", "chunks_used": [], "routed_call_type": None, "sources": [],
}
_scorer = types.ModuleType("src.tools.qa_scorer")
_scorer.score_call = lambda transcript, call_id="", policy_context="": f"scored {call_id}"
_scorer.SLA_PARAM = "sla_met"
_scorer.PARAM_NAMES = [
    "greeting", "identity_verification", "problem_acknowledgement", "call_classification",
    "solution_offered", "policy_compliance", "professional_tone", "proper_closure", "sla_met",
]
sys.modules["src.tools.policy_search"] = _policy
sys.modules["src.tools.qa_scorer"] = _scorer

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage  # noqa: E402
from src.agent import graph  # noqa: E402
from src.eval.validate_scorer import _parse_report  # noqa: E402
from src.tools import order_lookup  # noqa: E402
from src.ui import auth  # noqa: E402
from src.ui.auth import load_accounts, resolve_role, set_password  # noqa: E402


class TurnReplies(unittest.TestCase):
    def test_returns_every_reply_after_the_last_human_message(self):
        messages = [
            SystemMessage(content="Summary of earlier conversation:\n- looked up CALL-1001"),
            HumanMessage(content="show me call 1042"),
            AIMessage(content="[CALL-1042] ..."),
            HumanMessage(content="score Rahul's last 2 calls"),
            AIMessage(content="[CALL-1001] ...\n[CALL-1034] ..."),   # lookup reply
            AIMessage(content="#### QA Scorecard — CALL-1001"),       # score reply
        ]
        self.assertEqual(
            graph.turn_replies(messages),
            ["[CALL-1001] ...\n[CALL-1034] ...", "#### QA Scorecard — CALL-1001"],
        )

    def test_empty_when_the_turn_routed_nowhere(self):
        messages = [HumanMessage(content="hello"), AIMessage(content="hi"), HumanMessage(content="???")]
        self.assertEqual(graph.turn_replies(messages), [])

    def test_handles_dict_messages_and_empty_input(self):
        self.assertEqual(graph.turn_replies([]), [])
        messages = [{"role": "user", "content": "q"}, {"role": "assistant", "content": "a"}]
        self.assertEqual(graph.turn_replies(messages), ["a"])


def _two_records() -> dict:
    return {
        "messages": [HumanMessage(content="score them")],
        "call_records": [
            {"call_id": "CALL-1001", "transcript": "t1"},
            {"call_id": "CALL-1002", "transcript": "t2"},
        ],
        "qa_scores": [],
        "tool_trace": [],
    }


class PerSessionCancel(unittest.TestCase):
    def test_scores_everything_when_no_cancel_event_is_passed(self):
        out = graph.scorer_node(_two_records())
        self.assertEqual(out["qa_scores"], ["scored CALL-1001", "scored CALL-1002"])
        self.assertEqual(len(out["tool_trace"]), 2)

    def test_stops_before_the_first_call_when_its_own_event_is_set(self):
        cancel = threading.Event()
        cancel.set()
        out = graph.scorer_node(_two_records(), {"configurable": {"cancel": cancel}})
        self.assertEqual(out["qa_scores"], [])
        self.assertIn("Scoring stopped", out["messages"][0].content)

    def test_another_sessions_unset_event_does_not_stop_this_run(self):
        other_session = threading.Event()  # never set — belongs to someone else's turn
        out = graph.scorer_node(_two_records(), {"configurable": {"cancel": other_session}})
        self.assertEqual(len(out["qa_scores"]), 2)

    def test_global_cancel_api_is_gone(self):
        for name in ("_CANCEL", "request_cancel", "reset_cancel"):
            self.assertFalse(hasattr(graph, name), name)


class CancelThroughCompiledGraph(unittest.TestCase):
    """Critical finding 1: under `from __future__ import annotations`, a
    `RunnableConfig | None` annotation on scorer_node is a *string* LangGraph
    1.2.11 does not recognise as an injectable config type, so it warns at
    build_graph() and calls the node with config=None — the Stop button's
    cancel Event never arrives. Drives cancellation THROUGH the compiled graph
    (not a direct scorer_node call) so a regression here is caught for real."""

    def test_cancel_event_set_before_invoke_stops_the_graph_from_scoring(self):
        original_llm = graph._SUPERVISOR_LLM
        graph._SUPERVISOR_LLM = types.SimpleNamespace(
            invoke=lambda *a, **k: AIMessage(content="score")
        )
        try:
            with warnings.catch_warnings(record=True) as caught:
                warnings.simplefilter("always")
                app = graph.build_graph()
            user_warnings = [w for w in caught if issubclass(w.category, UserWarning)]
            self.assertEqual(user_warnings, [], [str(w.message) for w in user_warnings])

            cancel = threading.Event()
            cancel.set()
            state = {
                "messages": [HumanMessage(content="score them")],
                "call_records": [
                    {"call_id": "CALL-1001", "transcript": "t1"},
                    {"call_id": "CALL-1002", "transcript": "t2"},
                ],
                "qa_scores": [],
                "tool_trace": [],
                "role": "supervisor",
                "next_tool": "",
                "pending_tools": [],
            }
            result = app.invoke(state, config={"configurable": {"cancel": cancel}})
        finally:
            graph._SUPERVISOR_LLM = original_llm

        self.assertEqual(result["qa_scores"], [])
        self.assertIn("Scoring stopped", result["messages"][-1].content)


def _scorecard(overall: str, why: str) -> str:
    """Mimic qa_scorer._format_report: a Markdown table + bold footer."""
    rows = "\n".join(f"| {p} | ❌ FAIL | 10 | {why} |" for p in _scorer.PARAM_NAMES)
    return (
        "#### QA Scorecard — CALL-1016\n*Category: inbound — weights sum to 100*\n\n"
        "| Parameter | Result | Weight | Why |\n|:--|:--:|:--:|:--|\n"
        f"{rows}\n\n**Weighted score: 40/100 (40%) — {overall}**"
    )


class ParseReportFooter(unittest.TestCase):
    def test_pass_text_inside_a_justification_cannot_flip_a_fail(self):
        report = _scorecard("FAIL", "agent said the customer was fine — PASS them along")
        per_param, overall = _parse_report(report)
        self.assertEqual(overall, "FAIL")
        self.assertEqual(per_param["professional_tone"], "FAIL")
        self.assertEqual(len(per_param), 9)

    def test_footer_pass_is_read(self):
        self.assertEqual(_parse_report(_scorecard("PASS", "fine"))[1], "PASS")

    def test_missing_footer_is_unknown(self):
        self.assertEqual(_parse_report("no table here — PASS")[1], "?")


class ResolveRole(unittest.TestCase):
    """Runs against a temp copy of data/supervisors.csv so no test touches the real sheet."""

    def setUp(self):
        self._tmp = tempfile.mkdtemp()
        self._orig = auth.SUPERVISORS_CSV
        auth.SUPERVISORS_CSV = shutil.copy(self._orig, os.path.join(self._tmp, "supervisors.csv"))

    def tearDown(self):
        auth.SUPERVISORS_CSV = self._orig
        shutil.rmtree(self._tmp)

    def test_sheet_has_the_two_seeded_accounts(self):
        self.assertEqual(
            load_accounts(),
            {"qa.lead@example.com": "supervisor123", "supervisor@example.com": "supervisor123"},
        )

    def test_set_password_rewrites_the_sheet_and_signs_in(self):
        self.assertTrue(set_password("  QA.Lead@example.com ", "newpass"))
        self.assertEqual(resolve_role("qa.lead@example.com", "newpass"), "Supervisor")
        self.assertEqual(resolve_role("qa.lead@example.com", "supervisor123"), "Customer")
        self.assertEqual(resolve_role("supervisor@example.com", "supervisor123"), "Supervisor")  # untouched
        self.assertEqual(len(load_accounts()), 2)

    def test_set_password_for_unknown_email_is_refused(self):
        self.assertFalse(set_password("nobody@example.com", "x"))
        self.assertEqual(len(load_accounts()), 2)

    def test_missing_sheet_means_no_supervisors(self):
        os.remove(auth.SUPERVISORS_CSV)
        self.assertEqual(load_accounts(), {})
        self.assertEqual(resolve_role("qa.lead@example.com", "supervisor123"), "Customer")

    def test_listed_email_with_its_password_is_supervisor(self):
        email, password = next(iter(load_accounts().items()))
        self.assertEqual(resolve_role(email, password), "Supervisor")

    def test_email_is_case_and_whitespace_insensitive(self):
        email, password = next(iter(load_accounts().items()))
        self.assertEqual(resolve_role(f"  {email.upper()} ", password), "Supervisor")

    def test_wrong_password_is_customer(self):
        email = next(iter(load_accounts()))
        self.assertEqual(resolve_role(email, "nope"), "Customer")

    def test_unknown_email_is_customer_with_any_password(self):
        self.assertEqual(resolve_role("someone@example.com", ""), "Customer")
        self.assertEqual(resolve_role("someone@example.com", "supervisor123"), "Customer")

    def test_non_ascii_password_for_a_listed_email_does_not_raise(self):
        # hmac.compare_digest on plain `str` requires both args to be ASCII-only
        # and raises TypeError otherwise; a real login form can receive this.
        email = next(iter(load_accounts()))
        self.assertEqual(resolve_role(email, "pässword"), "Customer")


class OrderFocus(unittest.TestCase):
    """A follow-up like "when can I expect the return?" names no order, so the
    order tool must answer about the order in focus from earlier in the chat —
    not dump DEFAULT_LIMIT unrelated orders (the bug: 10 orders for one question)."""

    def test_focus_is_the_single_order_named_most_recently(self):
        texts = [
            "did my refund for order 5027 go through?",
            "[ORD-5027] 2026-08-28 — Kavya Iyer ...\n    Return: RET-7027 approved",
            "when can i expect the retirn",
        ]
        self.assertEqual(order_lookup.focus_order_id(texts), "ORD-5027")

    def test_no_focus_when_the_last_mention_listed_many_orders(self):
        texts = ["show me my orders", "[ORD-5001] ...\n\n[ORD-5002] ...", "when will it arrive"]
        self.assertIsNone(order_lookup.focus_order_id(texts))

    def test_follow_up_with_no_filters_answers_about_the_focus_order(self):
        with patch.object(order_lookup, "_llm_filters", return_value=None):
            out = order_lookup.lookup_orders("when can i expect the return", focus_order_id="ORD-5027")
        self.assertIn("[ORD-5027]", out)
        self.assertNotIn("[ORD-5001]", out)

    def test_explicit_filters_in_the_request_beat_the_focus(self):
        out = order_lookup.lookup_orders("where is order 5031", focus_order_id="ORD-5027")
        self.assertIn("[ORD-5031]", out)
        self.assertNotIn("ORD-5027", out)

    def test_order_node_passes_the_conversation_focus_to_the_tool(self):
        seen = {}

        def fake_lookup(query, focus_order_id=None):
            seen.update(query=query, focus=focus_order_id)
            return "ok"

        state = {
            "messages": [
                HumanMessage(content="did my refund for order 5027 go through?"),
                AIMessage(content="[ORD-5027] ..."),
                HumanMessage(content="when can i expect the return"),
            ],
            "tool_trace": [],
        }
        with patch.object(graph, "lookup_orders", fake_lookup):
            graph.order_node(state)
        self.assertEqual(seen, {"query": "when can i expect the return", "focus": "ORD-5027"})


class AnswerFromConversation(unittest.TestCase):
    """"what was the call about?" after a lookup/score must be answered FROM the
    conversation (the graph already keeps `messages`, summarized after 6 turns),
    not routed to a data tool that only sees the last message."""

    def _fake_llm(self, replies: dict):
        # Routing prompts end with "Tools:"; anything else is the answer prompt.
        def invoke(prompt, *a, **k):
            key = "route" if str(prompt).rstrip().endswith("Tools:") else "answer"
            return AIMessage(content=replies[key])
        return types.SimpleNamespace(invoke=invoke)

    def test_answer_is_a_valid_tool_for_customers_too(self):
        self.assertIn("answer", graph._VALID_TOOLS)
        self.assertIn("answer", graph.CUSTOMER_ALLOWED_TOOLS)

    def test_answer_node_replies_from_the_conversation_and_fetches_nothing(self):
        seen = {}
        def invoke(prompt, *a, **k):
            seen["prompt"] = prompt
            return AIMessage(content="It was about a router disconnecting every evening.")
        state = {
            "messages": [
                SystemMessage(content="Summary of earlier conversation:\n- looked up CALL-1016"),
                AIMessage(content="QA Scorecard — CALL-1016 ... router keeps disconnecting"),
                HumanMessage(content="what was the call about?"),
            ],
            "tool_trace": [{"tool": "score", "call_id": "CALL-1016"}],
        }
        with patch.object(graph, "_SUPERVISOR_LLM", types.SimpleNamespace(invoke=invoke)):
            out = graph.answer_node(state)
        self.assertIn("router keeps disconnecting", seen["prompt"])   # sees prior replies
        self.assertIn("looked up CALL-1016", seen["prompt"])          # sees the summary
        self.assertEqual(out["messages"][0].content, "It was about a router disconnecting every evening.")
        self.assertNotIn("tool_trace", out)                            # not a data tool

    def test_follow_up_routes_to_answer_through_the_compiled_graph(self):
        fake = self._fake_llm({"route": "answer", "answer": "It was about a router."})
        with patch.object(graph, "_SUPERVISOR_LLM", fake):
            app = graph.build_graph()
            result = app.invoke({
                "messages": [
                    HumanMessage(content="score call 1016"),
                    AIMessage(content="QA Scorecard — CALL-1016 ... router"),
                    HumanMessage(content="what was the call about?"),
                ],
                "call_records": [], "qa_scores": [], "tool_trace": [],
                "role": "customer", "next_tool": "", "pending_tools": [],
            })
        self.assertEqual(result["messages"][-1].content, "It was about a router.")
        self.assertEqual(result["tool_trace"], [])

    def test_filterless_lookup_with_calls_loaded_becomes_answer(self):
        # The routing LLM said "lookup" for "what was this call about?" — with no
        # filters that dumps rows. Calls are already in focus, so answer instead.
        base = {"call_records": [{"call_id": "CALL-1016", "transcript": "t"}], "role": "supervisor"}
        fake = types.SimpleNamespace(invoke=lambda *a, **k: AIMessage(content="lookup"))
        with patch.object(graph, "_SUPERVISOR_LLM", fake):
            for msg, expected in (
                ("what was this call about?", "answer"),
                ("show me call 1042", "lookup"),        # real filter -> real lookup
                ("show me recent calls", "lookup"),     # fuzzy date -> Stage 2 lookup
            ):
                out = graph.supervisor_node({**base, "messages": [HumanMessage(content=msg)]})
                self.assertEqual(out["next_tool"], expected, msg)
            # Nothing loaded yet -> nothing to answer from; leave the LLM's choice.
            out = graph.supervisor_node({"messages": [HumanMessage(content="what was this call about?")],
                                         "call_records": [], "role": "supervisor"})
            self.assertEqual(out["next_tool"], "lookup")

    def test_answer_node_sees_the_loaded_transcripts(self):
        seen = {}
        def invoke(prompt, *a, **k):
            seen["prompt"] = prompt
            return AIMessage(content="ok")
        state = {
            "messages": [HumanMessage(content="summarize the call")],
            "call_records": [{"call_id": "CALL-1016", "transcript": "Customer: my router drops at 8pm"}],
        }
        with patch.object(graph, "_SUPERVISOR_LLM", types.SimpleNamespace(invoke=invoke)):
            graph.answer_node(state)
        self.assertIn("CALL-1016", seen["prompt"])
        self.assertIn("my router drops at 8pm", seen["prompt"])


if __name__ == "__main__":
    unittest.main()
