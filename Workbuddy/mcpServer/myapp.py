# ui/app.py — User Layer

import sys
import queue
import threading
import gradio as gr

from client_ollama import chat, stream_chat,interact_with_langchain_agent,stream_agent,ollama_chat_stream

SYSTEM_PROMPT = "You are a helpful, crisp assistant. Prefer bullets when helpful."

OLLAMA_MODEL = "mistral:latest"

def chat_fn(message, history, temperature, num_ctx):
   msgs = [{"role":"system","content":SYSTEM_PROMPT}]
   for u, a in history:
       if u: msgs.append({"role":"user","content":u})
       if a: msgs.append({"role":"assistant","content":a})
   msgs.append({"role":"user","content": message})
   acc = ""
   try:
       for part in ollama_chat_stream(msgs, model=OLLAMA_MODEL, temperature=temperature, num_ctx=num_ctx or None):
           acc += part
           yield acc
   except Exception as e:
       yield f"⚠️ Error: {e}"

def main():
    with gr.Blocks(title="Ollama Chat (Colab)", fill_height=True) as demo:
        gr.Markdown("# 🦙 Ollama Chat (Colab)nSmall local-ish LLM via Ollama + Gradio.n")
        with gr.Row():
            temp = gr.Slider(0.0, 1.0, value=0.3, step=0.1, label="Temperature")
            num_ctx = gr.Slider(512, 8192, value=2048, step=256, label="Context Tokens (num_ctx)")
        chat = gr.Chatbot(height=460)
        msg = gr.Textbox(label="Your message", placeholder="Ask anything…", lines=3)
        clear = gr.Button("Clear")


        def user_send(m, h):
            m = (m or "").strip()
            if not m: return "", h
            return "", h + [[m, None]]


        def bot_reply(h, temperature, num_ctx):
            u = h[-1][0]
            stream = chat_fn(u, h[:-1], temperature, int(num_ctx))
            acc = ""
            for partial in stream:
                acc = partial
                h[-1][1] = acc
                yield h


        msg.submit(user_send, [msg, chat], [msg, chat]).then(bot_reply, [chat, temp, num_ctx], [chat])
        clear.click(lambda: None, None, chat)
    print("🌐 Launching Gradio ...")
    demo.launch(share=True)

if __name__ == "__main__":
    main()