from datetime import date, datetime
from pathlib import Path

import httpx
from langchain.agents import create_agent
from langchain_community.document_loaders import DirectoryLoader
from langchain_community.vectorstores import FAISS
from langchain_core.messages import AIMessage
from langchain_ollama import ChatOllama
from langchain_ollama.embeddings import OllamaEmbeddings
from langchain.tools import tool


OLLAMA_MODEL = "qwen2.5:7b"
OLLAMA_BASE_URL = "http://localhost:11434"


@tool
def get_current_date(_: str = "") -> str:
    """Return today's date in YYYY-MM-DD format."""
    return date.today().isoformat()


@tool
def get_current_time(_: str = "") -> str:
    """Return the current time in HH:MM:SS format."""
    return datetime.now().strftime("%H:%M:%S")


@tool
def calculate_days_until(future_date_str: str) -> str:
    """Calculate the number of days until a future YYYY-MM-DD date."""
    try:
        cleaned_date = future_date_str.strip().strip("'\"")
        future_date = datetime.strptime(cleaned_date, "%Y-%m-%d").date()
        days = (future_date - date.today()).days
        if days <= 0:
            return f"Error: The date {cleaned_date} is not in the future."
        return f"There are {days} days remaining until {cleaned_date}."
    except ValueError:
        return "Error: Invalid date format. Please use 'YYYY-MM-DD'."


@tool
def wikipedia(query: str) -> str:
    """Search Wikipedia and return a short summary."""
    try:
        response = httpx.get(
            "https://en.wikipedia.org/w/api.php",
            params={"action": "query", "list": "search", "srsearch": query, "format": "json"},
            headers={"User-Agent": "Workbuddy-RAG/1.0"},
            timeout=10,
        )
        if response.status_code == 403:
            return "Wikipedia blocked automated access."
        results = response.json().get("query", {}).get("search", [])
        return results[0]["snippet"] if results else "No Wikipedia results found."
    except Exception as error:
        return f"Wikipedia error: {error}"


class RAGClient:
    """RAG research client compatible with Workbuddy's streamChat interface."""

    def __init__(self, model_name=OLLAMA_MODEL, base_url=OLLAMA_BASE_URL, docs_folder=None):
        self.model_name = model_name
        self.base_url = base_url
        self.docs_folder = Path(
            docs_folder or Path(__file__).resolve().parent / "docs_to_load"
        )
        self._agent = None
        self._retriever = None

    def _ensure_agent(self):
        if self._agent is not None:
            return

        llm = ChatOllama(model=self.model_name, base_url=self.base_url, temperature=0)
        self._retriever = self._build_retriever()
        self._agent = create_agent(
            model=llm,
            tools=[get_current_date, get_current_time, calculate_days_until, wikipedia],
            system_prompt=(
                "You are a helpful research assistant. Use the supplied document context "
                "first, and clearly say when it does not contain the answer."
            ),
        )

    def _build_retriever(self):
        if not self.docs_folder.exists():
            return None
        documents = DirectoryLoader(
            str(self.docs_folder), glob="**/*.txt", show_progress=False
        ).load()
        if not documents:
            return None
        embeddings = OllamaEmbeddings(model=self.model_name, base_url=self.base_url)
        return FAISS.from_documents(documents, embeddings).as_retriever(search_kwargs={"k": 2})

    def run(self, user_input):
        self._ensure_agent()
        context = "No specific context found in documents for this query."
        if self._retriever is not None:
            documents = self._retriever.invoke(user_input)
            context = "\n\n".join(document.page_content for document in documents) or context

        prompt = f"Use this document context first:\n\n{context}\n\nQuestion:\n{user_input}"
        response = self._agent.invoke({"messages": [{"role": "user", "content": prompt}]})
        messages = response.get("messages", [])
        for message in reversed(messages):
            if isinstance(message, AIMessage) or getattr(message, "type", None) == "ai":
                return str(message.content)
        return str(messages[-1].content) if messages else "No response returned."

    def streamChat(
        self,
        user_input,
        history=None,
        model=None,
        temperature=None,
        top_p=None,
        conversation_id=None,
    ):
        del model, temperature, top_p, conversation_id
        display_history = list(history or [])
        display_history.append({"role": "user", "content": user_input})
        display_history.append({"role": "assistant", "content": "正在执行 RAG 检索..."})
        yield display_history, ""
        try:
            display_history[-1]["content"] = self.run(user_input)
        except Exception as error:
            display_history[-1]["content"] = f"❌ RAG 调用失败：{error}"
        yield display_history, ""


if __name__ == "__main__":
    client = RAGClient()
    print(client.run(input("Your question: ")))
