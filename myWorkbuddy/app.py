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
from mylog import log
from gameAgent import run_game_agent_sync
from graphAgent import run_graph_agent_sync
from travelAgent import clear_travel_agent_history, run_travel_agent_sync

from myfunctions import get_default_model, _to_text, change_agent, toolChanged, modelChanged

DEFAULT_SYSTEM_PROMPT = "你是一个乐于助人的 AI 助手，请用中文回答。"
DEFAULT_AGENNT = "A1"


# ---- 创建 RoundAgent 实例 ----
agent = RoundAgent()

def refresh_models():
    """刷新模型列表，返回下拉框更新对象"""
    models = list_models()
    return gr.update(choices=models, value=get_default_model(models))


def clear_chat():
    """清空对话历史 — 同时清空 Gradio UI 和 RoundAgent 的 LangChain 历史"""
    agent.clear_history()
    clear_travel_agent_history()
    return [], "", ""



def respond_url(user_input, history, model, temperature, top_p, system_prompt):
    """处理用户输入，流式生成回复
 
    history: list[dict]，使用 gradio Chatbot 的 messages 格式
             [{"role": "user"/"assistant", "content": "..."}, ...]
    """
    if not user_input or not user_input.strip():
        yield history, "", ""
        return
 
    if not model:
        history = history + [{"role": "user", "content": user_input}]
        history = history + [{
            "role": "assistant",
            "content": "❌ 未检测到可用模型，请确认 Ollama 服务已启动（`ollama serve`）且已 `ollama pull` 至少一个模型，然后点击「刷新模型列表」。",
        }]
        yield history, "", ""
        return
 
    history = history + [{"role": "user", "content": user_input}]
    history = history + [{"role": "assistant", "content": ""}]
    yield history, "", ""
 
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
            yield history, "", ""
    except Exception as e:
        full_response = f"❌ 请求出错：{e}"
        history[-1]["content"] = full_response
        yield history, "", "✅ 当前任务已结束"

def respondGameAgent(user_input, history):
    """处理 Game Agent 请求，并把 AutoGen 团队结果显示在聊天窗口。"""
    history = history + [{"role": "user", "content": user_input}]
    history = history + [{"role": "assistant", "content": ""}]
    yield history, "", ""
    try:
        response = run_game_agent_sync(user_input)
    except Exception as e:
        response = f"❌ Game Agent 请求出错：{e}"
    history[-1]["content"] = response
    yield history, "", "✅ 当前任务已结束"


def respondGraphAgent(user_input, history, model, temperature, top_p, system_prompt):
    """处理 Graph Agent 请求，并把 LangGraph 结果显示在聊天窗口。"""
    history = history + [{"role": "user", "content": user_input}]
    history = history + [{"role": "assistant", "content": ""}]
    yield history, "", ""
    try:
        response = run_graph_agent_sync(
            user_input,
            model,
            temperature,
            top_p,
            system_prompt or "",
        )
    except Exception as e:
        response = f"❌ Graph Agent 请求出错：{e}"
    history[-1]["content"] = response
    yield history, "", "✅ 当前任务已结束"


def respondMCPTravel(user_input, history, model):
    """处理 MCP-Travel 请求，并保留连续旅行对话上下文。"""
    history = history + [{"role": "user", "content": user_input}]
    history = history + [{"role": "assistant", "content": ""}]
    yield history, "", ""
    try:
        response = run_travel_agent_sync(user_input, model=model or "gpt-5.4-mini")
    except Exception as e:
        response = f"❌ MCP-Travel 请求出错：{e}"
    history[-1]["content"] = response
    yield history, "", "✅ 当前任务已结束"


def respondRoundAgent(user_input, history, model, temperature, top_p, system_prompt):
    """处理普通 Agent 请求，通过 RoundAgent.round_stream 流式生成回复

    对话历史由 RoundAgent 内部的 LangChain RunnableWithMessageHistory 管理，
    Gradio 的 history 参数仅用于 UI 渲染展示。

    history: list[dict]，使用 gradio Chatbot 的 messages 格式
             [{"role": "user"/"assistant", "content": "..."}, ...]
    """
    if not user_input or not user_input.strip():
        yield history, "", ""
        return

    if not model:
        history = history + [{"role": "user", "content": user_input}]
        history = history + [{
            "role": "assistant",
            "content": "❌ 未检测到可用模型，请确认 Ollama 服务已启动（`ollama serve`）且已 `ollama pull` 至少一个模型，然后点击「刷新模型列表」。",
        }]
        yield history, "", ""
        return

    # 追加用户消息和空的 assistant 占位
    history = history + [{"role": "user", "content": user_input}]
    history = history + [{"role": "assistant", "content": ""}]
    yield history, "", ""

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
            yield history, "", ""
    except Exception as e:
        full_response = f"❌ 请求出错：{e}"
        history[-1]["content"] = full_response
        yield history, "", "✅ 当前任务已结束"


