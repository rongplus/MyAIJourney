import gradio as gr
from huggingface_hub import list_models

from ronglog import log

from rongtools import get_weather, safe_path, read_file, write_file, list_files, TOOLS

from url_client import list_models, respond_url, chat_stream


def get_default_model(models: list[str]):
    if not models:
        return None
    return "qwen2.5:7b" if "qwen2.5:7b" in models else models[0]


# Response the user input
def userInput(user_input, history):
    history = history or []
    #，该版本的 Chatbot 组件已完全移除了 type 参数，仅支持 messages 格式（即 {"role": "user", "content": "..."} 字典）。
    history.append({"role": "user", "content": user_input}) 
    #Second is for return to the input box or user
    yield history, "Got it! Processing..."

def toolChanged(tool_selections):
    # Update the selected tools based on user selection
    """记录用户选择的工具。"""
    log("Tool selection changed to: " + str(tool_selections or []))



def noChat(user_input_box, chatbot):
    user_input_box.submit(
        userInput,
        inputs=[user_input_box, chatbot],
        outputs=[chatbot,user_input_box],
    )

def chatWithUrl(user_input_box, chatbot, model_dropdown, temperature_slider, top_p_slider):
    user_input_box.submit(
        respond_url,
        inputs=[user_input_box, chatbot, model_dropdown, temperature_slider, top_p_slider],
        outputs=[chatbot,user_input_box],
    )

with gr.Blocks(title="Rong's Workbuddy") as demo:
    gr.Markdown("# 🦙 Rong's Workbuddy")

    with gr.Row():
            # ---- 侧边栏设置 ----
            with gr.Column(scale=1, min_width=280):
                gr.Markdown("### ⚙️ 设置")

                tool_selections = gr.CheckboxGroup(
                                choices=['Get Weather', 'Safe Path', 'Read File', 'Write File', 'List Files'],
                                value=[],
                                label="Tool 类型",
                            )
                
                llm_btn = gr.Button("⚙️ 本地模型", variant="secondary")    
                # ---- Advance Setting 弹出面板（默认隐藏） ----
                llm_panel = gr.Group(visible=False)
                with llm_panel:
                    gr.Markdown("### ⚙️ Local LLaMA 设置，保存后生效。")
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


            # ---- 聊天窗口 ----

            with gr.Column(scale=4, min_width=600):
                gr.Markdown("### 💬 聊天窗口")
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
    # Advance Setting 弹窗：打开时从 State 读入当前值
    llm_btn.click(
        lambda t, p: (gr.update(visible=True), gr.update(value=t), gr.update(value=p)),
        inputs=[temperature_slider, top_p_slider],
        outputs=[llm_panel, adv_temperature, adv_top_p],
    )
    # 保存：把弹窗里的值写回 State 并关闭面板
    adv_save_btn.click(
        lambda t, p: (gr.update(visible=False), t, p),
        inputs=[adv_temperature, adv_top_p],
        outputs=[llm_panel, temperature_slider, top_p_slider],
    )
    
    # 重置默认
    adv_reset_btn.click(
        lambda: (gr.update(value=0.7), gr.update(value=0.9)),
        inputs=None,
        outputs=[adv_temperature, adv_top_p],
    )

    
    # 事件绑定: chat
    """
    
    """

    chatWithUrl(user_input_box, chatbot, model_dropdown, temperature_slider, top_p_slider)
    
    tool_selections.change(
            toolChanged,
            inputs=[tool_selections],
            outputs=None
        )

if __name__ == "__main__":
    demo.queue().launch(theme=gr.themes.Soft())