"""Step 8 — Streamlit chat UI for the call-center QA agent.

A chat interface over the supervisor LangGraph (``src/agent/graph.py``). Run it
from the repo root so the ``src`` package resolves:

    streamlit run src/ui/app.py

(The graph builds its LLM client at import, so the active provider must be
reachable — e.g. LM Studio up with a model loaded — before the app starts.)

What this UI adds on top of a plain per-turn invoke:

  * **Threaded memory.** One ``AgentState`` lives in ``st.session_state`` and is
    threaded through every turn, so ``messages`` accumulate and ``call_records``
    (the calls currently *in focus*) persist. A follow-up like "score them" reuses
    the previous lookup instead of asking again — the supervisor emits ``score``
    alone and the scorer reads the retained ``call_records``.
  * **Memory management.** Once the conversation runs long
    (``SUMMARY_TURN_THRESHOLD`` user turns), the older messages are compressed via
    ``graph.summarize_history`` into a single summary message (the last couple of
    turns are kept verbatim), and a visible "conversation summarized to manage
    memory" note is shown. The full transcript stays on screen — only the agent's
    working memory is bounded.
  * **Tool visibility.** Each assistant turn shows which tool(s) answered, read
    from that turn's ``tool_trace`` entries.
  * **Landing page + mock sign-in.** The app opens on a landing page that says
    what the agent does and offers two entry points. *Continue as a customer*
    needs no account. *Continue as a supervisor* opens a sign-in form that only
    admits the accounts in ``src/ui/auth.py``. The role is what
    ``supervisor_node`` gates tools on, so the login is real routing, not decoration.
  * **Liquid-glass theme.** ``GLASS_CSS`` (below) restyles Streamlit's chrome as
    translucent Apple-style materials floating on an ambient gradient, with
    reduced-transparency / high-contrast / reduced-motion fallbacks.
"""

from __future__ import annotations

import re
import sys
import threading
import time
from pathlib import Path

import streamlit as st
from langchain_core.messages import HumanMessage, SystemMessage

# `streamlit run src/ui/app.py` puts src/ui/ on sys.path — NOT the directory it
# was launched from — so `import src...` fails even when run from the repo root
# as documented. Put the repo root on the path ourselves (same trick the test
# notebooks use) so the documented command works with no PYTHONPATH.
_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from src.config import CONFIG  # noqa: E402 - must follow the sys.path bootstrap
from src.ui.auth import email_exists, resolve_role, set_password  # noqa: E402

# Attaching the Streamlit run-context to the worker thread avoids "missing
# ScriptRunContext" warnings; guarded so a version change can't break import.
try:  # pragma: no cover - import-path guard
    from streamlit.runtime.scriptrunner import add_script_run_ctx
except Exception:  # noqa: BLE001
    def add_script_run_ctx(thread):  # type: ignore
        return thread

POLL_SECONDS = 0.3  # how often the UI re-checks the background turn while it runs

# --------------------------------------------------------------------------- #
# Constants
# --------------------------------------------------------------------------- #

SUMMARY_TURN_THRESHOLD = 6   # summarize once the chat reaches this many user turns
KEEP_RECENT_MESSAGES = 4     # messages kept verbatim after a summary (~2 turns)

# Per-role page identity (browser tab title, header, subtitle). The Customer view
# is a customer-facing help agent; the Supervisor view is the internal QA tool.
ROLE_UI = {
    "Supervisor": {
        "icon": "📞",
        "title": "Call Center QA Agent",
        "caption": "Ask about company policies, look up call records, or score a call against the QA rubric.",
    },
    "Customer": {
        "icon": "💬",
        "title": "Customer Care Agent",
        "caption": "Ask about your orders — where they are, delivery dates, returns and refunds — or about our policies.",
    },
}

