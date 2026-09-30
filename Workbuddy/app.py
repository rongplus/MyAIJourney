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
        return "Please enter an MCP Server URL."

    try:
        tools = asyncio.run(TaskMCPClient(server_url).list_tools())
    except Exception as exc:
        log(f"MCP Server connection failed: {exc}")
        return f"**Connection failed**: `{exc}`"

    if not tools:
        return "No MCP Tools found."

    tool_lines = ["### Available MCP Tools", ""]
    for tool in tools:
        name = getattr(tool, "name", "unnamed tool")
        description = getattr(tool, "description", None) or "no description"
        tool_lines.append(f"- **{name}**: {description}")
    return "\n".join(tool_lines)

# Response the user input
def userInput(user_input, history):
    history = history or []
    # This version of the Chatbot component has removed the type parameter;
    # it only supports the messages format (i.e., {"role": "user", "content": "..."} dicts).
    history.append({"role": "user", "content": user_input})
    #Second is for return to the input box or user
    yield history, "Got it! Processing..."

def toolChanged(tool_selections):
    # Update the selected tools based on user selection
    """Record the user's selected tools."""
    log("Tool selection changed to: " + str(tool_selections or []))

def specialChanged(backend, model, temperature, server_url):
    global current_client, mcp_client, gmail_agent
    if backend == "MCP Expert":
        mcp_client = MCPChatClient(server_url or "http://localhost:8001/sse", model or "qwen2.5:7b")
        current_client = mcp_client
        log(f"Switching chat client: MCP Server {mcp_client.server_url}")
        return "MCP Expert activated."
    if backend == "Gmail Expert":
        if gmail_agent is None:
            try:
                gmail_agent = GmailAgent()
            except Exception as error:
                msg = (
                    "Failed to initialize Gmail Expert. Please set GMAIL_EMAIL and GMAIL_APP_PASSWORD "
                    "in the current environment, then select Gmail Expert again."
                )
                log(f"GmailAgent initialization failed: {error}")
                return msg
        current_client = gmail_agent
        log("Switching chat client: Gmail Expert")
        return "Gmail Expert activated."
    if backend == "AutoGen Game Expert":
        current_client = game_client
        log("Switching chat client: AutoGen Game Expert")
        return "AutoGen Game Expert activated."
    if backend == "CrewAI Expert":
        current_client = crewai_client
        log("Switching chat client: CrewAI Expert")
        return "CrewAI Expert activated."
    if backend == "RAG Expert":
        current_client = rag_client
        log("Switching chat client: RAG Expert")
        return "RAG Expert activated."

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
    log(f"Switching chat client: {backend}, model={model}")
    return f"{backend} Expert activated."

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
    gr.Markdown("# Workbuddy")

    with gr.Row():
            # ---- Sidebar Settings ----
            with gr.Column(scale=1, min_width=400):
                gr.Markdown("### Settings")

                tool_selections = gr.CheckboxGroup(
                                choices=['Get Weather', 'Safe Path', 'Read File', 'Write File', 'List Files',"GMail","Outlook","PDF","Text2Video","Photo Generator",
                                         "Wechat","Weibo","Twitter","Facebook","Instagram","YouTube","TikTok","LinkedIn"],
                                value=[],
                                label="Tools",
                            )

                gr.Markdown("### MCP Server")
                mcp_server_url = gr.Textbox(
                    value="http://localhost:8001/sse",
                    label="Server URL",
                    placeholder="http://localhost:8001/sse",
                )
                mcp_connect_btn = gr.Button("Connect & Refresh MCP Tools", variant="secondary")
                mcp_tools_display = gr.Markdown("MCP Server not connected yet.")
                


                special_selector = gr.Radio(
                        choices=["Ollama", "OpenAI", "Gmail Expert", "MCP Expert", "AutoGen Game Expert", "CrewAI Expert", "RAG Expert"],
                    value="Ollama",
                    label="Expert",
                    )

                teams_selector = gr.Radio(
                                    choices=["Software Dev Team", "Content Distribution Team" ,"UX Architect Team"],
                                    value="Ollama",
                                    label="Team",
                                    )
                                
                conversation_id = gr.Textbox(
                        value="default",
                        label="Conversation ID",
                        info="Use the same ID to continue the conversation when reopened",
                    )

                automations = gr.Textbox(
                                        value="Automation tasks",
                                        label="Automation Tasks",
                                        info="Automation tasks",
                                    )
                llm_btn = gr.Button("Local Model Settings", variant="secondary")    
                # ---- Advanced Settings popup panel (hidden by default) ----
                llm_panel = gr.Group(visible=False)
                with llm_panel:
                    gr.Markdown("### Local LLaMA Settings (takes effect after saving)")
                    initial_models = list_models()
                    
                    model_dropdown = gr.Dropdown(
                        label="Select Model",
                        choices=initial_models,
                        value=get_default_model(initial_models),
                    )
                    if not initial_models:
                        gr.Markdown(
                            "No installed models detected. Please make sure the local Ollama service is running, "
                            "and that you have run `ollama pull <model_name>`, then click \"Refresh Model List\" below."
                        )
        
                    temperature_slider = gr.State(0.7)   # Actual value, written from the popup
                    top_p_slider = gr.State(0.9)          # Actual value, written from the popup
                    
    
                    adv_temperature = gr.Slider(
                        label="Temperature",
                        minimum=0.0, maximum=1.5, value=0.7, step=0.05,
                        info="Higher = more creative, lower = more deterministic and conservative",
                    )
                    adv_top_p = gr.Slider(
                        label="Top-P",
                        minimum=0.1, maximum=1.0, value=0.9, step=0.05,
                        info="Nucleus sampling threshold, controls candidate word range",
                    )
    
                    with gr.Row():
                        adv_reset_btn = gr.Button("Reset to Default", variant="secondary")
                        adv_save_btn = gr.Button("Save & Close", variant="primary")
                

            # ---- Chat Window ----

            with gr.Column(scale=4, min_width=600):
                gr.Markdown("### Chat Window")
                chatbot = gr.Chatbot(
                                label="Conversation",
                                height=560,
                                buttons=["copy", "copy_all"],
                            )
                task_status = gr.Markdown()
                with gr.Row():
                    copy_btn = gr.Button("Copy")
                    like_btn = gr.Button("Like")
                    dislike_btn = gr.Button("Dislike")
                    clear_btn = gr.Button("Clear")
                user_input_box = gr.Textbox(
                    placeholder="Type a message...",
                    show_label=False,
                    lines=1,
                )
    # Advanced Settings popup: read current values from State when opening
    llm_btn.click(
        lambda t, p: (gr.update(visible=True), gr.update(value=t), gr.update(value=p)),
        inputs=[temperature_slider, top_p_slider],
        outputs=[llm_panel, adv_temperature, adv_top_p],
    )
    # Save: write the popup values back to State and close the panel
    adv_save_btn.click(
        lambda t, p: (gr.update(visible=False), t, p),
        inputs=[adv_temperature, adv_top_p],
        outputs=[llm_panel, temperature_slider, top_p_slider],
    )
    
    # Reset to default
    adv_reset_btn.click(
        lambda: (gr.update(value=0.7), gr.update(value=0.9)),
        inputs=None,
        outputs=[adv_temperature, adv_top_p],
    )

    
    # Event binding: chat
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
            return "No message to copy."
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
        lambda: "Marked as helpful.",
        inputs=None,
        outputs=[task_status],
    )
    dislike_btn.click(
        lambda: "Marked as not helpful.",
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
