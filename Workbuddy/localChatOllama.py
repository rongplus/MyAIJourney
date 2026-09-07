from itertools import chain
from unittest import result

from langchain_ollama import ChatOllama, OllamaEmbeddings
from langchain_core.runnables.history import RunnableWithMessageHistory
from langchain_core.messages import HumanMessage
from langchain_core.chat_history import InMemoryChatMessageHistory
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from pymsgbox import prompt
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

tools = [
    StructuredTool.from_function(ddgs_search, name="ddgs_search", description="Perform web search via DuckDuckGo."),
    StructuredTool.from_function(browser_render, name="browser_render", description="Render a webpage using headless Chromium and return HTML content."),
    StructuredTool.from_function(http_fetch, name="http_fetch", description="Fetch plain text or JSON from HTTP endpoints."),
    StructuredTool.from_function(download_pdf_text, name="download_pdf_text", description="Download a PDF file and extract its textual content."),
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



    def chatWithChatOllama(self, input_text: str) -> str:
        result = self.agent.invoke({"input": input_text})
        return result.get("output")
        #print(output)


    def chatWithChatOllamaStream(self, input_text: str):
        for result in self.agent.stream({"input": input_text}):
            yield result.get("output")


    def chatWithChatOllamaWithMemory(self, input_text: str, session_id: str) -> str:
        if session_id not in self.store:
            self.store[session_id] = []
        self.store[session_id].append({"role": "user", "content": input_text})
        result = self.agent.invoke({"input": input_text, "chat_history": self.store[session_id]})
        self.store[session_id].append({"role": "assistant", "content": result.get("output")})
        return result.get("output")


    def chatWithChatOllamaWithMemoryStream(self,input_text: str, session_id: str):
        if session_id not in self.store:
            self.store[session_id] = []
        self.store[session_id].append({"role": "user", "content": input_text})
        for result in self.agent.stream({"input": input_text, "chat_history": self.store[session_id]}):
            yield result.get("output")

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
        for chunk in chatOllama.chatWithChatOllamaStream(user_input):
            print(chunk, end="", flush=True)
        print("Done")