# Sample queries shown per role. Supervisor sees the full mix (lookup / score /
# policy); a customer sees policy questions only, matching their access.
SAMPLE_QUERIES_BY_ROLE = {
    "Supervisor": [
        "Show me Rahul's last 3 calls",
        "Score call CALL-1016",
        "Score Rahul's last 5 calls",
        "score those calls",
        "What is the escalation policy?",
    ],
    "Customer": [
        "Where is my order 5031?",
        "When will ORD-5033 be delivered?",
        "Did my refund for order 5027 go through?",
        "Which orders are out for delivery?",
        "What is the replacement policy?",
        "How do returns and refunds work?",
    ],
}

TOOL_LABELS = {
    "policy": "policy",
    "lookup": "lookup",
    "order": "order",
    "score": "score",
}


# Shown when the supervisor routed the request to no tool (the graph then appends
# no reply at all — previously the user's own message was echoed back).
NO_ROUTE_REPLY = (
    "I couldn't match that request to anything I can do. Try a policy question, "
    "a call lookup, an order question, or a scoring request."
)

# Landing-page copy: three things the agent does, shown as a row under the CTAs.
# (icon, title, two-line blurb) — the blurbs describe Tools 1, 4 and 2+3.
LANDING_FEATURES = [
    (
        "📚",
        "Policy answers, grounded",
        "Ask about replacements, returns, escalations or SLAs and get an answer drawn only "
        "from the policy documents — never from general knowledge.",
    ),
    (
        "📦",
        "Order status in plain language",
        "Where an order is, when it lands, whether a refund went through — resolved from "
        "the order, shipment and return records.",
    ),
    (
        "🧾",
        "Calls scored against the rubric",
        "Supervisors look up call records and score transcripts on a 9-parameter weighted "
        "QA rubric, with a justification for every parameter.",
    ),
]

