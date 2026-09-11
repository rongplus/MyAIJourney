from itertools import chain
from unittest import result

from langchain_ollama import ChatOllama, OllamaEmbeddings
from langchain_core.runnables.history import RunnableWithMessageHistory
from langchain_core.messages import HumanMessage
from langchain_core.chat_history import InMemoryChatMessageHistory
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from pymsgbox import prompt
from ronglog import log
# Per-session memory store




# Web 搜索（DuckDuckGo）
from ddgs import DDGS

def ddgs_search(q: str) -> str:
    items = []
    with DDGS() as s:
        for it in s.text(q.strip(), max_results=6):
            items.append(f"{it['title']} :: {it['href']} :: {it['body']}")
    return "\n".join(items)[:2000] or "no results"

# 浏览器渲染（获取真实页面内容）
from playwright.sync_api import sync_playwright

def browser_render(url: str) -> str:
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context()
        page = context.new_page()
        page.goto(url.strip(), wait_until="domcontentloaded", timeout=30000)
        html = page.content()
        context.close(); browser.close()
    return html[:4000]

# HTTP 端点获取
import requests

def http_fetch(url: str) -> str:
    r = requests.get(url.strip(), timeout=20)
    r.raise_for_status()
    return r.text[:2000]

# PDF 文本提取（可选）
import tempfile
from pathlib import Path

def download_pdf_text(url: str) -> str:
    r = requests.get(url.strip(), timeout=30)
    r.raise_for_status()
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
        tmp.write(r.content)
        path = Path(tmp.name)
    try:
        from langchain_community.document_loaders.pdf import PyPDFLoader
        pages = PyPDFLoader(str(path)).load()
        return "\n".join(p.page_content for p in pages)[:4000]
    finally:
        path.unlink(missing_ok=True)



from langchain_core.tools import StructuredTool

from rongtools import get_weather, safe_path, read_file, write_file, list_files, TOOLS

tools = [
    StructuredTool.from_function(ddgs_search, name="ddgs_search", description="Perform web search via DuckDuckGo."),
    StructuredTool.from_function(browser_render, name="browser_render", description="Render a webpage using headless Chromium and return HTML content."),
    StructuredTool.from_function(http_fetch, name="http_fetch", description="Fetch plain text or JSON from HTTP endpoints."),
    StructuredTool.from_function(download_pdf_text, name="download_pdf_text", description="Download a PDF file and extract its textual content."),
    StructuredTool.from_function(get_weather, name="get_weather", description="当你需要查询天气的时候， 调用此函数."),
]



from langchain_classic.agents import AgentType, initialize_agent



