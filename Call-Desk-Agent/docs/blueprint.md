# Call Center AI Operations Assistant — Complete Project Blueprint

> **Document purpose:** This is a teaching document written for an LLM acting as a coding guide.
> It contains everything needed to navigate a learner through building this project from scratch —
> including the learner's background, all design decisions already made, the reasoning behind them,
> the full architecture, synthetic data specs, code structure, and step-by-step build order.
> Do not improvise. Follow this document as the source of truth.

---

## 1. Who You Are Teaching

| Property | Detail |
|---|---|
| Python level | Comfortable — has built projects, used APIs, file handling |
| LangChain | Used before — understands chains, prompts, LLM wrappers |
| LangGraph | Never used — needs explanation before every new concept |
| LLM APIs | Has used OpenAI/Anthropic style APIs before |
| Streamlit | Used before |
| API access | Will use **Google Gemini free tier** (aistudio.google.com) |
| Background | Working professional, not a full-time developer |
| Goal | IIT Patna GenAI certification — Project 3 (Agentic AI) |

**Teaching style rules:**
- Never dump all code at once. Build one file at a time.
- Before every new LangGraph concept, give a 2-sentence plain-English explanation.
- After each file is built, tell the learner exactly what to run to verify it works.
- Always explain *why* a design decision was made, not just *what* to do.
- If the learner asks why, answer with reasoning not just reassurance.

---

## 2. What This Project Is

A **conversational AI agent** for call center operations. A user types natural language requests into a Streamlit chat interface. The AI agent reads the request, decides which tool to use, runs it, and returns a structured answer.

This is not a chatbot. It does not just answer questions from memory. It actively calls functions (tools) to fetch real data and perform real analysis.

### Why this project was chosen over alternatives

The learner originally proposed a standalone call quality scoring tool (audio → transcription → score). That project was rejected as the primary submission because:

1. It only demonstrates: LLM API calls, Whisper, basic prompt engineering.
2. It does NOT demonstrate: LangGraph, tool calling, agentic routing, state management — all of which are explicitly graded.
3. It is harder to build (audio pipeline) but scores lower on the rubric.

The chosen project (Project 3 — Agentic AI) absorbs the original QA scoring idea as **Tool 3** inside a larger agentic system. The learner keeps their original idea but gains coverage of every graded concept.

---

## 3. Evaluation Criteria Being Targeted

From the official IIT Patna assessment document:

| Criterion | How this project satisfies it |
|---|---|
| Functional completeness | All 3 tools work, Streamlit UI runs, multi-turn conversation works |
| GenAI implementation | LLM used for routing decisions, QA scoring, policy answer generation |
| Architecture | Modular — each tool is its own file, graph is separate, UI is separate |
| Technical depth | LangGraph with state, conditional routing, tool calling — not just API calls |
| Code quality | Clean functions, typed state, error handling in every tool |
| Error handling | Every tool has try/except, agent handles unknown requests gracefully |
| User experience | Streamlit chat with history, tool result visibility |
| Documentation | README with architecture diagram, setup steps, sample I/O |
| Engineering practices | `.env` for API keys, `requirements.txt`, logging, Git |
| Demonstration | Learner must explain the graph routing and state management |

---

## 4. Tech Stack

| Component | Technology | Why |
|---|---|---|
| LLM | Google Gemini (current free-tier Flash model — e.g. `gemini-3.5-flash` as of Aug 2026) | Free tier, no credit card, works with LangChain. **Gemini 1.5 is fully shut down (404s on every call) — Google retires model IDs fast, so check the live list at aistudio.google.com before hardcoding a version, not just at write-time.** |
| Agent framework | LangGraph | Explicitly required by Project 3 rubric |
| LangChain | LangChain core + Google integration | LangGraph is built on LangChain |
| RAG / vector store | FAISS + HuggingFace embeddings | Both fully local, no API cost |
| Embeddings | `sentence-transformers/all-MiniLM-L6-v2` | Free, runs locally, good quality |
| Data storage | CSV (calls) + TXT files (policies) | Simple, no database setup needed |
| UI | Streamlit | Required by rubric, learner already knows it |
| Language | Python 3.10+ | Required by rubric |
| Env management | `python-dotenv` | API key safety |