# --------------------------------------------------------------------------- #
# Liquid-glass theme (Apple-style materials, depth and typography)
# --------------------------------------------------------------------------- #
# Injected once per rerun via st.markdown. Streamlit has no theming hook for
# translucent materials, so this is plain CSS over its data-testid hooks.
#
# The rules that shape it (Apple HIG / "Designing Fluid Interfaces"):
#   * Glass needs something to blur — the app sits on a soft ambient gradient,
#     and every panel is a translucent layer floating on THAT, never glass
#     stacked on glass (legibility collapses when you nest translucency).
#   * Material weight encodes hierarchy: the sidebar is the heaviest surface
#     (structural), chat cards are lighter, buttons lightest (interactive).
#   * Feedback lands on pointer-DOWN (:active), not on release, and takes 100ms.
#   * Type: system font, negative tracking on large text, near-zero on body.
#   * prefers-reduced-transparency / -contrast / -motion each get a real
#     fallback — reduced transparency means frosted-to-solid, not "no style".
GLASS_CSS = """
<style>
:root {
  --glass-bg:        rgba(255, 255, 255, 0.55);
  --glass-bg-strong: rgba(255, 255, 255, 0.72);
  --glass-edge:      rgba(255, 255, 255, 0.75);
  --glass-hairline:  rgba(0, 0, 0, 0.06);
  --glass-shadow:    0 8px 32px rgba(0, 0, 0, 0.10), 0 1px 2px rgba(0, 0, 0, 0.04);
  --glass-shadow-lg: 0 16px 48px rgba(0, 0, 0, 0.14), 0 1px 2px rgba(0, 0, 0, 0.05);
  --accent:          #0071e3;
  --ink:             #1d1d1f;
  --ink-dim:         #55555b;
  --canvas-1:        #eef1f6;
  --canvas-2:        #dfe6f0;
  --tint-user:       rgba(0, 113, 227, 0.10);
  --radius:          18px;
}

@media (prefers-color-scheme: dark) {
  :root {
    --glass-bg:        rgba(30, 32, 38, 0.55);
    --glass-bg-strong: rgba(24, 26, 32, 0.72);
    --glass-edge:      rgba(255, 255, 255, 0.14);
    --glass-hairline:  rgba(255, 255, 255, 0.08);
    --glass-shadow:    0 8px 32px rgba(0, 0, 0, 0.45), 0 1px 2px rgba(0, 0, 0, 0.30);
    --glass-shadow-lg: 0 16px 48px rgba(0, 0, 0, 0.55), 0 1px 2px rgba(0, 0, 0, 0.35);
    --accent:          #0a84ff;
    --ink:             #f5f5f7;
    --ink-dim:         #a1a1a8;
    --canvas-1:        #14161b;
    --canvas-2:        #0b0c10;
    --tint-user:       rgba(10, 132, 255, 0.16);
  }
}

/* ---- Type: the platform font, tracking tuned per size ------------------- */
html, body, [class*="css"], .stApp, [data-testid="stAppViewContainer"] {
  font-family: -apple-system, BlinkMacSystemFont, "SF Pro Text", "Segoe UI",
               system-ui, "Helvetica Neue", sans-serif;
  -webkit-font-smoothing: antialiased;
  color: var(--ink);
}
.stApp h1 { font-weight: 700; letter-spacing: -0.028em; line-height: 1.08; }
.stApp h2 { font-weight: 650; letter-spacing: -0.018em; line-height: 1.15; }
.stApp h3 { font-weight: 600; letter-spacing: -0.012em; }
.stApp p, .stApp li { letter-spacing: 0; line-height: 1.55; }

/* ---- The ground the glass sits on --------------------------------------- */
/* Static, not animated: a slow looping background is a reduced-motion hazard. */
[data-testid="stAppViewContainer"] {
  background:
    radial-gradient(1100px 720px at 12% -8%,  rgba(120, 170, 255, 0.30), transparent 60%),
    radial-gradient(900px 640px at 92% 4%,   rgba(190, 140, 255, 0.24), transparent 62%),
    radial-gradient(900px 700px at 50% 108%, rgba(120, 220, 210, 0.20), transparent 60%),
    linear-gradient(168deg, var(--canvas-1), var(--canvas-2));
  background-attachment: fixed;
}

/* Scroll edge effect: the header floats over content instead of dividing it. */
[data-testid="stHeader"] {
  background: transparent;
  backdrop-filter: blur(14px) saturate(150%);
  -webkit-backdrop-filter: blur(14px) saturate(150%);
}

/* ---- Sidebar: the heaviest material (structural region) ------------------ */
[data-testid="stSidebar"] > div:first-child {
  background: var(--glass-bg-strong);
  backdrop-filter: blur(32px) saturate(180%);
  -webkit-backdrop-filter: blur(32px) saturate(180%);
  border-right: 1px solid var(--glass-hairline);
  box-shadow: var(--glass-shadow);
}
[data-testid="stSidebar"] hr { border-color: var(--glass-hairline); opacity: 1; }

/* ---- Chat cards: lighter material, floating on the gradient -------------- */
[data-testid="stChatMessage"] {
  background: var(--glass-bg);
  backdrop-filter: blur(24px) saturate(170%);
  -webkit-backdrop-filter: blur(24px) saturate(170%);
  border: 1px solid var(--glass-hairline);
  border-top-color: var(--glass-edge);   /* bright top edge = light on the material */
  border-radius: var(--radius);
  box-shadow: var(--glass-shadow);
  padding: 1rem 1.15rem;
  margin-bottom: 0.85rem;
}
/* The user's own turn carries the accent tint so the two speakers read apart. */
[data-testid="stChatMessage"]:has([data-testid="stChatMessageAvatarUser"]) {
  background: linear-gradient(var(--tint-user), var(--tint-user)), var(--glass-bg);
}

/* Scorecards and lookup output are dense data — put them on a solid-ish layer
   rather than a second sheet of translucency (vibrancy rule). */
[data-testid="stChatMessage"] pre,
[data-testid="stChatMessage"] code,
[data-testid="stChatMessage"] table {
  background: var(--glass-bg-strong);
  border: 1px solid var(--glass-hairline);
  border-radius: 12px;
}
[data-testid="stChatMessage"] table { border-collapse: separate; border-spacing: 0; }
[data-testid="stChatMessage"] th, [data-testid="stChatMessage"] td {
  border-color: var(--glass-hairline) !important;
}

/* Captions (tool badges, provider info): vibrancy wants a touch more weight
   and tracking than flat gray, so they stay legible over a blurred surface. */
[data-testid="stCaptionContainer"], .stCaption, [data-testid="stChatMessage"] small {
  color: var(--ink-dim);
  font-weight: 450;
  letter-spacing: 0.005em;
}

/* ---- Buttons: lightest material, feedback on press ---------------------- */
.stButton > button {
  background: var(--glass-bg);
  backdrop-filter: blur(18px) saturate(170%);
  -webkit-backdrop-filter: blur(18px) saturate(170%);
  border: 1px solid var(--glass-hairline);
  border-top-color: var(--glass-edge);
  border-radius: 12px;
  color: var(--ink);
  font-weight: 500;
  letter-spacing: -0.003em;
  text-align: left;
  box-shadow: var(--glass-shadow);
  transition: background 140ms ease-out, box-shadow 140ms ease-out,
              transform 100ms ease-out;
}
.stButton > button:hover {
  background: var(--glass-bg-strong);
  box-shadow: var(--glass-shadow-lg);
  border-color: var(--glass-edge);
  color: var(--ink);
}
/* Respond on pointer-down, not on release. */
.stButton > button:active { transform: scale(0.97); transition-duration: 100ms; }
.stButton > button:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }
.stButton > button[data-testid="stBaseButton-primary"] {
  background: var(--accent);
  color: #fff;
  border-color: transparent;
}
.stButton > button[data-testid="stBaseButton-primary"]:hover {
  background: color-mix(in srgb, var(--accent) 88%, #000);
  color: #fff;
}

/* ---- Chat input: a floating capsule, content scrolls under -------------- */
[data-testid="stChatInput"] {
  background: var(--glass-bg-strong);
  backdrop-filter: blur(30px) saturate(180%);
  -webkit-backdrop-filter: blur(30px) saturate(180%);
  border: 1px solid var(--glass-hairline);
  border-top-color: var(--glass-edge);
  border-radius: 22px;
  box-shadow: var(--glass-shadow-lg);
}
[data-testid="stBottomBlockContainer"] { background: transparent; }

/* ---- Notices (the "conversation summarized" note) ---------------------- */
[data-testid="stAlert"] {
  background: var(--glass-bg);
  backdrop-filter: blur(22px) saturate(170%);
  -webkit-backdrop-filter: blur(22px) saturate(170%);
  border: 1px solid var(--glass-hairline);
  border-top-color: var(--glass-edge);
  border-radius: 14px;
  box-shadow: var(--glass-shadow);
}

/* ---- Landing page: hero type + feature row ------------------------------ */
.landing-h1 {
  font-size: 3rem;
  font-weight: 700;
  letter-spacing: -0.03em;
  line-height: 1.05;
  margin: 0.5rem 0 1rem;
  color: var(--ink);
}
.landing-h1 .accent { color: var(--accent); }
.landing-lede {
  font-size: 1.15rem;
  color: var(--ink-dim);
  max-width: 38rem;
  margin: 0 0 1.5rem;
}
.landing-feature h4 { margin: 0 0 0.3rem; font-size: 1rem; letter-spacing: -0.008em; }
.landing-feature p  { margin: 0; font-size: 0.92rem; color: var(--ink-dim); line-height: 1.5; }

/* ---- Accessibility fallbacks ------------------------------------------- */
/* Reduced transparency: frost the glass solid, drop the blur. */
@media (prefers-reduced-transparency: reduce) {
  :root {
    --glass-bg:        #ffffff;
    --glass-bg-strong: #ffffff;
    --tint-user:       rgba(0, 113, 227, 0.08);
  }
  @media (prefers-color-scheme: dark) {
    :root { --glass-bg: #1c1e24; --glass-bg-strong: #16181d; }
  }
  [data-testid="stSidebar"] > div:first-child,
  [data-testid="stChatMessage"], [data-testid="stChatInput"],
  [data-testid="stAlert"], [data-testid="stHeader"], .stButton > button {
    backdrop-filter: none;
    -webkit-backdrop-filter: none;
  }
  [data-testid="stAppViewContainer"] { background: var(--canvas-1); }
}
/* More contrast: near-solid surfaces with a defined border. */
@media (prefers-contrast: more) {
  :root { --glass-bg: #ffffff; --glass-bg-strong: #ffffff; --glass-hairline: rgba(0,0,0,0.55); }
  @media (prefers-color-scheme: dark) {
    :root { --glass-bg: #000; --glass-bg-strong: #000; --glass-hairline: rgba(255,255,255,0.6); }
  }
}
/* Reduced motion: keep the material, drop the movement. */
@media (prefers-reduced-motion: reduce) {
  .stButton > button { transition: background 140ms ease-out; }
  .stButton > button:active { transform: none; }
}
</style>
"""

