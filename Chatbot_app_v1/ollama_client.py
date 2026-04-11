import requests

OLLAMA_URL = "http://localhost:11434/api/chat"

MODEL_MAP = {
    "reasoning": "deepseek-r1:1.5b",
    "coding":    "qwen2.5:7b-instruct",
    "creative":  "gemma:2b",
    "chat":      "qwen2.5:3b",
    "simple":    "phi3:mini",
    "default":   "qwen3:4b", # if slow replace with "phi3:mini"
}

def get_model(task_type: str) -> str:
    return MODEL_MAP.get(task_type, MODEL_MAP["default"])

def call_ollama(messages: list, task_type: str = "default") -> tuple[str, str]:
    model = get_model(task_type)
    payload = {
        "model": model,
        "messages": messages,
        "stream": False
    }
    response = requests.post(OLLAMA_URL, json=payload)
    response.raise_for_status()
    reply = response.json()["message"]["content"]
    return reply, model