---

## 5. The Three Tools — Detailed Specification

### Tool 1: Policy Search (RAG)

**What it does:** Searches a local folder of call center policy documents and returns the relevant answer.

**When the agent uses it:** User asks anything about rules, policies, procedures, SLAs.

**Examples of triggering requests:**
- "What is the replacement policy?"
- "How long does a repair take?"
- "What are the logistics guidelines for returns?"

**Implementation:**
- Load all `.txt` files from `data/policies/`
- Chunk them using LangChain `RecursiveCharacterTextSplitter`
- Embed using HuggingFace `all-MiniLM-L6-v2`
- Store in FAISS vector store
- On query: retrieve top 3 chunks, pass to Gemini with a prompt to answer from context only
- Return the answer as a string

**File:** `src/tools/policy_search.py`

**Key function signature:**
```python
def search_policy(query: str) -> str:
    """Search policy documents and return relevant answer."""
```

---

### Tool 2: Call Record Lookup

**What it does:** Queries `data/calls.csv` to fetch call records by agent name, call ID, date, or call type.

**When the agent uses it:** User asks to fetch, find, or retrieve call records.

**Examples of triggering requests:**
- "Fetch Rahul's last 5 calls"
- "Show me call #1042"
- "Get all repair calls from this week"

**Implementation:**
- Load `calls.csv` into a pandas DataFrame
- Parse the natural language query using Gemini to extract filter parameters (agent name, call ID, date range, call type, limit)
- Apply filters to DataFrame
- Return matching records as a formatted string + store in agent state

**File:** `src/tools/call_lookup.py`

**Key function signature:**
```python
def lookup_calls(query: str) -> str:
    """Look up call records based on natural language query."""
```

---

### Tool 3: QA Scorer

**What it does:** Takes a call transcript and scores it against a fixed rubric of 8 parameters. Returns pass/fail per parameter and an overall score.

**When the agent uses it:** User asks to score, evaluate, or assess a call or agent.

**Examples of triggering requests:**
- "Score call #1042"
- "Score Rahul's last 5 calls"
- "Evaluate this transcript"

**Note:** Often chains with Tool 2 — agent first fetches transcript via Tool 2, then passes it to Tool 3.

**Scoring rubric (8 parameters, all binary pass/fail):**

| # | Parameter | What to detect in transcript |
|---|---|---|
| 1 | Greeting | Agent said hello/good morning/hi in first 3 turns |
| 2 | Identity verification | Agent asked for name, account number, or order ID |
| 3 | Problem acknowledgement | Agent acknowledged the customer's issue explicitly |
| 4 | Correct call classification | Agent identified call type (replacement/repair/logistics/device/escalation — matches the 5 `call_type` values in `calls.csv`) |
| 5 | Solution offered | Agent offered a resolution or next step |
| 6 | Policy compliance | Agent's response matches the relevant policy |
| 7 | Professional tone | No rude, dismissive, or unprofessional language |
| 8 | Proper closure | Agent summarised and closed the call politely |

**Scoring logic:**
- Each parameter: 1 point if PASS, 0 if FAIL
- Overall score: X/8
- Overall result: PASS if score >= 6, FAIL if score < 6

**Implementation:**
- Accept a transcript string
- **Before scoring, call `search_policy()` (Tool 1) with the call's likely topic to retrieve the actual policy text.** Without this, parameter 6 ("Policy compliance") has nothing to check against — the LLM would be judging compliance from its own training data instead of your RAG documents, which quietly breaks the "answers only from retrieved context" guarantee that's the whole point of building RAG in the first place.
- Send transcript + retrieved policy text to Gemini with a structured prompt asking it to evaluate each parameter
- Ask Gemini to respond in JSON format
- Parse JSON into a Python dict
- Calculate overall score
- Return formatted report as string

