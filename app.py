"""Gradio + Ollama 本地聊天机器人

功能：
- 多轮对话上下文（由 roundAgent 管理 LangChain 对话历史）
- 流式逐字输出
- 模型切换（自动列出已安装模型）
- Temperature / Top-P 参数调节
- System Prompt 自定义
- 对话清空
"""
import gradio as gr

from ollama_client import list_models,chat_stream
from roundAgent import RoundAgent

DEFAULT_SYSTEM_PROMPT = "你是一个乐于助人的 AI 助手，请用中文回答。"

# ---- 创建 RoundAgent 实例 ----
agent = RoundAgent()


def get_default_model(models: list[str]):
    if not models:
        return None
    return "qwen2.5:7b" if "qwen2.5:7b" in models else models[0]


def refresh_models():
    """刷新模型列表，返回下拉框更新对象"""
    models = list_models()
    return gr.update(choices=models, value=get_default_model(models))


def clear_chat():
    """清空对话历史 — 同时清空 Gradio UI 和 RoundAgent 的 LangChain 历史"""
    agent.clear_history()
    return [], ""


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



def respond_url(user_input, history, model, temperature, top_p, system_prompt):
    """处理用户输入，流式生成回复
 
    history: list[dict]，使用 gradio Chatbot 的 messages 格式
             [{"role": "user"/"assistant", "content": "..."}, ...]
    """
    if not user_input or not user_input.strip():
        yield history, ""
        return
 
    if not model:
        history = history + [{"role": "user", "content": user_input}]
        history = history + [{
            "role": "assistant",
            "content": "❌ 未检测到可用模型，请确认 Ollama 服务已启动（`ollama serve`）且已 `ollama pull` 至少一个模型，然后点击「刷新模型列表」。",
        }]
        yield history, ""
        return
 
    history = history + [{"role": "user", "content": user_input}]
    history = history + [{"role": "assistant", "content": ""}]
    yield history, ""
 
    # 构建上下文（不包含刚追加的空 assistant 占位）
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
            yield history, ""
    except Exception as e:
        full_response = f"❌ 请求出错：{e}"
        history[-1]["content"] = full_response
        yield history, ""

def respondRoundGroup(user_input, history, model, temperature, top_p, system_prompt):
    """处理用户输入，通过 RoundAgent.round_stream 流式生成回复

    对话历史由 RoundAgent 内部的 LangChain RunnableWithMessageHistory 管理，
    Gradio 的 history 参数仅用于 UI 渲染展示。

    history: list[dict]，使用 gradio Chatbot 的 messages 格式
             [{"role": "user"/"assistant", "content": "..."}, ...]
    """
    if not user_input or not user_input.strip():
        yield history, ""
        return

    if not model:
        history = history + [{"role": "user", "content": user_input}]
        history = history + [{
            "role": "assistant",
            "content": "❌ 未检测到可用模型，请确认 Ollama 服务已启动（`ollama serve`）且已 `ollama pull` 至少一个模型，然后点击「刷新模型列表」。",
        }]
        yield history, ""
        return

    # 追加用户消息和空的 assistant 占位
    history = history + [{"role": "user", "content": user_input}]
    history = history + [{"role": "assistant", "content": ""}]
    yield history, ""

    # ---- 调用 RoundAgent.round_stream 完成对话 ----
    full_response = ""
    try:
        for chunk in agent.round_stream(
            user_input=user_input,
            system_prompt=system_prompt or "",
            model=model,
            temperature=temperature,
            top_p=top_p,
        ):
            full_response += chunk
            history[-1]["content"] = full_response
            yield history, ""
    except Exception as e:
        full_response = f"❌ 请求出错：{e}"
        history[-1]["content"] = full_response
        yield history, ""


with gr.Blocks(title="Ollama Chat") as demo:
    gr.Markdown("# 🦙 Ollama Chat")

    with gr.Row():
        # ---- 侧边栏设置 ----
        with gr.Column(scale=1, min_width=280):
            gr.Markdown("### ⚙️ 设置")

            initial_models = list_models()

            model_dropdown = gr.Dropdown(
                label="选择模型",
                choices=initial_models,
                value=get_default_model(initial_models),
            )
            if not initial_models:
                gr.Markdown(
                    "⚠️ 未检测到已安装的模型，请确认本机 Ollama 服务已启动，"
                    "且已执行过 `ollama pull <模型名>`，再点击下方「刷新模型列表」。"
                )

            temperature_slider = gr.Slider(
                label="Temperature",
                minimum=0.0, maximum=1.5, value=0.7, step=0.05,
                info="越高越有创造力，越低越确定保守",
            )
            top_p_slider = gr.Slider(
                label="Top-P",
                minimum=0.1, maximum=1.0, value=0.9, step=0.05,
                info="核采样阈值，控制候选词范围",
            )

            system_prompt_box = gr.Textbox(
                label="System Prompt",
                value=DEFAULT_SYSTEM_PROMPT,
                lines=4,
            )

            with gr.Row():
                refresh_btn = gr.Button("🔄 刷新模型列表")
                clear_btn = gr.Button("🗑️ 清空对话")

            gr.Markdown("---")
            gr.Markdown("🦙 Powered by Ollama + Gradio")

        # ---- 主聊天区域 ----
        with gr.Column(scale=3):
            chatbot = gr.Chatbot(
                label="对话",
                height=560,
                buttons=["copy", "copy_all"],
            )
            user_input_box = gr.Textbox(
                placeholder="输入消息...",
                show_label=False,
                lines=1,
            )

    # ---- 事件绑定 ----
    user_input_box.submit(
        respond_url, #respondRoundGroup
        inputs=[user_input_box, chatbot, model_dropdown, temperature_slider, top_p_slider, system_prompt_box],
        outputs=[chatbot, user_input_box],
    )

    refresh_btn.click(refresh_models, inputs=None, outputs=model_dropdown)
    clear_btn.click(clear_chat, inputs=None, outputs=[chatbot, user_input_box])


if __name__ == "__main__":
    demo.queue().launch(theme=gr.themes.Soft())