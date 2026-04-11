from ollama_client import call_ollama

ROUTER_SYSTEM = """You are a message classifier. Classify the user's message into exactly one of these categories:
- reasoning   → math, logic, analysis, puzzles, step-by-step problems
- coding      → code, programming, debugging, scripts, technical implementation
- creative    → stories, poems, brainstorming, writing, creative tasks
- simple      → greetings, yes/no questions, very short factual questions
- chat        → everything else, general conversation, explanations

Reply with ONLY the single word category. Nothing else."""

def classify_message(user_message: str) -> str:
    messages = [
        {"role": "system", "content": ROUTER_SYSTEM},
        {"role": "user",   "content": user_message}
    ]
    try:
        reply, _ = call_ollama(messages, task_type="default")
        task_type = reply.strip().lower().split()[0]
        valid = {"reasoning", "coding", "creative", "simple", "chat"}
        return task_type if task_type in valid else "chat"
    except Exception:
        return "chat"