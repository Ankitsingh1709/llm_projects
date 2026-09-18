"""Offline AppTest checks for the landing page → customer / supervisor sign-in flow.

Run from the repo root:

    myenv/bin/python -m unittest tests/test_ui_flow.py -v

Same offline setup as tests/test_review_fixes.py: the two heavy tool modules are
stubbed and the ``openai`` provider is forced with a dummy key, so building the
graph (which the chat page does on entry) needs no provider running.
"""

from __future__ import annotations

import os
import shutil
import sys
import tempfile
import types
import unittest
from pathlib import Path

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
# setdefault: if test_review_fixes.py ran first in the same process its (identical) stubs win.
sys.modules.setdefault("src.tools.policy_search", _policy)
sys.modules.setdefault("src.tools.qa_scorer", _scorer)

from streamlit.testing.v1 import AppTest  # noqa: E402
from src.ui import auth  # noqa: E402
from src.ui.auth import load_accounts  # noqa: E402

APP = str(Path(__file__).resolve().parents[1] / "src" / "ui" / "app.py")


def _app() -> AppTest:
    """A fresh app run, sitting on the landing page."""
    return AppTest.from_file(APP, default_timeout=60).run()


def _button_keys(at: AppTest) -> set:
    return {b.key for b in at.button}


class Landing(unittest.TestCase):
    def test_landing_shows_two_entry_points_and_no_chat(self):
        at = _app()
        self.assertIn("landing_customer", _button_keys(at))
        self.assertIn("landing_supervisor", _button_keys(at))
        self.assertEqual(len(at.chat_input), 0)
        self.assertIsNone(at.session_state["user"])

    def test_continue_as_customer_opens_the_customer_chat(self):
        at = _app()
        at.button(key="landing_customer").click().run()
        self.assertEqual(at.session_state["role"], "Customer")
        self.assertEqual(len(at.chat_input), 1)
        self.assertIn("Customer Care Agent", at.title[0].value)

    def test_sign_out_returns_to_the_landing_page(self):
        at = _app()
        at.button(key="landing_customer").click().run()
        at.button(key="sign_out").click().run()
        self.assertIsNone(at.session_state["user"])
        self.assertIn("landing_customer", _button_keys(at))


class SupervisorSignIn(unittest.TestCase):
    def _at_login(self) -> AppTest:
        at = _app()
        at.button(key="landing_supervisor").click().run()
        return at

    def test_supervisor_button_opens_the_sign_in_form(self):
        at = self._at_login()
        self.assertIn("Sign in", at.title[0].value)
        self.assertEqual(len(at.chat_input), 0)
        self.assertIsNone(at.session_state["user"])

    def test_wrong_credentials_show_an_error_and_keep_the_form(self):
        at = self._at_login()
        at.text_input(key="login_email").set_value("someone@example.com")
        at.text_input(key="login_password").set_value("supervisor123")
        at.button(key="login_submit").click().run()
        self.assertIn("Invalid email or password", at.error[0].value)
        self.assertIsNone(at.session_state["user"])
        self.assertEqual(len(at.chat_input), 0)

    def test_listed_account_opens_the_supervisor_chat(self):
        email, password = next(iter(load_accounts().items()))
        at = self._at_login()
        at.text_input(key="login_email").set_value(email)
        at.text_input(key="login_password").set_value(password)
        at.button(key="login_submit").click().run()
        self.assertEqual(at.session_state["role"], "Supervisor")
        self.assertEqual(at.session_state["user"], email)
        self.assertEqual(len(at.chat_input), 1)
        self.assertIn("Call Center QA Agent", at.title[0].value)

    def test_back_returns_to_the_landing_page(self):
        at = self._at_login()
        at.button(key="login_back").click().run()
        self.assertIsNone(at.session_state["user"])
        self.assertIn("landing_customer", _button_keys(at))


class ForgotPassword(unittest.TestCase):
    """The reset flow rewrites the sheet, so these run against a temp copy of it.
    AppTest runs app.py in this process, so patching the module attribute is enough."""

    def setUp(self):
        self._tmp = tempfile.mkdtemp()
        self._orig = auth.SUPERVISORS_CSV
        auth.SUPERVISORS_CSV = shutil.copy(self._orig, os.path.join(self._tmp, "supervisors.csv"))

    def tearDown(self):
        auth.SUPERVISORS_CSV = self._orig
        shutil.rmtree(self._tmp)

    def _at_forgot(self) -> AppTest:
        at = _app()
        at.button(key="landing_supervisor").click().run()
        at.button(key="login_forgot").click().run()
        return at

    def test_forgot_shows_the_email_step_without_the_sign_in_form(self):
        at = self._at_forgot()
        self.assertIn("reset_email", {t.key for t in at.text_input})
        self.assertNotIn("login_email", {t.key for t in at.text_input})

    def test_unknown_email_is_rejected(self):
        at = self._at_forgot()
        at.text_input(key="reset_email").set_value("nobody@example.com")
        at.button(key="reset_continue").click().run()
        self.assertIn("No supervisor account", at.error[0].value)
        self.assertNotIn("reset_password", {t.key for t in at.text_input})

    def test_mismatched_passwords_are_rejected(self):
        email = next(iter(load_accounts()))
        at = self._at_forgot()
        at.text_input(key="reset_email").set_value(email)
        at.button(key="reset_continue").click().run()
        at.text_input(key="reset_password").set_value("abc")
        at.text_input(key="reset_confirm").set_value("abd")
        at.button(key="reset_submit").click().run()
        self.assertIn("do not match", at.error[0].value)
        self.assertEqual(load_accounts()[email], "supervisor123")  # sheet untouched

    def test_new_password_is_written_and_signs_in(self):
        email = next(iter(load_accounts()))
        at = self._at_forgot()
        at.text_input(key="reset_email").set_value(email.upper())
        at.button(key="reset_continue").click().run()
        at.text_input(key="reset_password").set_value("newpass")
        at.text_input(key="reset_confirm").set_value("newpass")
        at.button(key="reset_submit").click().run()
        self.assertEqual(load_accounts()[email], "newpass")
        self.assertIn("Password updated", at.success[0].value)
        # Back on the sign-in form; the new password works.
        at.text_input(key="login_email").set_value(email)
        at.text_input(key="login_password").set_value("newpass")
        at.button(key="login_submit").click().run()
        self.assertEqual(at.session_state["role"], "Supervisor")

    def test_back_returns_to_the_sign_in_form(self):
        at = self._at_forgot()
        at.button(key="reset_back").click().run()
        self.assertIn("login_email", {t.key for t in at.text_input})
        self.assertIsNone(at.session_state["user"])


if __name__ == "__main__":
    unittest.main()
