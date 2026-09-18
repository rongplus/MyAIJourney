import gradio as gr
import asyncio

from ronglog import log

from rongtools import get_weather, safe_path, read_file, write_file, list_files, TOOLS

from url_client import list_models, respond_url

from myclient import get_default_model, getClient
from localChatOllama import localChatOllama
from autogenGame import AutoGenGameClient
from crewaiAgent import CrewAIClient
from ragAgent import RAGClient
from mcpServer.client import MCPChatClient, TaskMCPClient
from mytool.gmail_listener import GmailAgent


current_client = getClient(
    "OpenAI",
    "qwen2.5:7b",
    0.7,
    "ollamaAI_memory.json",
    ["download_pdf_text"],
)
game_client = AutoGenGameClient()
crewai_client = CrewAIClient()
rag_client = RAGClient()
mcp_client = MCPChatClient("http://localhost:8001/sse")

try:
    gmail_agent = GmailAgent()
except Exception:
    gmail_agent = None


def load_mcp_tools(server_url):
    """Connect to an MCP server and format its available tools for the UI."""
    server_url = (server_url or "").strip()
    if not server_url:
        return "请输入 MCP Server 地址。"

    try:
        tools = asyncio.run(TaskMCPClient(server_url).list_tools())
    except Exception as exc:
        log(f"MCP Server 连接失败: {exc}")
        return f"**连接失败**：`{exc}`"

    if not tools:
        return "未发现可用的 MCP Tool。"

    tool_lines = ["### 可用的 MCP Tools", ""]
    for tool in tools:
        name = getattr(tool, "name", "未命名工具")
        description = getattr(tool, "description", None) or "无描述"
        tool_lines.append(f"- **{name}**：{description}")
    return "\n".join(tool_lines)

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

def specialChanged(backend, model, temperature, server_url):
    global current_client, mcp_client, gmail_agent
    if backend == "mcp专家":
        mcp_client = MCPChatClient(server_url or "http://localhost:8001/sse", model or "qwen2.5:7b")
        current_client = mcp_client
        log(f"切换聊天 client: MCP Server {mcp_client.server_url}")
        return "MCP 专家已切换。"
    if backend == "Gmail专家":
        if gmail_agent is None:
            try:
                gmail_agent = GmailAgent()
            except Exception as error:
                msg = (
                    "❌ Gmail 专家未能初始化。请先在当前环境中设置 GMAIL_EMAIL 和 GMAIL_APP_PASSWORD，"
                    "再重新选择 Gmail 专家。"
                )
                log(f"GmailAgent 初始化失败：{error}")
                return msg
        current_client = gmail_agent
        log("切换聊天 client: Gmail专家")
        return "Gmail 专家已启用。"
    if backend == "autoGenGame专家":
        current_client = game_client
        log("切换聊天 client: autoGenGame专家")
        return "autoGenGame 专家已启用。"
    if backend == "CrewAI专家":
        current_client = crewai_client
        log("切换聊天 client: CrewAI专家")
        return "CrewAI 专家已启用。"
    if backend == "RAG专家":
        current_client = rag_client
        log("切换聊天 client: RAG专家")
        return "RAG 专家已启用。"

    model = model or ("llama3.2:3b-instruct-fp16" if backend == "OpenAI" else "qwen2.5:7b")
    temperature = temperature if temperature is not None else 0.7
    memory_file = "openAI_memory.json" if backend == "OpenAI" else "ollamaAI_memory.json"
    current_client = getClient(
        backend,
        model,
        temperature,
        memory_file,
        ["download_pdf_text", "get_weather"],
    )
    log(f"切换聊天 client: {backend}, model={model}")
    return f"{backend} 专家已启用。"

def noChat(user_input_box, chatbot):
    user_input_box.submit(
        userInput,
        inputs=[user_input_box, chatbot],
        outputs=[chatbot,user_input_box],
    )

##### -----chat functions-----
def chatWithUrl(user_input_box, chatbot, model_dropdown, temperature_slider, top_p_slider):
    user_input_box.submit(
        respond_url,
        inputs=[user_input_box, chatbot, model_dropdown, temperature_slider, top_p_slider],
        outputs=[chatbot,user_input_box],
    )