# --------------------------------------------------------------------------- #
# Graph (built once, cached across reruns)
# --------------------------------------------------------------------------- #

@st.cache_resource(show_spinner="Starting the agent…")
def get_graph():
    """Compile the supervisor graph once. Importing it builds the LLM client, so
    a provider/endpoint problem surfaces here as one clear error."""
    from src.agent.graph import build_graph

    return build_graph()


# --------------------------------------------------------------------------- #
# Session state
# --------------------------------------------------------------------------- #

def _fresh_agent_state() -> dict:
    return {
        "messages": [],
        "call_records": [],
        "qa_scores": [],
        "role": "Customer",
        "next_tool": "",
        "pending_tools": [],
        "tool_trace": [],
    }


def _init_state() -> None:
    if "agent_state" not in st.session_state:
        st.session_state.agent_state = _fresh_agent_state()
    if "display" not in st.session_state:
        # Rendered transcript, kept separate from the agent's (summarized) memory
        # so the full conversation stays visible. Entries:
        #   {"role": "user"|"assistant"|"note", "content": str, "trace": list}
        st.session_state.display = []
    if "pending_input" not in st.session_state:
        st.session_state.pending_input = None
    if "user" not in st.session_state:
        st.session_state.user = None        # signed-in email; None → show the login form
    if "login_requested" not in st.session_state:
        st.session_state.login_requested = False  # landing page by default; True → sign-in form
    if "reset_step" not in st.session_state:
        st.session_state.reset_step = None      # None | "email" | "password" (forgot-password flow)
    if "reset_account" not in st.session_state:
        st.session_state.reset_account = ""
    if "role" not in st.session_state:
        st.session_state.role = "Customer"  # fail closed; set by the login form
    if "running" not in st.session_state:
        st.session_state.running = False
    if "job" not in st.session_state:
        st.session_state.job = None


