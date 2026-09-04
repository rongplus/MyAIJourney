# ==================================================
# JSON helpers（模块级工具函数，不含状态）
# ==================================================
import json
import os
from typing import Dict, Generator, Optional, List, Any
from langchain_core.messages import HumanMessage, AIMessage


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
