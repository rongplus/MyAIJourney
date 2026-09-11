from ronglog import log
# local ollama
from localChatOllama import localChatOllama

chat_client = localChatOllama(modelName='qwen2.5:7b', temperature= 0.7)


def respond_local_ollama_stream(user_input, history, model, temperature, top_p):
    history = history or []
    if not user_input or not str(user_input).strip():
        yield history, ""
        return

    if not model:
        history = history + [{"role": "user", "content": user_input}]
        history = history + [{
            "role": "assistant",
            "content": "❌ 未检测到可用的本地模型，请确认 Ollama 服务已启动，并确保已安装模型。",
        }]
        yield history, ""
        return

    history = history + [{"role": "user", "content": user_input}]
    history = history + [{"role": "assistant", "content": ""}]
    yield history, ""
    log("history")
    log(history)

    try:
        full_response = ""
        for chunk in chat_client.chatWithChatOllamaStream(user_input, history=history[:-1]):
            if chunk is None:
                continue
            full_response += str(chunk)
            history[-1]["content"] = full_response
            yield history, ""
    except Exception as e:
        history[-1]["content"] = f"❌ 本地模型调用失败：{e}"
        yield history, ""



# local url
from url_client import list_models, respond_url, chat_stream

def get_default_model(models: list[str]):
    if not models:
        return None
    return "qwen2.5:7b" if "qwen2.5:7b" in models else models[0]


# local openai