class localChatOllama:
    def __init__(self, modelName:str, temperature:int):
        self.llm = self.initLLM(modelName, temperature)
        self.agent = initialize_agent(
            tools=tools,
            llm=self.llm,
            agent=AgentType.ZERO_SHOT_REACT_DESCRIPTION,
            verbose=True,
            max_iterations=30,
            agent_kwargs={
                "system_message": (
                    "You are a ReAct analyst. Solve the task by interleaving Thought, Action, and Observation. "
                    "Do not treat search engine result pages (SERPs) as evidence. Always open and summarize at least one "
                    "content page, PDF, or API response before concluding. If evidence is insufficient, state 'Insufficient Evidence' "
                    "instead of hallucinating."
                )
            },
        )

        self.chat = RunnableWithMessageHistory(
            self.llm,
            self.get_session_history,
        )
        self.store = {}


        self.prompt = ChatPromptTemplate.from_messages([
            ("system", "你是一个基于本地知识库回答问题的 AI，请只根据以下内容回答：\n\n{context}"),
            MessagesPlaceholder(variable_name="chat_history"),
            ("human", "{question}")
        ])

        self.chain = self.prompt | self.llm

        self.chat_chain = RunnableWithMessageHistory(
            self.chain,
            self.get_session_history,
            input_messages_key="question",
            history_messages_key="chat_history"
        )

    def get_session_history(self,session_id: str):
        if session_id not in self.store:
            self.store[session_id] = InMemoryChatMessageHistory()
        return self.store[session_id]
            
    def initLLM(self, modelName: str, temperature: int):
        llm = ChatOllama(
            model=modelName,
            temperature=temperature,
            streaming=True,
        )
        return llm



    def _normalize_history(self, history):
        if not history:
            return []
        messages = []
        for item in history:
            if not isinstance(item, dict):
                continue
            role = str(item.get("role", "user")).lower()
            content = item.get("content", "")
            if not content:
                continue
            if role in {"user", "assistant", "system"}:
                messages.append({"role": role, "content": str(content)})
        return messages

    def _build_history_prompt(self, input_text: str, history=None) -> str:
        history = self._normalize_history(history or [])
        if not history:
            return input_text

        parts = []
        for msg in history:
            role = msg["role"]
            content = msg["content"].strip()
            if not content:
                continue
            if role == "user":
                parts.append(f"User: {content}")
            elif role == "assistant":
                parts.append(f"Assistant: {content}")
            else:
                parts.append(f"System: {content}")
        parts.append(f"User: {input_text.strip()}")
        return "\n\n".join(parts)

    def _extract_text(self, value):
        if value is None:
            return ""
        if isinstance(value, str):
            return value
        if isinstance(value, dict):
            return str(value.get("text") or value.get("content") or "")
        if isinstance(value, list):
            return "".join(self._extract_text(item) for item in value)
        return str(value)

    def chatWithChatOllama(self, input_text: str, history=None) -> str:
        prompt = self._build_history_prompt(input_text, history)
        result = self.agent.invoke({"input": prompt})
        return result.get("output")
        #print(output)


    def respond_local_ollama_stream(self, user_input, history, model, temperature, top_p):
        history = [
            {
                "role": message.get("role"),
                "content": str(message.get("content") or ""),
            }
            for message in (history or [])
            if isinstance(message, dict)
            and message.get("role") in {"user", "assistant"}
        ]
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
            prompt = self._build_history_prompt(user_input, history[:-1])
            for result in self.agent.stream({"input": prompt}):
                chunk = self._extract_text(result.get("output"))
                if not chunk:
                    continue
                full_response += chunk
                history[-1]["content"] = full_response
                yield history, ""
        except Exception as error:
            history[-1]["content"] = f"❌ 本地模型调用失败：{error}"
            yield history, ""

        
        


    def chatWithChatOllamaWithMemory(self, input_text: str, session_id: str, history=None) -> str:
        if session_id not in self.store:
            self.store[session_id] = []
        if history is not None:
            self.store[session_id] = self._normalize_history(history)
        previous = self.store[session_id]
        previous.append({"role": "user", "content": input_text})
        prompt = self._build_history_prompt(input_text, previous)
        result = self.agent.invoke({"input": prompt})
        previous.append({"role": "assistant", "content": result.get("output")})
        self.store[session_id] = previous
        return result.get("output")


    def chatWithChatOllamaWithMemoryStream(self, input_text: str, session_id: str, history=None):
        if session_id not in self.store:
            self.store[session_id] = []
        if history is not None:
            self.store[session_id] = self._normalize_history(history)
        previous = self.store[session_id]
        previous.append({"role": "user", "content": input_text})
        prompt = self._build_history_prompt(input_text, previous)
        for result in self.agent.stream({"input": prompt}):
            yield result.get("output")
        self.store[session_id] = previous + [{"role": "assistant", "content": ""}]

    def chatWithRunableWithMessageHistory(self,input_text: str, session_id: str) -> str:
        response = self.chat.invoke(
            [HumanMessage(content=input_text)],
            config={"configurable": {"session_id": session_id}}
        )

        return response.get("output")




if __name__ == "__main__":
    chatOllama = localChatOllama("qwen2.5:7b", 0.7)
    while True:
        user_input = input("User: ")
        if user_input.lower() == "exit":
            break
        print("AI:", end=" ")
        prompt = chatOllama._build_history_prompt(user_input)
        for result in chatOllama.agent.stream({"input": prompt}):
            chunk = result.get("output")
            if chunk:
                print(chunk, end="", flush=True)
        print("Done")