def _reset_conversation() -> None:
    st.session_state.agent_state = _fresh_agent_state()
    st.session_state.display = []
    st.session_state.pending_input = None
    st.session_state.running = False
    st.session_state.job = None


def _sign_out() -> None:
    _reset_conversation()
    st.session_state.user = None
    st.session_state.role = "Customer"
    st.session_state.login_requested = False  # back to the landing page
    st.session_state.reset_step = None


def _render_landing() -> None:
    """Front door: what the agent does, then the two ways in. A customer needs no
    account; the supervisor button leads to the sign-in form."""
    st.markdown(
        '<h1 class="landing-h1">Ask about your order.<br>'
        '<span class="accent">Score the call.</span></h1>'
        '<p class="landing-lede">One agent over the company\'s policies, call records and '
        "orders. Customers get answers on deliveries, returns and refunds; supervisors look "
        "up calls and score them against the QA rubric.</p>",
        unsafe_allow_html=True,
    )
    st.subheader("Get started")
    left, right = st.columns(2)
    if left.button("🙋 Continue as a customer", key="landing_customer", use_container_width=True):
        st.session_state.user = "guest"
        st.session_state.role = "Customer"
        _reset_conversation()
        st.rerun()
    if right.button(
        "🛠️ Continue as a supervisor", key="landing_supervisor", type="primary", use_container_width=True
    ):
        st.session_state.login_requested = True
        st.rerun()
    st.caption("Supervisors sign in with a QA account. Customers need no account.")
    st.divider()
    for col, (icon, title, blurb) in zip(st.columns(3), LANDING_FEATURES):
        col.markdown(
            f'<div class="landing-feature"><h4>{icon} {title}</h4><p>{blurb}</p></div>',
            unsafe_allow_html=True,
        )


