# ==================================================
# JSON helpers (module-level utility functions, stateless)
# ==================================================
import json
import os
from typing import Dict, Generator, Optional, List, Any
from langchain_core.messages import HumanMessage, AIMessage
from ronglog import log


def _load_history_file(path: str) -> Dict[str, list]:
    if not os.path.exists(path):
        return {}
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _save_history_file(path: str, data: Dict[str, list]):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def _json_to_messages(items):
    messages = []
    for item in items:
        if item["role"] == "human":
            messages.append(HumanMessage(content=item["content"]))
        elif item["role"] == "ai":
            messages.append(AIMessage(content=item["content"]))
    return messages


def _messages_to_json(messages):
    out = []
    for m in messages:
        if isinstance(m, HumanMessage):
            out.append({"role": "human", "content": m.content})
        elif isinstance(m, AIMessage):
            out.append({"role": "ai", "content": m.content})
    return out


#---------------------------------------
def get_default_model(models: list[str]):
    if not models:
        return None
    return "qwen2.5:7b" if "qwen2.5:7b" in models else models[0]



def _to_text(content) -> str:
    """Flatten the content field from Gradio Chatbot messages into a plain string.

    In Gradio 6, the Chatbot component sometimes wraps the content field as a
    list of content fragments (e.g., [{"type": "text", "text": "..."}] for
    multimodal messages) when passing history back to Python callbacks.
    Ollama's /api/chat endpoint only accepts plain strings; passing a list
    directly causes "cannot unmarshal array into ... content of type string".
    This function unifies the conversion to avoid that issue.
    """
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict):
                text = item.get("text")
                if text:
                    parts.append(str(text))
        return "".join(parts)
    return "" if content is None else str(content)


def change_expert(expert_name: str, agent_type: str):
    return "z1"
def change_agent(agent_type: str):
    log("Agent changed to:" + agent_type)
    return agent_type

def modelChanged(model: str):
    """Record the user's selected model."""
    log("Model changed to:" + str(model))

def toolChanged(toolnames):
    """Record the user's selected tools."""
    log("Tool selection changed to: " + str(toolnames or []))
