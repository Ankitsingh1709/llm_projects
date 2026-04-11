# 🤖 Multi-Model AI Chatbot

A locally-run AI chatbot built with Streamlit and Ollama that features **automatic model routing** and **smart memory management**. Instead of using a single model for everything, the chatbot intelligently selects the best local model based on what you're asking.

---

## Features

- **Automatic Model Routing** — classifies each message and picks the best model for the task
- **Smart Memory** — maintains conversation context using a rolling summary + recent messages
- **Model Transparency** — every response shows which model was used and why
- **Fully Local** — runs entirely on your machine via Ollama, no API keys needed
- **Built with Streamlit** — clean chat UI with session persistence

---

## Project Structure

```
chatbot_app_v1/
├── app.py              # Streamlit UI and main app logic
├── router.py           # Classifies user messages and selects model
├── memory.py           # Manages conversation summary and context window
└── ollama_client.py    # Ollama API wrapper and model map
```

---

## Model Routing Map

| Task Type | Model | When it's used |
|---|---|---|
| `reasoning` | `deepseek-r1:1.5b` | Math, logic, puzzles, step-by-step analysis |
| `coding` | `qwen2.5:7b-instruct` | Writing, fixing, or debugging actual code |
| `creative` | `gemma:2b` | Stories, poems, brainstorming, creative writing |
| `chat` | `qwen2.5:3b` | General conversation, explanations, discussions |
| `simple` | `phi3:mini` | Greetings, basic facts, yes/no questions |
| `default` | `qwen3:4b` | Fallback + used as the router classifier itself |

---

## How It Works

### Routing
Every message is first sent to `qwen3:4b` with a strict classification prompt. The router identifies **what the user wants to do**, not just what words they use. For example, saying *"I am building something in Python"* is classified as `chat`, while *"write me a Python function"* is classified as `coding`.

### Memory
Rather than sending the full conversation history every time (which hits context window limits), the system uses two layers:

- **Short-term** — the last 5 messages are always included
- **Long-term** — every 10 messages, the full history is compressed into a 3-4 sentence summary by a model, and that summary is injected as a system message going forward

This keeps each request lean while preserving the important context.

---

## Requirements

- Python 3.10+
- [Ollama](https://ollama.com) installed and running locally
- The following models pulled in Ollama:

```bash
ollama pull qwen3:4b
ollama pull qwen2.5:7b-instruct
ollama pull qwen2.5:3b
ollama pull deepseek-r1:1.5b
ollama pull gemma:2b
ollama pull phi3:mini
```

---

## Installation

```bash
# 1. Clone or copy the project files into a folder
cd your-project-folder

# 2. Create a virtual environment
python -m venv myenv
myenv\Scripts\activate        # Windows
# source myenv/bin/activate   # Mac/Linux

# 3. Install dependencies
pip install streamlit requests

# 4. Make sure Ollama is running
ollama serve

# 5. Run the app
streamlit run app.py
```

---

## Usage

Just type naturally — the chatbot handles model selection automatically. You'll see a badge under each response showing:

```
🤖 `qwen2.5:7b-instruct`  ·  task: `coding`
```

Use the **Reset Conversation** button to clear history and start fresh.

---

## Configuration

To change model assignments, edit `MODEL_MAP` in `ollama_client.py`:

```python
MODEL_MAP = {
    "reasoning": "deepseek-r1:1.5b",
    "coding":    "qwen2.5:7b-instruct",
    "creative":  "gemma:2b",
    "chat":      "qwen2.5:3b",
    "simple":    "phi3:mini",
    "default":   "qwen3:4b",
}
```

To change how often the memory summarizes, edit `memory.py`:

```python
MAX_SHORT_TERM = 5      # how many recent messages to always include
SUMMARIZE_EVERY = 10    # summarize after this many user messages
```

---