def _render_login() -> None:
    """Supervisor sign-in. Only an account in ``data/supervisors.csv`` gets in;
    wrong credentials show an error and keep the form. Customers never see
    this — they take the other button on the landing page."""
    st.title("🔐 Sign in")
    if st.session_state.reset_step:
        _render_reset()
        return
    st.caption("Supervisors sign in with their QA account.")
    if st.session_state.pop("reset_done", False):
        st.success("Password updated — sign in with your new password.")
    with st.form("login"):
        email = st.text_input("Email", key="login_email")
        password = st.text_input("Password", type="password", key="login_password")
        if st.form_submit_button("Sign in", key="login_submit", type="primary", use_container_width=True):
            if resolve_role(email, password) != "Supervisor":
                st.error("Invalid email or password.")
            else:
                st.session_state.user = email.strip().lower()
                st.session_state.role = "Supervisor"
                st.session_state.login_requested = False
                _reset_conversation()
                st.rerun()
    left, right = st.columns(2)
    if left.button("← Back", key="login_back"):
        st.session_state.login_requested = False
        st.rerun()
    if right.button("Forgot password?", key="login_forgot"):
        st.session_state.reset_step = "email"
        st.rerun()


def _render_reset() -> None:
    """Two-step password reset: confirm the email is in the sheet, then write a
    new password to it. Email-only — no verification code (see auth.py)."""
    st.caption("Reset your supervisor password.")
    if st.session_state.reset_step == "email":
        with st.form("reset_email_form"):
            email = st.text_input("Email", key="reset_email")
            if st.form_submit_button("Continue", key="reset_continue", type="primary", use_container_width=True):
                if not email_exists(email):
                    st.error("No supervisor account with that email.")
                else:
                    st.session_state.reset_account = email.strip().lower()
                    st.session_state.reset_step = "password"
                    st.rerun()
    else:
        st.caption(f"Account: **{st.session_state.reset_account}**")
        with st.form("reset_password_form"):
            new = st.text_input("New password", type="password", key="reset_password")
            confirm = st.text_input("Confirm new password", type="password", key="reset_confirm")
            if st.form_submit_button("Set password", key="reset_submit", type="primary", use_container_width=True):
                if not new:
                    st.error("Enter a new password.")
                elif new != confirm:
                    st.error("Passwords do not match.")
                elif not set_password(st.session_state.reset_account, new):
                    st.error("No supervisor account with that email.")
                else:
                    st.session_state.reset_step = None
                    st.session_state.reset_done = True
                    st.rerun()
    if st.button("← Back", key="reset_back"):
        st.session_state.reset_step = None
        st.rerun()


# --------------------------------------------------------------------------- #
# Memory helpers
# --------------------------------------------------------------------------- #

def _user_turn_count(messages: list) -> int:
    return sum(1 for m in messages if isinstance(m, HumanMessage))


def _maybe_summarize(agent_state: dict) -> bool:
    """If the conversation is long, replace older messages with one summary
    message (keeping the last few verbatim). Returns True when it summarized."""
    from src.agent.graph import summarize_history

    messages = agent_state["messages"]
    if _user_turn_count(messages) < SUMMARY_TURN_THRESHOLD:
        return False
    if len(messages) <= KEEP_RECENT_MESSAGES:
        return False

    older = messages[:-KEEP_RECENT_MESSAGES]
    recent = messages[-KEEP_RECENT_MESSAGES:]
    summary = summarize_history(older)
    summary_msg = SystemMessage(content="Summary of earlier conversation:\n" + summary)
    agent_state["messages"] = [summary_msg] + recent
    return True


