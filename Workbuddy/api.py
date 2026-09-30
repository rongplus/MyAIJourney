"""
REST API for Workbuddy Agent backends.

Provides HTTP endpoints to chat with any of the available agent backends:
  - Ollama (LangChain ReAct agent with tools)
  - OpenAI (native function-calling agent)
  - MCP Expert (Model Context Protocol client)
  - AutoGen Game Expert (multi-agent game dev team)
  - CrewAI Expert (sequential software dev crew)
  - RAG Expert (retrieval-augmented generation)
  - Gmail Expert (Gmail inbox monitor + AI auto-reply)

Run:
    python api.py

Interactive docs:
    http://localhost:8000/docs

Example (curl):
    # List models
    curl http://localhost:8000/api/models

    # Non-streaming chat
    curl -X POST http://localhost:8000/api/chat \
      -H "Content-Type: application/json" \
      -d '{"message": "What is the weather in Toronto?", "backend": "Ollama", "model": "qwen2.5:7b"}'

    # Streaming chat (SSE)
    curl -N -X POST http://localhost:8000/api/chat/stream \
      -H "Content-Type: application/json" \
      -d '{"message": "Hello!", "backend": "Ollama"}'
"""

import json
import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from ronglog import log

# url_client only needs `requests` — safe to import at top level
from url_client import list_models


# ---------------------------------------------------------------------------
# Pydantic request / response models
# ---------------------------------------------------------------------------

