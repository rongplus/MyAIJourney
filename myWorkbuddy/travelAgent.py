from typing import Literal

from langchain_openai import ChatOpenAI
from langchain_core.tools import tool
from langgraph.graph import (
    StateGraph,
    MessagesState,
    START,
    END,
)
from langgraph.prebuilt import ToolNode
from langgraph.checkpoint.memory import InMemorySaver


@tool
def multiply(a: int, b: int) -> int:
    """计算两个整数的乘积。"""
    return a * b


tools = [multiply]


def call_model(state: MessagesState):
    llm = state.get("_llm")
    if llm is None:
        raise RuntimeError("Travel Agent LLM is not configured")

    messages = [
        {
            "role": "system",
            "content": (
                "你是一个严谨的 AI 助手。"
                "遇到乘法计算时，必须调用工具，"
                "不要自己猜测计算结果。"
            ),
        },
        *state["messages"],
    ]

    response = llm.bind_tools(tools).invoke(messages)

    return {
        "messages": [response]
    }


def route(
    state: MessagesState,
) -> Literal["tools", "end"]:

    last_message = state["messages"][-1]

    if last_message.tool_calls:
        return "tools"

    return "end"


def build_travel_agent(model: str = "gpt-5.4-mini", temperature: float = 0):
    """Build the travel graph without making a request during import."""
    llm = ChatOpenAI(model=model, temperature=temperature)

    builder = StateGraph(MessagesState)

    def model_node(state: MessagesState):
        return call_model({**state, "_llm": llm})

    builder.add_node("model", model_node)
    builder.add_node("tools", ToolNode(tools))
    builder.add_edge(START, "model")
    builder.add_conditional_edges(
        "model",
        route,
        {"tools": "tools", "end": END},
    )
    builder.add_edge("tools", "model")
    return builder.compile(checkpointer=InMemorySaver())


_travel_agent = None


def run_travel_agent_sync(
    user_input: str,
    thread_id: str = "mcp-travel-user",
    model: str = "gpt-5.4-mini",
) -> str:
    """Run MCP-Travel with persistent conversation memory for one thread."""
    global _travel_agent
    if _travel_agent is None:
        _travel_agent = build_travel_agent(model=model)

    result = _travel_agent.invoke(
        {"messages": [{"role": "user", "content": user_input}]},
        {"configurable": {"thread_id": thread_id}},
    )
    return str(result["messages"][-1].content)


def clear_travel_agent_history() -> None:
    """Reset the in-memory MCP-Travel graph and its conversation history."""
    global _travel_agent
    _travel_agent = None