# --------------------------------------------------------------------------- #
# One turn — run on a background thread so a Stop button stays clickable
# --------------------------------------------------------------------------- #

def _start_turn(graph, user_input: str) -> None:
    """Kick off one turn on a daemon thread. The graph runs in the background
    while the main script polls (and shows a Stop button); the worker writes only
    into a plain dict (result_box), never into st.session_state."""
    agent_state = st.session_state.agent_state
    # Append the user message and clear the previous turn's trace so the returned
    # trace is exactly this turn's; stamp the selected role for tool gating.
    agent_state["messages"] = agent_state["messages"] + [HumanMessage(content=user_input)]
    agent_state["tool_trace"] = []
    agent_state["role"] = st.session_state.get("role", "Customer")

    # This turn's own Stop flag, handed to the graph via config — never a module
    # global, so another browser session's Stop can't cancel this run.
    cancel = threading.Event()
    result_box: dict = {"done": False}

    def _run() -> None:
        try:
            result_box["state"] = graph.invoke(
                agent_state, config={"configurable": {"cancel": cancel}}
            )
        except Exception as exc:  # noqa: BLE001 - surface as a message, not a crash
            result_box["error"] = str(exc)
        finally:
            result_box["done"] = True

    thread = threading.Thread(target=_run, daemon=True)
    add_script_run_ctx(thread)
    thread.start()
    st.session_state.job = {"thread": thread, "result_box": result_box, "cancel": cancel}
    st.session_state.running = True


def _finalize_turn() -> None:
    """Called once the worker is done: store the new state, render the assistant
    entry (+ any summary note) into the display transcript, clear running."""
    box = st.session_state.job["result_box"]

    if "error" in box:
        answer, trace = (
            f"Sorry — something went wrong handling that request ({box['error']}).",
            [],
        )
    else:
        from src.agent.graph import turn_replies

        new_state = box.get("state") or st.session_state.agent_state
        st.session_state.agent_state = new_state
        trace = new_state.get("tool_trace", [])
        # Every reply this turn produced (a chained lookup→score turn has two),
        # not just the last message.
        answer = "\n\n".join(turn_replies(new_state.get("messages", []))) or NO_ROUTE_REPLY

    st.session_state.display.append({"role": "assistant", "content": answer, "trace": trace})

    if _maybe_summarize(st.session_state.agent_state):
        st.session_state.display.append(
            {"role": "note", "content": "🗂️ Earlier conversation summarized to manage memory."}
        )

    st.session_state.running = False
    st.session_state.job = None


# --------------------------------------------------------------------------- #
# Rendering
# --------------------------------------------------------------------------- #

def _render_badges(trace: list) -> None:
    if not trace:
        return
    tools = " → ".join(TOOL_LABELS.get(t.get("tool"), t.get("tool", "?")) for t in trace)
    st.caption(f"🔧 Tool(s) used: {tools}")
    if any(t.get("llm_degraded") for t in trace):
        st.caption("⚠️ Lookup used keyword-only matching (the AI extraction step was unavailable).")


def _render_entry(entry: dict) -> None:
    if entry["role"] == "note":
        st.info(entry["content"])
        return
    with st.chat_message(entry["role"]):
        # Tool output is line-oriented (one call/order per line, indented
        # Shipment:/Return: sub-lines). Markdown folds single newlines into one
        # paragraph, so force a hard break on each; tables/lists are unaffected.
        st.markdown(re.sub(r"(?<!  )\n", "  \n", entry["content"]))
        if entry["role"] == "assistant":
            _render_badges(entry.get("trace", []))


