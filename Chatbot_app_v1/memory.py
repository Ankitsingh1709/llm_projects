from ollama_client import call_ollama

MAX_SHORT_TERM = 5       # last N messages always included
SUMMARIZE_EVERY = 10     # summarize after this many messages

SUMMARY_PROMPT = """Summarize this conversation in 3-4 sentences. 
Be concise. Focus on key topics, decisions, and context that would help continue the conversation."""

def should_summarize(history: list) -> bool:
    user_msgs = [m for m in history if m["role"] == "user"]
    return len(user_msgs) > 0 and len(user_msgs) % SUMMARIZE_EVERY == 0

def summarize(history: list) -> str:
    conversation_text = "\n".join(
        f"{m['role'].upper()}: {m['content']}" for m in history
    )
    messages = [
        {"role": "user", "content": f"{SUMMARY_PROMPT}\n\n{conversation_text}"}
    ]
    try:
        summary, _ = call_ollama(messages, task_type="simple")
        return summary.strip()
    except Exception:
        return ""

def build_context(history: list, summary: str) -> list:
    """Build the message list to send: system summary + last N messages."""
    context = []

    if summary:
        context.append({
            "role": "system",
            "content": f"Conversation summary so far:\n{summary}"
        })

    # Always include last MAX_SHORT_TERM messages
    recent = history[-MAX_SHORT_TERM:] if len(history) > MAX_SHORT_TERM else history
    context.extend(recent)

    return context