import warnings
warnings.filterwarnings('ignore')

import streamlit as st
from ollama_client import call_ollama
from router import classify_message
from memory import build_context, should_summarize, summarize

st.set_page_config(page_title="My First AI Chat Assistant", page_icon="🤖")
st.title("🤖 AI Chat Assistant")

# Initialize state
if "history" not in st.session_state:
    st.session_state["history"] = [{"role": "assistant", "content": "Hello! How can I help you today?"}]
if "summary" not in st.session_state:
    st.session_state["summary"] = ""
if "message_meta" not in st.session_state:
    st.session_state["message_meta"] = {}  # index → {model, task_type}

# Display chat history
for i, msg in enumerate(st.session_state["history"]):
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])
        # Show meta badge if this assistant message has model info
        if msg["role"] == "assistant" and i in st.session_state["message_meta"]:
            meta = st.session_state["message_meta"][i]
            st.caption(f"🤖 `{meta['model']}`  ·  task: `{meta['task_type']}`")

# User input
if prompt := st.chat_input("Type your message..."):
    st.session_state["history"].append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    # 1. Route → classify task
    task_type = classify_message(prompt)

    # 2. Memory → build context
    if should_summarize(st.session_state["history"]):
        st.session_state["summary"] = summarize(st.session_state["history"])

    context = build_context(st.session_state["history"], st.session_state["summary"])

    # 3. Call the selected model
    reply, model_used = call_ollama(context, task_type=task_type)

    # 4. Save reply + meta
    assistant_index = len(st.session_state["history"])
    st.session_state["history"].append({"role": "assistant", "content": reply})
    st.session_state["message_meta"][assistant_index] = {
        "model": model_used,
        "task_type": task_type
    }

    with st.chat_message("assistant"):
        st.markdown(reply)
        st.caption(f"🤖 `{model_used}`  ·  task: `{task_type}`")

# Reset
if st.button("🔄 Reset Conversation"):
    st.session_state["history"] = [{"role": "assistant", "content": "Conversation reset. How can I assist you?"}]
    st.session_state["summary"] = ""
    st.session_state["message_meta"] = {}
    st.rerun()