# --------------------------------------------------------------------------- #
# App
# --------------------------------------------------------------------------- #

def main() -> None:
    # Title/header follow the signed-in role. Reading session_state before
    # set_page_config is allowed (it's not a page command).
    user = st.session_state.get("user")
    role = st.session_state.get("role", "Customer")
    if user:
        ui = ROLE_UI.get(role, ROLE_UI["Customer"])
    elif st.session_state.get("login_requested"):
        ui = {"icon": "🔐", "title": "Sign in", "caption": ""}
    else:
        ui = {"icon": "📞", "title": "Call Center Agent", "caption": ""}
    st.set_page_config(page_title=ui["title"], page_icon=ui["icon"], layout="centered")
    st.markdown(GLASS_CSS, unsafe_allow_html=True)

    _init_state()
    if not st.session_state.user:
        if st.session_state.login_requested:
            _render_login()
        else:
            _render_landing()
        st.stop()

    st.title(f"{ui['icon']} {ui['title']}")
    st.caption(ui["caption"])

    # Fail clearly if the agent (and its LLM client) can't be built.
    try:
        graph = get_graph()
    except Exception as exc:  # noqa: BLE001
        st.error(
            "Could not start the agent — the configured LLM provider is unavailable.\n\n"
            f"{exc}\n\nStart the provider (e.g. LM Studio with a model loaded) or switch "
            "`active_provider` in `config.json`, then reload."
        )
        st.stop()

    # --- Sidebar -----------------------------------------------------------
    with st.sidebar:
        st.subheader("Signed in")
        st.caption(
            f"**{st.session_state.user}**  \n"
            + (
                "🛠️ **Supervisor** — policies, call lookup, order lookup, QA scoring"
                if role == "Supervisor"
                else "🙋 **Customer** — policy questions and order status"
            )
        )
        if st.button("Sign out", key="sign_out", use_container_width=True):
            _sign_out()
            st.rerun()
        st.divider()

        st.header("Try a sample")
        for query in SAMPLE_QUERIES_BY_ROLE[role]:
            if st.button(query, use_container_width=True):
                st.session_state.pending_input = query
        st.divider()
        provider = CONFIG["active_provider"]
        model = CONFIG["providers"][provider].get("model", "?")
        st.caption(f"**Provider:** {provider}\n\n**Model:** {model}")
        st.caption(
            f"Conversation memory is summarized after {SUMMARY_TURN_THRESHOLD} turns "
            "to stay bounded."
        )
        st.divider()
        if st.button("🗑️ Clear conversation", use_container_width=True):
            _reset_conversation()
            st.rerun()

    # --- Prior transcript --------------------------------------------------
    for entry in st.session_state.display:
        _render_entry(entry)

    # --- A turn is running: show a Stop button and poll the worker ---------
    if st.session_state.running:
        st.session_state.pending_input = None  # ignore sample clicks mid-turn
        box = st.session_state.job["result_box"]
        with st.chat_message("assistant"):
            if box.get("done"):
                _finalize_turn()
                st.rerun()  # re-render with the finished assistant entry
            else:
                st.caption("💭 Thinking…")
                if st.button("⏹ Stop generating", type="primary", use_container_width=True):
                    st.session_state.job["cancel"].set()
                    st.caption("Stopping after the current step…")
        if not box.get("done"):
            time.sleep(POLL_SECONDS)
            st.rerun()
        return

    # --- New input (typed box or a sidebar sample) -------------------------
    typed = st.chat_input("Type your request…")
    user_input = typed or st.session_state.pending_input
    st.session_state.pending_input = None
    if not user_input:
        return

    # Record + render the user turn, then start the background worker and rerun
    # into the polling branch above.
    st.session_state.display.append({"role": "user", "content": user_input})
    with st.chat_message("user"):
        st.markdown(user_input)
    _start_turn(graph, user_input)
    st.rerun()


# Streamlit executes this module top-to-bottom on every rerun (not via __main__),
# so the entry point is a bare call here.
main()
