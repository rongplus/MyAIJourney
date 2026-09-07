import gradio as gr

from ronglog import log

from rongtools import get_weather, safe_path, read_file, write_file, list_files, TOOLS

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
              
    user_input_box.submit(
            userInput,
            inputs=[user_input_box, chatbot],
            outputs=[chatbot,user_input_box],
        )
    tool_selections.change(
            toolChanged,
            inputs=[tool_selections],
            outputs=None
        )

if __name__ == "__main__":
    demo.queue().launch(theme=gr.themes.Soft())