def chatWithSelectedModel(user_input, history, model, temperature, top_p, backend, conversation_id):
   
        yield from current_client.streamChat(
            user_input,
            history,
            model,
            temperature,
            top_p,
            conversation_id,
        )

   

###### --------UI-------

with gr.Blocks(title="Rong's Workbuddy") as demo:
    gr.Markdown("# 🦙 Rong's Workbuddy")

    with gr.Row():
            # ---- 侧边栏设置 ----
            with gr.Column(scale=1, min_width=400):
                gr.Markdown("### ⚙️ 设置")

                tool_selections = gr.CheckboxGroup(
                                choices=['Get Weather', 'Safe Path', 'Read File', 'Write File', 'List Files',"GMail","Outlook","PDF","Text2Video","Photo Generator",
                                         "Wechat","Weibo","Twitter","Facebook","Instagram","YouTube","TikTok","LinkedIn"],
                                value=[],
                                label="Tools",
                            )

                gr.Markdown("### MCP Server")
                mcp_server_url = gr.Textbox(
                    value="http://localhost:8001/sse",
                    label="Server 地址",
                    placeholder="http://localhost:8001/sse",
                )
                mcp_connect_btn = gr.Button("🔌 连接并刷新 MCP Tools", variant="secondary")
                mcp_tools_display = gr.Markdown("尚未连接 MCP Server。")
                
                

                special_selector = gr.Radio(
                        choices=["Ollama", "OpenAI", "Gmail专家", "mcp专家", "autoGenGame专家", "CrewAI专家", "RAG专家"],
                    value="Ollama",
                    label="专家",
                    )

                teams_selector = gr.Radio(
                                    choices=["软件开发团队", "全域内容分发专家团" ,"用户体验架构师"],
                                    value="Ollama",
                                    label="团队",
                                    )
                                
                conversation_id = gr.Textbox(
                        value="default",
                        label="对话 ID",
                        info="重新打开时使用相同的 ID 继续对话",
                    )

                automations = gr.Textbox(
                                        value="自动化任务",
                                        label="自动化任务",
                                        info="自动化任务",
                                    )
                llm_btn = gr.Button("⚙️ 本地模型设置", variant="secondary")    
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
                with gr.Row():
                    copy_btn = gr.Button("📋 Copy")
                    like_btn = gr.Button("👍 Like")
                    dislike_btn = gr.Button("👎 Dislike")
                    clear_btn = gr.Button("🗑️ Clear")
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

    user_input_box.submit(
        chatWithSelectedModel,
        inputs=[
            user_input_box,
            chatbot,
            model_dropdown,
            temperature_slider,
            top_p_slider,
            special_selector,
            conversation_id,
        ],
        outputs=[chatbot, user_input_box],
    )

    tool_selections.change(
            toolChanged,
            inputs=[tool_selections],
            outputs=None
        )

    mcp_connect_btn.click(
        load_mcp_tools,
        inputs=[mcp_server_url],
        outputs=[mcp_tools_display],
    )

    special_selector.change(
            specialChanged,
            inputs=[special_selector, model_dropdown, temperature_slider, mcp_server_url],
            outputs=[task_status],
        )

    def copy_last_message(chatbot_history):
        if not chatbot_history:
            return "没有可复制的消息。"
        for message in reversed(chatbot_history):
            if isinstance(message, dict) and message.get("role") == "assistant":
                return str(message.get("content", ""))
        return str(chatbot_history[-1])

    def clear_chat():
        return [], ""

    copy_btn.click(
        copy_last_message,
        inputs=[chatbot],
        outputs=[task_status],
    )
    like_btn.click(
        lambda: "👍 已标记为有用。",
        inputs=None,
        outputs=[task_status],
    )
    dislike_btn.click(
        lambda: "👎 已标记为不满意。",
        inputs=None,
        outputs=[task_status],
    )
    clear_btn.click(
        clear_chat,
        inputs=None,
        outputs=[chatbot, user_input_box],
    )

if __name__ == "__main__":
    demo.queue().launch(theme=gr.themes.Soft())