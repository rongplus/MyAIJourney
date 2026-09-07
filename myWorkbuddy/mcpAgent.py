"""MCP Agent — LangGraph ReAct agent that connects to a Gmail MCP server.

Architecture:
  1. Native MCP SDK (``mcp.ClientSession`` + ``mcp.client.stdio.stdio_client``)
     connects to ``gmail_mcp_server.py`` via **stdio** transport — the server
     runs as a subprocess.  No ``langchain-mcp-adapters`` dependency.
  2. MCP tools are wrapped as LangChain ``StructuredTool`` instances so they
     work with ``create_react_agent``.
  3. ``create_react_agent`` (from langgraph.prebuilt) wraps an LLM + those tools
     into a ReAct graph with automatic tool-calling loops.
  4. A background asyncio event loop (``_AsyncLoopRunner``) keeps the MCP client
     connection alive across synchronous ``invoke`` calls — necessary because
     MCP tool calls are async and the client must persist.

Public API (mirrors travelAgent.py):
  - ``run_mcp_agent_sync(user_input, model)`` → str
  - ``clear_mcp_agent_history()``
"""
import sys
import os
import asyncio
import threading
from typing import Tuple, Type, Optional

from langchain_ollama import ChatOllama
from langgraph.prebuilt import create_react_agent
from langgraph.checkpoint.memory import InMemorySaver
from langchain_core.tools import StructuredTool
from pydantic import BaseModel, create_model

from mcp import ClientSession
from mcp.client.stdio import stdio_client, StdioServerParameters

_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_GMAIL_SERVER_SCRIPT = os.path.join(_THIS_DIR, "gmail_mcp_server.py")
_DEFAULT_MODEL = "qwen2.5:7b"

_SYSTEM_PROMPT = (
    "You are a helpful assistant with access to Gmail tools via MCP.\n"
    "You can send emails, search emails, read specific emails, and list labels.\n"
    "When the user asks about email tasks, use the appropriate Gmail tool.\n"
    "Always explain what you did after using a tool.\n"
    "If a tool returns an error about missing OAuth credentials, explain to the "
    "user how to set up Gmail OAuth (see the tool's error message for instructions)."
)


# ---------------------------------------------------------------------------
# JSON-Schema → Pydantic model converter
# ---------------------------------------------------------------------------

_TYPE_MAP = {
    "string": str,
    "integer": int,
    "number": float,
    "boolean": bool,
    "array": list,
    "object": dict,
}


def _json_schema_to_pydantic(schema: dict, model_name: str) -> Type[BaseModel]:
    """Convert a JSON Schema dict (from MCP tool inputSchema) to a Pydantic model."""
    properties = schema.get("properties", {})
    required = set(schema.get("required", []))

    fields = {}
    for prop_name, prop_schema in properties.items():
        json_type = prop_schema.get("type", "string")
        py_type = _TYPE_MAP.get(json_type, str)

        if prop_name in required:
            fields[prop_name] = (py_type, ...)
        else:
            default = prop_schema.get("default")
            fields[prop_name] = (py_type, default)

    return create_model(model_name, **fields)  # type: ignore[call-overload]


# ---------------------------------------------------------------------------
# MCP tool → LangChain StructuredTool wrapper
# ---------------------------------------------------------------------------

def _create_langchain_tool(session: ClientSession, mcp_tool) -> StructuredTool:
    """Wrap a single MCP tool as a LangChain StructuredTool.

    The tool's ``_arun`` calls ``session.call_tool()`` on the live MCP session.
    """
    tool_name = mcp_tool.name
    tool_desc = mcp_tool.description or tool_name
    args_schema = _json_schema_to_pydantic(
        mcp_tool.inputSchema, f"{tool_name}_args"
    )

    async def _arun(**kwargs) -> str:
        result = await session.call_tool(tool_name, arguments=kwargs)
        if result.content and len(result.content) > 0:
            content = result.content[0]
            return content.text if hasattr(content, "text") else str(content)
        return "No response content returned from tool."

    def _sync(**kwargs):
        raise RuntimeError(
            f"MCP tool '{tool_name}' only supports async execution (ainvoke)."
        )

    return StructuredTool(
        name=tool_name,
        description=tool_desc,
        func=_sync,
        coroutine=_arun,
        args_schema=args_schema,
    )


# ---------------------------------------------------------------------------
# Background asyncio loop runner
# ---------------------------------------------------------------------------