def respond(user_input, history, model, temperature, top_p, system_prompt, selected_agent_type):
    """根据用户选择，只调用对应的 Agent 处理函数。"""
    if not user_input or not user_input.strip():
        yield history, "", ""
        return

    if selected_agent_type == "Game Agent":
        yield from respondGameAgent(user_input, history)
        return

    if selected_agent_type == "Graph Agent":
        if not model:
            yield from respondRoundAgent(
                user_input,
                history,
                model,
                temperature,
                top_p,
                system_prompt,
            )
            return
        yield from respondGraphAgent(
            user_input,
            history,
            model,
            temperature,
            top_p,
            system_prompt,
        )
        return

    if selected_agent_type == "MCP-Travel":
        yield from respondMCPTravel(user_input, history, model)
        return

    yield from respondRoundAgent(
        user_input,
        history,
        model,
        temperature,
        top_p,
        system_prompt,
    )


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

            temperature_slider = gr.State(0.7)   # 实际值，由弹窗写入
            top_p_slider = gr.State(0.9)          # 实际值，由弹窗写入

            advance_btn = gr.Button("⚙️ Advance Setting", variant="secondary")

            # ---- Advance Setting 弹出面板（默认隐藏） ----
            advance_panel = gr.Group(visible=False)
            with advance_panel:
                gr.Markdown("### ⚙️ Advance Setting")
                gr.Markdown("调整模型生成参数，保存后生效。")

                adv_temperature = gr.Slider(
                    label="Temperature",
                    minimum=0.0, maximum=1.5, value=0.7, step=0.05,
                    info="越高越有创造力，越低越确定保守",
                )
                adv_top_p = gr.Slider(
                    label="Top-P",
                    minimum=0.1, maximum=1.0, value=0.9, step=0.05,
                    info="核采样阈值，控制候选词范围",
                )

                with gr.Row():
                    adv_reset_btn = gr.Button("↩️ 重置默认", variant="secondary")
                    adv_save_btn = gr.Button("✅ 保存并关闭", variant="primary")
            agent_type = gr.Radio(
                choices=["Code Expert", "Travel Guide", "Math Tutor", "Story Teller", "Game Agent", "Graph Agent", "MCP-Travel"],
                value="Code Expert",
                label="Agent 类型",
            )
            tool_selections = gr.CheckboxGroup(
                choices=["Email管家","Calendar助手","文件助手"," 搜索专家"],
                value=[],
                label="Tool 类型",
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
            task_status = gr.Markdown()
            user_input_box = gr.Textbox(
                placeholder="输入消息...",
                show_label=False,
                lines=1,
            )

    # ---- 事件绑定 ----
    # Advance Setting 弹窗：打开时从 State 读入当前值
    advance_btn.click(
        lambda t, p: (gr.update(visible=True), gr.update(value=t), gr.update(value=p)),
        inputs=[temperature_slider, top_p_slider],
        outputs=[advance_panel, adv_temperature, adv_top_p],
    )

    # 保存：把弹窗里的值写回 State 并关闭面板
    adv_save_btn.click(
        lambda t, p: (gr.update(visible=False), t, p),
        inputs=[adv_temperature, adv_top_p],
        outputs=[advance_panel, temperature_slider, top_p_slider],
    )

    # 重置默认
    adv_reset_btn.click(
        lambda: (gr.update(value=0.7), gr.update(value=0.9)),
        inputs=None,
        outputs=[adv_temperature, adv_top_p],
    )

    user_input_box.submit(
        respond,
        inputs=[user_input_box, chatbot, model_dropdown, temperature_slider, top_p_slider, system_prompt_box, agent_type],
        outputs=[chatbot, user_input_box, task_status],
    )

    refresh_btn.click(refresh_models, inputs=None, outputs=model_dropdown)
    clear_btn.click(clear_chat, inputs=None, outputs=[chatbot, user_input_box, task_status])

    model_dropdown.change(
        modelChanged,
        inputs=[model_dropdown],
        outputs=None,
    )

    agent_type.change(
        change_agent,
        inputs=[agent_type],
        outputs=[system_prompt_box]
    )

    tool_selections.change(
        toolChanged,
        inputs=[tool_selections],
        outputs=None
    )


if __name__ == "__main__":
    demo.queue().launch(theme=gr.themes.Soft())