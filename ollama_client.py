"""Ollama API 客户端 — 封装模型列表、流式聊天接口"""
import json

import requests

OLLAMA_HOST = "http://localhost:11434"


_EMBED_KEYWORDS = ("embed", "bge-", "minilm", "gte-")


def list_models() -> list[str]:
    """获取已安装的模型列表

    优先用 capabilities 字段过滤出对话模型；如果当前 Ollama 版本的
    /api/tags 不返回 capabilities（旧版本没有这个字段），则退化为按
    名字关键词粗略排除纯 embedding 模型，而不是返回一个写死的、
    可能本地根本没安装的模型名（这会导致 /api/chat 返回 400/404）。
    """
    try:
        resp = requests.get(f"{OLLAMA_HOST}/api/tags", timeout=5)
        resp.raise_for_status()
        models = resp.json().get("models", [])
    except Exception as e:
        print(f"[list_models] 获取模型列表失败：{e}")
        return []

    if not models:
        return []

    all_names = [m["name"] for m in models if m.get("name")]

    # 优先按 capabilities 过滤（新版 Ollama 才有该字段）
    chat_models = [
        m["name"] for m in models
        if "completion" in m.get("capabilities", [])
           or "tools" in m.get("capabilities", [])
           or "vision" in m.get("capabilities", [])
    ]
    if chat_models:
        return sorted(chat_models)

    # capabilities 字段缺失（旧版 Ollama）：退化为按名字关键词排除 embedding 模型
    fallback = [n for n in all_names if not any(k in n.lower() for k in _EMBED_KEYWORDS)]
    return sorted(fallback) if fallback else sorted(all_names)


def chat_stream(model: str, messages: list[dict], temperature: float = 0.7, top_p: float = 0.9):
    """流式聊天，逐 token 返回生成器"""
    payload = {
        "model": model,
        "messages": messages,
        "stream": True,
        "options": {"temperature": temperature, "top_p": top_p},
    }
    resp = requests.post(
        f"{OLLAMA_HOST}/api/chat",
        json=payload,
        stream=True,
        timeout=120,
    )
    if not resp.ok:
        # 把 Ollama 返回的具体错误原因带出来（例如“模型不存在”），
        # 而不是只报一个笼统的 400/404 状态码。
        try:
            detail = resp.json().get("error", resp.text)
        except Exception:
            detail = resp.text
        raise RuntimeError(f"Ollama 返回错误（HTTP {resp.status_code}）：{detail}")
    for line in resp.iter_lines(decode_unicode=True):
        if not line:
            continue
        try:
            chunk = json.loads(line)
        except json.JSONDecodeError:
            continue
        content = chunk.get("message", {}).get("content", "")
        if content:
            yield content
        if chunk.get("done"):
            break