class _AsyncLoopRunner:
    """Run a persistent asyncio event loop in a daemon thread.

    The MCP client's stdio connections are async — they need a live event
    loop to function.  This runner lets synchronous code submit coroutines
    to that loop and block until they finish.
    """

    def __init__(self):
        self.loop = asyncio.new_event_loop()
        self._thread = threading.Thread(target=self._run_forever, daemon=True)
        self._thread.start()

    def _run_forever(self):
        asyncio.set_event_loop(self.loop)
        self.loop.run_forever()

    def run(self, coro, timeout: float = 300):
        """Submit *coro* to the background loop and block for *timeout* seconds."""
        future = asyncio.run_coroutine_threadsafe(coro, self.loop)
        return future.result(timeout=timeout)

    def shutdown(self):
        """Stop the loop and wait for the thread to exit."""
        self.loop.call_soon_threadsafe(self.loop.stop)
        self._thread.join(timeout=5)


_runner = _AsyncLoopRunner()
_lock = threading.Lock()

# Module-level state — kept alive so the MCP subprocess stays connected
_mcp_agent = None
_mcp_session: Optional[ClientSession] = None
_stdio_cm = None      # async context manager for stdio_client
_session_cm = None    # async context manager for ClientSession


# ---------------------------------------------------------------------------
# Agent construction
# ---------------------------------------------------------------------------

async def _build_mcp_agent_async(model: str):
    """Connect to the Gmail MCP server and build a LangGraph ReAct agent.

    Uses native MCP SDK (``stdio_client`` + ``ClientSession``) — no
    ``langchain-mcp-adapters`` required.  The context managers are entered
    manually so the connection persists across multiple ``invoke`` calls.
    """
    global _stdio_cm, _session_cm, _mcp_session

    server_params = StdioServerParameters(
        command=sys.executable,
        args=[_GMAIL_SERVER_SCRIPT],
    )

    # --- Enter context managers manually (keep alive until cleanup) ----------
    _stdio_cm = stdio_client(server_params)
    read, write = await _stdio_cm.__aenter__()

    try:
        _session_cm = ClientSession(read, write)
        _mcp_session = await _session_cm.__aenter__()
        await _mcp_session.initialize()
    except Exception:
        # If session setup fails, clean up the stdio client
        await _stdio_cm.__aexit__(None, None, None)
        _stdio_cm = None
        raise

    # --- Discover tools from the MCP server ---------------------------------
    tools_result = await _mcp_session.list_tools()

    if not tools_result.tools:
        raise RuntimeError(
            "Gmail MCP server returned no tools. Check that "
            f"{_GMAIL_SERVER_SCRIPT} can start without errors."
        )

    # --- Wrap MCP tools as LangChain StructuredTools -------------------------
    langchain_tools = [
        _create_langchain_tool(_mcp_session, t) for t in tools_result.tools
    ]

    # --- Build the ReAct agent -----------------------------------------------
    llm = ChatOllama(model=model, temperature=0)

    try:
        # langgraph >= 0.2.39 supports `prompt` as a plain string
        agent = create_react_agent(
            llm,
            langchain_tools,
            prompt=_SYSTEM_PROMPT,
            checkpointer=InMemorySaver(),
        )
    except TypeError:
        # Fallback for older langgraph versions (prompt → state_modifier)
        agent = create_react_agent(
            llm,
            langchain_tools,
            state_modifier=_SYSTEM_PROMPT,
            checkpointer=InMemorySaver(),
        )

    return agent


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def run_mcp_agent_sync(
    user_input: str,
    thread_id: str = "mcp-user",
    model: str = _DEFAULT_MODEL,
) -> str:
    """Run the MCP agent and return its final response as a string.

    On the first call, the agent (and its MCP client connection) is lazily
    built.  Subsequent calls reuse the same connection with persistent
    conversation memory (per *thread_id*).
    """
    global _mcp_agent

    # Lazy init — thread-safe
    with _lock:
        if _mcp_agent is None:
            _mcp_agent = _runner.run(_build_mcp_agent_async(model))

    async def _invoke() -> str:
        result = await _mcp_agent.ainvoke(
            {"messages": [{"role": "user", "content": user_input}]},
            {"configurable": {"thread_id": thread_id}},
        )
        return str(result["messages"][-1].content)

    return _runner.run(_invoke())


def clear_mcp_agent_history() -> None:
    """Reset the MCP agent — closes the server connection and clears memory.

    The agent will be rebuilt (and the MCP server relaunched) on the next
    ``run_mcp_agent_sync`` call.
    """
    global _mcp_agent, _mcp_session, _stdio_cm, _session_cm

    with _lock:
        if _mcp_session is not None or _stdio_cm is not None:
            async def _close():
                # Close session first (reverse order of acquisition)
                if _session_cm is not None:
                    try:
                        await _session_cm.__aexit__(None, None, None)
                    except Exception:
                        pass
                # Then close stdio client (terminates the subprocess)
                if _stdio_cm is not None:
                    try:
                        await _stdio_cm.__aexit__(None, None, None)
                    except Exception:
                        pass

            _runner.run(_close())

        _mcp_agent = None
        _mcp_session = None
        _stdio_cm = None
        _session_cm = None