**File:** `src/tools/qa_scorer.py`

**Key function signature:**
```python
def score_call(transcript: str, call_id: str = "", policy_context: str = "") -> str:
    """Score a call transcript against the QA rubric.
    policy_context: retrieved policy text from search_policy(), used to judge
    parameter 6 (policy_compliance) against real documents instead of guessing."""
```

---

## 6. The LangGraph Architecture

### What LangGraph is (explain this to the learner before any code)

LangGraph is a library for building AI agents as a **graph of nodes and edges**.

- A **node** is a Python function that does one thing (call the LLM, run a tool, format output).
- An **edge** is a connection between nodes — it determines what runs next.
- A **conditional edge** checks a condition (like "which tool did the agent decide to use?") and routes to different nodes based on the answer.
- The **state** is a Python dictionary that every node can read from and write to. It travels through the entire graph, accumulating information.

Think of it as a flowchart where the boxes are Python functions and the arrows are edges.

### The State Object

```python
from typing import TypedDict, Annotated
from langgraph.graph.message import add_messages

class AgentState(TypedDict):
    messages: Annotated[list, add_messages]  # full conversation history
    call_records: list        # results from Tool 2
    qa_scores: list           # results from Tool 3
    agent_name: str           # agent name if mentioned by user
    next_tool: str            # the tool to run right now: "policy", "lookup", "score", "end"
    pending_tools: list       # remaining tools queued for this turn, e.g. ["score"]
```

**Why `add_messages`?** LangGraph uses this special annotation to automatically append new messages to the list rather than replacing it. The learner must use this exact pattern.

**Why `pending_tools` exists — read this before building the graph.** The original single-hop design (supervisor picks one tool, that tool runs, graph ends) cannot handle "Score Rahul's last 5 calls." That request needs Tool 2 (fetch the calls) to run *before* Tool 3 (score them) — two tools, one user turn. `pending_tools` is a small queue: the supervisor can output more than one tool word, the first becomes `next_tool`, the rest sit in `pending_tools`. After `lookup_node` finishes, a conditional edge checks whether `pending_tools` still has something in it and routes to `scorer_node` if so, instead of ending the turn. Without this field, the "multi-step agent chaining" demo in Section 15 has no path to actually happen.

### The Graph Nodes

```
Node 1: supervisor        — LLM reads user message, decides next_tool
Node 2: policy_node       — calls Tool 1, writes result to messages
Node 3: lookup_node       — calls Tool 2, writes result to messages + call_records
Node 4: scorer_node       — calls Tool 3, writes result to messages + qa_scores
Node 5: END               — conversation turn is complete
```

### The Graph Edges

```
START → supervisor
supervisor → [conditional edge on next_tool] →
    if next_tool == "policy"  → policy_node → END
    if next_tool == "lookup"  → lookup_node → [conditional edge on pending_tools] →
                                      if pending_tools has "score" → scorer_node → END
                                      else → END
    if next_tool == "score"   → scorer_node → END
    if next_tool == "end"     → END
```

**This is the chaining path.** "Score Rahul's last 5 calls" is really two tools in sequence: fetch, then score. The supervisor sets `next_tool = "lookup"` and `pending_tools = ["score"]`. `lookup_node` runs, populates `state["call_records"]`, and instead of always going to `END`, a second conditional edge checks `pending_tools`: if it's non-empty, route to `scorer_node`, which reads the transcripts straight out of `call_records` rather than asking the user for one. This is the only way "Score call #1042" (single tool) and "Score Rahul's last 5 calls" (two tools chained) can both work through the same graph.

### The Supervisor Node (most important)

This is the brain. It receives the user message and outputs which tool to use.

The supervisor uses a prompt like this:

