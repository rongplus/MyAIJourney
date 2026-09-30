"""Ollama API client — wraps model listing and streaming chat interface"""
import json

import requests

from rongfunctions import _to_text, log

OLLAMA_HOST = "http://localhost:11434"


_EMBED_KEYWORDS = ("embed", "bge-", "minilm", "gte-")


def list_models() -> list[str]:
    """Get the list of installed models.

    Prefer filtering chat models using the capabilities field; if the current
    Ollama version's /api/tags does not return capabilities (older versions
    don't have this field), fall back to roughly excluding pure embedding
    models by name keywords, rather than returning a hardcoded model name
    that may not be installed locally (which would cause /api/chat to return
    400/404).
    """
    try:
        resp = requests.get(f"{OLLAMA_HOST}/api/tags", timeout=5)
        resp.raise_for_status()
        models = resp.json().get("models", [])
    except Exception as e:
        print(f"[list_models] Failed to get model list: {e}")
        return []

    if not models:
        return []

    all_names = [m["name"] for m in models if m.get("name")]

    # Prefer filtering by capabilities (only newer Ollama versions have this field)
    chat_models = [
        m["name"] for m in models
        if "completion" in m.get("capabilities", [])
           or "tools" in m.get("capabilities", [])
           or "vision" in m.get("capabilities", [])
    ]
    if chat_models:
        return sorted(chat_models)

    # capabilities field missing (older Ollama): fall back to excluding embedding models by name keywords
    fallback = [n for n in all_names if not any(k in n.lower() for k in _EMBED_KEYWORDS)]
    return sorted(fallback) if fallback else sorted(all_names)



def respond_url(user_input, history, model, temperature, top_p, system_prompt):
    """Process user input and stream a response.
 
    history: list[dict], using gradio Chatbot's messages format
             [{"role": "user"/"assistant", "content": "..."}, ...]
    """
    system_prompt = """
    You are a helpful assistant that helps users complete various tasks. Please provide useful answers based on user input and context."""
    log(f"respond_url: user_input={user_input}, model={model}, temperature={temperature}, top_p={top_p}, system_prompt={system_prompt}")
    if not user_input or not user_input.strip():
        yield history, "", ""
        return
 
    if not model:
        history = history + [{"role": "user", "content": user_input}]
        history = history + [{
            "role": "assistant",
            "content": "No available model detected. Please make sure the Ollama service is running (`ollama serve`) and at least one model has been pulled via `ollama pull`, then click \"Refresh Model List\".",
        }]
        yield history, "", ""
        return
 
    history = history + [{"role": "user", "content": user_input}]
    history = history + [{"role": "assistant", "content": ""}]
    yield history, "", ""
 
    # Build context (excluding the empty assistant placeholder just appended)
    context = []
    if system_prompt and system_prompt.strip():
        context.append({"role": "system", "content": system_prompt})
    context.extend(
        {"role": m["role"], "content": _to_text(m["content"])}
        for m in history[:-1]
    )
 
    full_response = ""
    try:
        for chunk in chat_stream(model, context, temperature, top_p):
            full_response += chunk
            history[-1]["content"] = full_response
            yield history, "", ""
    except Exception as e:
        full_response = f"Request error: {e}"
        history[-1]["content"] = full_response
        yield history, "", "Current task completed"


def chat_stream(model: str, messages: list[dict], temperature: float = 0.7, top_p: float = 0.9):
    """Streaming chat, returns a generator yielding tokens one by one"""
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
        # Bring out the specific error reason returned by Ollama
        # (e.g., "model does not exist"), rather than just reporting a generic
        # 400/404 status code.
        try:
            detail = resp.json().get("error", resp.text)
        except Exception:
            detail = resp.text
        raise RuntimeError(f"Ollama returned error (HTTP {resp.status_code}): {detail}")
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
