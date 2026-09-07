# ==================================================
# JSON helpers（模块级工具函数，不含状态）
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
    """把 Gradio Chatbot 消息里的 content 统一拍平成纯字符串。

    Gradio 6 的 Chatbot 组件在把历史消息回传给 Python 回调时，content
    字段有时是 str，有时会被包装成内容片段列表（例如
    [{"type": "text", "text": "..."}]，用于支持图片/文件等多模态消息）。
    Ollama 的 /api/chat 接口只接受纯字符串，直接把 list 传过去会报
    "cannot unmarshal array into ... content of type string"。这里做
    统一转换，避免这个问题。
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
    """记录用户选择的模型。"""
    log("Model changed to:" + str(model))

def toolChanged(toolnames):
    """记录用户选择的工具。"""
    log("Tool selection changed to: " + str(toolnames or []))