```
You are a call center operations assistant.
Based on the user's message, decide which tool(s) to use, in order.

Tools available:
- "policy": user is asking about rules, policies, procedures, SLAs
- "lookup": user wants to fetch or retrieve call records
- "score": user wants to evaluate or score a call
- "end": user is saying thanks, goodbye, or asking something you cannot help with

If the user wants records fetched AND scored in the same request
(e.g. "score Rahul's last 5 calls"), respond with both, comma-separated,
in the order they must run: lookup,score

User message: {user_message}

Respond with ONLY the tool word(s), comma-separated, nothing else.
Examples: "policy"  |  "lookup"  |  "lookup,score"  |  "end"
```

**File:** `src/agent/graph.py`

---

## 7. Synthetic Data Specification

The learner has no real call center data. All data must be generated. This section specifies exactly what to create.

### 7a. Policy Documents (data/policies/)

Create 5 plain `.txt` files. Content should be realistic but fictional.

**replacement_policy.txt**
- Replacement eligibility: product must be within 90 days of purchase
- Customer must provide proof of purchase
- Replacement dispatched within 3-5 business days
- Only one replacement per order allowed
- Damaged due to misuse is not eligible

**repair_sla.txt**
- Repair requests acknowledged within 24 hours
- Standard repair SLA: 7 business days
- Complex repairs: up to 14 business days
- Customer receives SMS update at each stage
- If repair exceeds SLA, customer is entitled to a temporary replacement

**logistics_guidelines.txt**
- All returns must use the prepaid return label sent via email
- Items must be packed in original packaging where possible
- Return tracking number must be shared with customer
- Refund processed within 5-7 business days of receiving the item
- Lost-in-transit claims must be raised within 30 days

**device_support.txt**
- Device setup support available Mon-Sat 9am-6pm
- Remote support via screen share available for premium customers
- Basic troubleshooting guide sent via email on first contact
- Hardware issues beyond software support escalated to repair team

**escalation_policy.txt**
- Escalation triggered when: issue unresolved after 2 contacts, customer requests manager, SLA breached
- Escalated cases assigned to senior agent within 2 hours
- Customer notified of escalation via email and SMS
- Escalation team SLA: resolution within 24 hours

---

### 7b. Calls CSV (data/calls.csv)

**Columns:**
```
call_id, date, agent_name, call_type, direction, duration_mins, transcript, channel
```

**Column definitions:**
- `call_id`: format CALL-1001 to CALL-1030
- `date`: dates within the last 30 days
- `agent_name`: use 5 agent names — Rahul, Priya, Amit, Sara, James
- `call_type`: one of — replacement, repair, logistics, device, escalation
- `direction`: inbound or outbound
- `duration_mins`: integer between 3 and 18
- `transcript`: a realistic 8-12 line conversation between Agent and Customer
- `channel`: one of — phone, chat, email

**Create 30 rows total.** Each agent should appear 5-6 times. Call types should be mixed.

**Transcript format example:**
```
Agent: Good morning, thank you for calling support. How can I help you today?
Customer: Hi, I received a damaged product and I need a replacement.
Agent: I'm sorry to hear that. Can I have your order number please?
Customer: Yes it's ORD-8823.
Agent: Thank you. I can see your order. This is within our 90-day replacement window. I'll process a replacement for you right away.
Customer: How long will it take?
Agent: You'll receive it within 3-5 business days. Is there anything else I can help with?
Customer: No that's all, thank you.
Agent: Thank you for calling. Have a great day.
```