class ChatMessage(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    message: str
    history: list[ChatMessage] = Field(default_factory=list)
    backend: str = "Ollama"
    model: str | None = None
    temperature: float = 0.7
    top_p: float = 0.9
    conversation_id: str = "default"
    mcp_server_url: str = "http://localhost:8001/sse"


class ChatResponse(BaseModel):
    response: str
    history: list[dict]


class HealthResponse(BaseModel):
    status: str
    ollama_reachable: bool


# ---------------------------------------------------------------------------
# Available backends
# ---------------------------------------------------------------------------

AVAILABLE_BACKENDS = [
    "Ollama",
    "OpenAI",
    "MCP Expert",
    "AutoGen Game Expert",
    "CrewAI Expert",
    "RAG Expert",
    "Gmail Expert",
]

# Backends that are singletons (don't depend on model / temperature)
_SINGLETON_BACKENDS = {
    "AutoGen Game Expert",
    "CrewAI Expert",
    "RAG Expert",
}


# ---------------------------------------------------------------------------
# Client registry — lazy-init, cached by (backend, model, temperature)
# ---------------------------------------------------------------------------

class ClientRegistry:
    """Manages agent client instances. Singleton backends are created once;
    model-based backends are cached by (backend, model, temperature)."""

    def __init__(self):
        self._singletons: dict[str, object] = {}
        self._model_clients: dict[tuple, object] = {}
        self._gmail_agent = None
        self._gmail_initialized = False

    # -- internal helpers --------------------------------------------------

    def _get_or_create_singleton(self, backend: str):
        if backend in self._singletons:
            return self._singletons[backend]

        if backend == "CrewAI Expert":
            from crewaiAgent import CrewAIClient
            client = CrewAIClient()
        elif backend == "AutoGen Game Expert":
            from autogenGame import AutoGenGameClient
            client = AutoGenGameClient()
        elif backend == "RAG Expert":
            from ragAgent import RAGClient
            client = RAGClient()
        else:
            raise ValueError(f"Unknown singleton backend: {backend}")

        self._singletons[backend] = client
        log(f"API: created singleton client for {backend}")
        return client

    def _get_or_create_model_client(self, backend, model, temperature):
        key = (backend, model, temperature)
        if key in self._model_clients:
            return self._model_clients[key]

        model = model or "qwen2.5:7b"
        memory_file = "openAI_memory.json" if backend == "OpenAI" else "ollamaAI_memory.json"
        tools_list = ["download_pdf_text", "get_weather"]

        # Lazy import — avoid loading crewai/autogen/etc. at startup
        if backend == "OpenAI":
            from localOpenAI import localOpenAIClient
            client = localOpenAIClient(
                modelName=model, temperature=temperature,
                memory_file=memory_file, custom_tools=tools_list,
            )
        else:
            # Ollama (default)
            from localChatOllama import localChatOllama
            client = localChatOllama(
                modelName=model, temperature=temperature,
                memory_file=memory_file, custom_tools=tools_list,
            )

        self._model_clients[key] = client
        log(f"API: created model client for {backend}, model={model}, temp={temperature}")
        return client

    def _get_gmail_agent(self):
        if self._gmail_initialized:
            return self._gmail_agent
        self._gmail_initialized = True
        try:
            from mytool.gmail_listener import GmailAgent
            self._gmail_agent = GmailAgent()
            log("API: GmailAgent initialized")
        except Exception as e:
            log(f"API: GmailAgent init failed: {e}")
            self._gmail_agent = None
        return self._gmail_agent

    # -- public API --------------------------------------------------------

    def get_client(self, req: ChatRequest):
        backend = req.backend

        if backend not in AVAILABLE_BACKENDS:
            raise HTTPException(400, f"Unknown backend: {backend}. Available: {AVAILABLE_BACKENDS}")

        if backend in _SINGLETON_BACKENDS:
            return self._get_or_create_singleton(backend)

        if backend == "Gmail Expert":
            agent = self._get_gmail_agent()
            if agent is None:
                raise HTTPException(
                    400,
                    "Gmail Expert not available. Set GMAIL_EMAIL and GMAIL_APP_PASSWORD environment variables.",
                )
            return agent

        if backend == "MCP Expert":
            from mcpServer.client import MCPChatClient
            return MCPChatClient(req.mcp_server_url, req.model or "qwen2.5:7b")

        # Ollama or OpenAI
        return self._get_or_create_model_client(backend, req.model, req.temperature)


# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------

registry = ClientRegistry()


@asynccontextmanager
async def lifespan(app: FastAPI):
    log("API: starting Workbuddy Agent API")
    yield
    log("API: shutting down")


app = FastAPI(
    title="Workbuddy Agent API",
    version="1.0.0",
    description="REST API to access Workbuddy AI agent backends via HTTP.",
    lifespan=lifespan,
)

# CORS — allow any origin so React / curl / Postman can call freely
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _history_to_dicts(history: list[ChatMessage]) -> list[dict]:
    """Convert Pydantic ChatMessage list to plain dicts for streamChat."""
    return [{"role": m.role, "content": m.content} for m in history]


def _extract_assistant_content(display_history) -> str:
    """Pull the latest assistant message content from a streamChat yield."""
    if not display_history or not isinstance(display_history, list):
        return ""
    last = display_history[-1]
    if isinstance(last, dict) and last.get("role") == "assistant":
        return str(last.get("content", ""))
    return ""


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@app.get("/api/health", response_model=HealthResponse)
def health():
    """Check API health and whether the Ollama service is reachable."""
    models = list_models()
    return HealthResponse(status="ok", ollama_reachable=len(models) > 0)


@app.get("/api/models")
def api_list_models():
    """List available Ollama models."""
    return {"models": list_models()}


@app.get("/api/backends")
def api_list_backends():
    """List all available agent backends."""
    return {"backends": AVAILABLE_BACKENDS}


@app.post("/api/chat", response_model=ChatResponse)
def api_chat(req: ChatRequest):
    """Non-streaming chat. Returns the final assistant response."""
    client = registry.get_client(req)
    history = _history_to_dicts(req.history)

    final_content = ""
    final_history = history

    for display_history, _ in client.streamChat(
        req.message,
        history,
        req.model,
        req.temperature,
        req.top_p,
        req.conversation_id,
    ):
        final_history = display_history
        final_content = _extract_assistant_content(display_history)

    return ChatResponse(response=final_content, history=final_history)


@app.post("/api/chat/stream")
def api_chat_stream(req: ChatRequest):
    """Streaming chat via Server-Sent Events (SSE).

    Each event is a JSON object with:
      - {"delta": "...", "content": "..."}  — incremental text
      - {"done": true, "content": "..."}   — final signal
    """

    client = registry.get_client(req)
    history = _history_to_dicts(req.history)

    def event_stream():
        prev_content = ""
        try:
            for display_history, _ in client.streamChat(
                req.message,
                history,
                req.model,
                req.temperature,
                req.top_p,
                req.conversation_id,
            ):
                content = _extract_assistant_content(display_history)
                if content and content != prev_content:
                    delta = content[len(prev_content):]
                    prev_content = content
                    yield f"data: {json.dumps({'delta': delta, 'content': content})}\n\n"
        except Exception as e:
            log(f"API stream error: {e}")
            yield f"data: {json.dumps({'error': str(e)})}\n\n"

        yield f"data: {json.dumps({'done': True, 'content': prev_content})}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("api:app", host="0.0.0.0", port=8000, reload=True)