**Important:** Create a mix of GOOD calls (agent follows all 8 rubric parameters) and BAD calls (agent skips greeting, doesn't verify identity, or closes poorly). Roughly 20 good, 10 bad. This ensures the QA scorer produces interesting results.

---

## 8. Complete File Structure

```
call-center-agent/
│
├── data/
│   ├── policies/
│   │   ├── replacement_policy.txt
│   │   ├── repair_sla.txt
│   │   ├── logistics_guidelines.txt
│   │   ├── device_support.txt
│   │   └── escalation_policy.txt
│   └── calls.csv
│
├── src/
│   ├── __init__.py
│   ├── tools/
│   │   ├── __init__.py
│   │   ├── policy_search.py
│   │   ├── call_lookup.py
│   │   └── qa_scorer.py
│   │
│   ├── agent/
│   │   ├── __init__.py
│   │   ├── state.py
│   │   └── graph.py
│   │
│   └── ui/
│       └── app.py
│
├── .env                  ← NEVER commit this
├── .env.example          ← commit this (no real keys)
├── .gitignore
├── requirements.txt
└── README.md
```

**Note:** `src/__init__.py` is included even though `src/tools/` and `src/agent/` already have their own `__init__.py`. Python 3 *can* resolve `src` as an implicit namespace package without it, but that resolution depends on your working directory and how the interpreter was invoked — Streamlit's import path isn't always the same as a plain `python` run. One empty file removes that ambiguity; skipping it is how learners get an unexplained `ModuleNotFoundError` on Step 7 or 8 after everything worked fine in isolation.

### 8a. Scaffold script

Run this once to generate the empty structure above — don't create these folders and files by hand.

```python
#!/usr/bin/env python3
"""Create the empty folder and file structure for the call-center agent project."""

from __future__ import annotations

import argparse
from pathlib import Path


PROJECT_FILES = [
    "data/policies/replacement_policy.txt",
    "data/policies/repair_sla.txt",
    "data/policies/logistics_guidelines.txt",
    "data/policies/device_support.txt",
    "data/policies/escalation_policy.txt",
    "data/calls.csv",
    "src/__init__.py",
    "src/tools/__init__.py",
    "src/tools/policy_search.py",
    "src/tools/call_lookup.py",
    "src/tools/qa_scorer.py",
    "src/agent/__init__.py",
    "src/agent/state.py",
    "src/agent/graph.py",
    "src/ui/app.py",
    ".env",
    ".env.example",
    ".gitignore",
    "requirements.txt",
    "README.md",
]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "target",
        nargs="?",
        default="call-center-agent",
        help="Directory in which to create the project structure",
    )
    args = parser.parse_args()
    root = Path(args.target).expanduser().resolve()

    for relative_path in PROJECT_FILES:
        file_path = root / relative_path
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.touch(exist_ok=True)

    print(f"Created project structure at: {root}")


if __name__ == "__main__":
    main()
```

**Run it:**
```bash
python scaffold.py            # creates ./call-center-agent/
python scaffold.py my-project # or a custom directory name
```

This only creates empty files — every `.py` file, `.txt` policy doc, and `calls.csv` still needs its real content written in during the build steps (Section 11). Don't expect the scaffold to do more than lay out the skeleton.

---

## 9. requirements.txt

**Pin versions.** `langchain`, `langchain-google-genai`, and `langgraph` all ship breaking API changes on a roughly monthly cadence. Leaving these unpinned means a `pip install` run on a different day than your teammate's (or your own, weeks later) can silently resolve a different API than the one every code pattern in this document assumes — `add_conditional_edges` signatures and message-handling helpers have changed shape more than once. Pin at least major.minor, and re-verify against the installed versions' docs if you bump them later.

```
langchain>=0.3,<0.4
langchain-google-genai>=2.0,<3.0
langchain-community>=0.3,<0.4
langgraph>=0.2,<0.3
faiss-cpu>=1.8,<2.0
sentence-transformers>=3.0,<4.0
streamlit>=1.38,<2.0
pandas>=2.2,<3.0
python-dotenv>=1.0,<2.0
```

Run `pip freeze > requirements.lock.txt` after your first successful install and keep that alongside this file — if something breaks weeks in, you can diff against a known-good environment instead of guessing which package moved.

---

## 10. Environment Setup

**.env file:**
```
GOOGLE_API_KEY=your_key_here
```

**.env.example file:**
```
GOOGLE_API_KEY=your_key_here
```

**.gitignore must include:**
```
.env
__pycache__/
*.pyc
.faiss/
```

**Loading in code:**
```python
from dotenv import load_dotenv
import os
load_dotenv()
api_key = os.getenv("GOOGLE_API_KEY")
```

---

## 11. Build Order — Strict Sequence

Do not skip steps. Each step verifies the previous one works before adding complexity.

### Step 1: Project setup
- Create folder structure
- Create and activate virtual environment
- Install requirements
- Create `.env` with Gemini API key
- Verify API key works with a 3-line test script

**Verification test:**
```python
from langchain_google_genai import ChatGoogleGenerativeAI
# gemini-1.5-flash is retired (404). Confirm the current free-tier model name
# at aistudio.google.com before running this — as of Aug 2026 it's gemini-3.5-flash,
# but Google has been retiring Flash versions roughly every few months.
llm = ChatGoogleGenerativeAI(model="gemini-3.5-flash")
print(llm.invoke("Say hello").content)
```

---

### Step 2: Create synthetic data
- Create 5 policy `.txt` files
- Create `calls.csv` with 30 rows
- Verify CSV loads cleanly with pandas

**Verification test:**
```python
import pandas as pd
df = pd.read_csv("data/calls.csv")
print(df.shape)
print(df.columns.tolist())
print(df.head(2))
```

---

### Step 3: Build Tool 2 — Call Lookup
- Build `src/tools/call_lookup.py`
- No LLM needed in the basic version — use pandas filtering
- Test with hardcoded queries first

**Verification test:**
```python
from src.tools.call_lookup import lookup_calls
print(lookup_calls("show me Rahul's last 3 calls"))
```

---

### Step 4: Build Tool 3 — QA Scorer
- Build `src/tools/qa_scorer.py`
- This is the first tool that uses Gemini
- Test with a hardcoded transcript from the CSV

**Verification test:**
```python
from src.tools.qa_scorer import score_call
sample = "Agent: Hi. Customer: I need help. Agent: What's your order? Customer: ORD-123. Agent: Done."
print(score_call(sample, "CALL-1001"))
```

---

### Step 5: Build Tool 1 — Policy Search
- Build `src/tools/policy_search.py`
- Build the FAISS index at startup
- Test with a policy question

**Verification test:**
```python
from src.tools.policy_search import search_policy
print(search_policy("What is the replacement policy?"))
```

---

### Step 6: Build the agent state
- Build `src/agent/state.py`
- Just the TypedDict definition, nothing else

---

### Step 7: Build the LangGraph graph
- Build `src/agent/graph.py`
- Start with just the supervisor node and routing
- Add tool nodes one at a time
- Test in terminal with a direct invoke

**Verification test:**
```python
from src.agent.graph import build_graph
graph = build_graph()
result = graph.invoke({"messages": [{"role": "user", "content": "What is the replacement policy?"}]})
print(result["messages"][-1].content)
```

---

### Step 8: Build the Streamlit UI
- Build `src/ui/app.py`
- Chat interface with message history
- Show which tool was used for each response
- Add a sidebar with sample queries the user can try

---

### Step 9: Polish and README
- Add logging to each tool (use Python `logging` module)
- Add error handling to every tool (try/except with fallback message)
- Write `README.md` (see section 13)
- Record demo video or prepare live demo

---

## 12. Key Code Patterns

### LangGraph graph skeleton (explain this pattern before coding)

```python
from langgraph.graph import StateGraph, END
from src.agent.state import AgentState

def build_graph():
    graph = StateGraph(AgentState)

    # Add nodes
    graph.add_node("supervisor", supervisor_node)
    graph.add_node("policy_node", policy_node)
    graph.add_node("lookup_node", lookup_node)
    graph.add_node("scorer_node", scorer_node)

    # Entry point
    graph.set_entry_point("supervisor")

    # Conditional routing from supervisor
    graph.add_conditional_edges(
        "supervisor",
        route_decision,   # function that reads state and returns node name
        {
            "policy_node": "policy_node",
            "lookup_node": "lookup_node",
            "scorer_node": "scorer_node",
            END: END
        }
    )

    # policy_node and scorer_node are always terminal for this turn
    graph.add_edge("policy_node", END)
    graph.add_edge("scorer_node", END)

    # lookup_node is NOT always terminal — if the supervisor queued "score"
    # after "lookup" (e.g. "score Rahul's last 5 calls"), route on to scorer_node.
    # This is what makes chaining actually work, not just look designed on paper.
    graph.add_conditional_edges(
        "lookup_node",
        route_after_lookup,   # reads state["pending_tools"], returns node name or END
        {
            "scorer_node": "scorer_node",
            END: END
        }
    )

    return graph.compile()
```

### Routing function pattern

```python
def route_decision(state: AgentState) -> str:
    return state["next_tool"]


def route_after_lookup(state: AgentState) -> str:
    """After lookup_node runs, check if 'score' is still queued.
    This is what lets 'score Rahul's last 5 calls' chain into scorer_node
    instead of ending the turn with just a list of records."""
    pending = state.get("pending_tools", [])
    if pending and pending[0] == "score":
        return "scorer_node"
    return END
```

### Supervisor node pattern

```python
def supervisor_node(state: AgentState) -> AgentState:
    last_message = state["messages"][-1].content
    prompt = f"""...(routing prompt — see Section 6, allows comma-separated chaining)...
    User message: {last_message}
    Respond with ONLY the tool word(s), comma-separated: policy, lookup, score, or end."""

    response = llm.invoke(prompt)
    # Gemini sometimes adds trailing punctuation or wraps output — strip it defensively
    # rather than trusting a raw .strip().lower() to always be clean.
    raw = response.content.strip().lower().strip(".")
    decisions = [d.strip() for d in raw.split(",") if d.strip()]

    valid_tools = {"policy", "lookup", "score", "end"}
    decisions = [d for d in decisions if d in valid_tools] or ["end"]

    first, rest = decisions[0], decisions[1:]

    node_map = {"policy": "policy_node", "lookup": "lookup_node", "score": "scorer_node", "end": END}

    return {
        "next_tool": node_map.get(first, END),
        "pending_tools": rest,   # e.g. ["score"] when chaining lookup -> score
    }
```

### QA scorer prompt pattern

```python
SCORING_PROMPT = """
You are a call center quality analyst.
Evaluate the following transcript against these 8 parameters.
For each parameter respond PASS or FAIL.

Parameters:
1. greeting - did agent greet the customer?
2. identity_verification - did agent verify customer identity?
3. problem_acknowledgement - did agent acknowledge the issue?
4. call_classification - did agent identify the call type? (replacement/repair/logistics/device/escalation)
5. solution_offered - did agent offer a resolution?
6. policy_compliance - does the agent's response match the policy text below?
   Base this judgment ONLY on the provided policy text, not on general knowledge.
   If no relevant policy text is provided, respond "FAIL" and note "no policy context available"
   rather than guessing.
7. professional_tone - was agent professional throughout?
8. proper_closure - did agent close the call properly?

Relevant policy text (from RAG retrieval):
{policy_context}

Transcript:
{transcript}

Respond ONLY in this exact JSON format:
{{
  "greeting": "PASS",
  "identity_verification": "FAIL",
  "problem_acknowledgement": "PASS",
  "call_classification": "PASS",
  "solution_offered": "PASS",
  "policy_compliance": "PASS",
  "professional_tone": "PASS",
  "proper_closure": "FAIL"
}}
"""
```

---

## 13. README.md Structure (learner must write this)

The README must contain these sections in this order:

1. **Project title and one-line description**
2. **Problem statement** — what problem does this solve in a real call center?
3. **Solution overview** — what does the agent do in plain English?
4. **Architecture diagram** — can be ASCII art or an image
5. **Technology stack** — table format
6. **Project structure** — folder tree
7. **Setup instructions** — step by step, exact commands
8. **Environment variables** — what keys are needed and where to get them
9. **How to run** — single command to launch
10. **Sample inputs and outputs** — show 3 example conversations
11. **Key design decisions** — why LangGraph, why FAISS, why these 3 tools
12. **Limitations** — what it cannot do yet
13. **Future improvements** — what you'd add with more time

---

## 14. Common Mistakes to Prevent

| Mistake | Prevention |
|---|---|
| Committing `.env` to GitHub | Add to `.gitignore` before first commit |
| LangGraph state not persisting between turns | Use `Annotated[list, add_messages]` for messages |
| FAISS index rebuilt on every query | Build index once at module load, cache it |
| Gemini returning JSON with markdown fences | Strip ```json and ``` before parsing |
| Agent always routes to same tool | Test each routing case explicitly before building UI |
| Streamlit re-running full graph on every keystroke | Use `st.session_state` to store graph and conversation |
| Tool errors crashing the whole agent | Wrap every tool in try/except, return error string |
| Hardcoding a Gemini model ID that Google has since retired | Check the live model list at aistudio.google.com before each build session — Google has been retiring Flash versions every few months through 2026 |
| "Score Rahul's last 5 calls" has nothing to score because lookup and scorer never connect | Use the `pending_tools` queue + `route_after_lookup` conditional edge (Section 6/12) — don't rely on the supervisor picking a single tool |
| QA scorer judges "policy compliance" from memory instead of your actual policy docs | Pass retrieved `policy_context` from Tool 1 into Tool 3's prompt (Section 5, Tool 3) |

---

## 15. Demo Script (for evaluation day)

Walk the evaluator through these 5 interactions in this order:

1. **"What is the replacement policy?"**
   → Demonstrates: Tool 1 (RAG), policy retrieval, LLM answer generation

2. **"Show me Rahul's last 3 calls"**
   → Demonstrates: Tool 2 (lookup), pandas filtering, structured output

3. **"Score call CALL-1005"**
   → Demonstrates: Tool 3 (QA scoring), Gemini structured output, rubric evaluation

4. **"Score Rahul's last 5 calls"**
   → Demonstrates: Multi-step — Tool 2 then Tool 3 in sequence, agent chaining.
   Mechanically: supervisor outputs `lookup,score` → `next_tool="lookup_node"`,
   `pending_tools=["score"]` → `lookup_node` runs, fills `call_records` →
   conditional edge `route_after_lookup` sees `"score"` still pending → routes to
   `scorer_node`, which scores each fetched transcript. Be ready to trace this exact
   path on the whiteboard — it's the part most likely to get a follow-up question.

5. **"What is the repair SLA?"**
   → Demonstrates: Tool 1 again, different policy, shows RAG working on a second doc

After the demo, be ready to explain:
- How LangGraph state flows between nodes
- Why conditional routing is better than if/else
- How the FAISS index works
- What happens when the agent doesn't know which tool to use

---

## 16. Concepts the Learner Must Be Able to Explain

The evaluator will ask about these. Prepare explanations in plain language.

**What is an agent?**
A system where an LLM doesn't just generate text — it decides what actions to take, runs those actions (tools), and uses the results to form a response.

**What is LangGraph?**
A framework that lets you define an agent as a graph of nodes (functions) connected by edges (routing logic), with a shared state that persists across the entire conversation.

**What is RAG?**
Retrieval Augmented Generation. Instead of asking the LLM from memory, you first search a document collection for relevant content, then pass that content to the LLM as context. The LLM answers only from the provided context, not its training data.

**What is FAISS?**
A library by Meta for fast similarity search. It stores text as numerical vectors (embeddings) and finds the most similar vectors to a query vector. Used here to find relevant policy document chunks.

**What is tool calling?**
The ability for an LLM to decide to invoke an external function (tool) instead of answering from memory. The LLM outputs a structured signal (which tool, with what parameters), the framework runs the tool, and the result is passed back to the LLM.

**What is state in LangGraph?**
A shared Python dictionary that travels through every node in the graph. Each node can read from it and write to it. This is how the agent remembers what tools it already ran, what data it fetched, and what the conversation history is.

---

*End of blueprint. Begin teaching at Section 11, Step 1. Do not skip steps.*
