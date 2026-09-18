"""Client for the FastMCP task server in app.py.

Start the server first with ``python app.py``. The client connects to the
server's SSE endpoint on localhost:8001.
"""

import argparse
import asyncio
import json
from typing import Any

from fastmcp import Client
from openai import OpenAI


class TaskMCPClient:
    """Async client for the TaskTracker MCP server."""

    def __init__(self, server_url: str = "http://localhost:8001/sse"):
        self.server_url = server_url

    async def list_tools(self) -> list[Any]:
        async with Client(self.server_url) as client:
            return await client.list_tools()

    async def call_tool_by_name(self, name: str, arguments: dict[str, Any]) -> Any:
        async with Client(self.server_url) as client:
            return await client.call_tool(name, arguments)

    async def add_task(self, title: str, description: str = "") -> Any:
        async with Client(self.server_url) as client:
            return await client.call_tool(
                "add_task",
                {"title": title, "description": description},
            )

    async def complete_task(self, task_id: int) -> Any:
        async with Client(self.server_url) as client:
            return await client.call_tool("complete_task", {"task_id": task_id})

    async def delete_task(self, task_id: int) -> Any:
        async with Client(self.server_url) as client:
            return await client.call_tool("delete_task", {"task_id": task_id})

    async def get_tasks(self, resource: str = "tasks://all") -> str:
        async with Client(self.server_url) as client:
            contents = await client.read_resource(resource)
            return "\n".join(
                str(content.text)
                for content in contents
                if hasattr(content, "text")
            )

    async def smoke_test(self) -> None:
        """Verify the connection and exercise the task server."""
        tools = await self.list_tools()
        print("Available tools:", [tool.name for tool in tools])

        result = await self.add_task(
            "Learn MCP",
            "Build a task tracker with FastMCP",
        )
        print("Added task:", result)
        print("\nAll tasks:\n", await self.get_tasks())


class MCPChatClient:
    """Use an Ollama-compatible model to select and call remote MCP tools."""

    def __init__(self, server_url: str, model_name: str = "qwen2.5:7b"):
        self.server_url = server_url
        self.model_name = model_name
        self.llm = OpenAI(base_url="http://localhost:11434/v1", api_key="ollama")

    def _tool_schemas(self, tools: list[Any]) -> list[dict[str, Any]]:
        return [
            {
                "type": "function",
                "function": {
                    "name": tool.name,
                    "description": tool.description or "",
                    "parameters": getattr(tool, "input_schema", None)
                    or getattr(tool, "inputSchema", None)
                    or {"type": "object", "properties": {}},
                },
            }
            for tool in tools
        ]

    def _tool_result_text(self, result: Any) -> str:
        if hasattr(result, "content"):
            return "\n".join(
                str(item.text) if hasattr(item, "text") else str(item)
                for item in result.content
            )
        return str(result)

    def streamChat(self, user_input, history, model, temperature, top_p, conversation_id):
        messages = [
            {"role": item["role"], "content": str(item.get("content") or "")}
            for item in (history or [])
            if isinstance(item, dict) and item.get("role") in {"user", "assistant"}
        ]
        messages.append({"role": "user", "content": user_input})
        display_history = messages + [{"role": "assistant", "content": ""}]
        yield display_history, ""

        try:
            tools = asyncio.run(TaskMCPClient(self.server_url).list_tools())
            while True:
                response = self.llm.chat.completions.create(
                    model=model or self.model_name,
                    messages=messages,
                    temperature=temperature if temperature is not None else 0.7,
                    top_p=top_p,
                    tools=self._tool_schemas(tools),
                    stream=False,
                )
                message = response.choices[0].message
                tool_calls = message.tool_calls or []
                if not tool_calls:
                    display_history[-1]["content"] = message.content or ""
                    yield display_history, ""
                    break

                messages.append(message.model_dump(exclude_none=True))
                for tool_call in tool_calls:
                    arguments = json.loads(tool_call.function.arguments or "{}")
                    result = asyncio.run(
                        TaskMCPClient(self.server_url).call_tool_by_name(
                            tool_call.function.name, arguments
                        )
                    )
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "content": self._tool_result_text(result),
                    })
        except Exception as error:
            display_history[-1]["content"] = f"❌ MCP 调用失败：{error}"
            yield display_history, ""


async def main() -> None:
    parser = argparse.ArgumentParser(description="Test the TaskTracker MCP server")
    parser.add_argument(
        "--server-url",
        default="http://localhost:8001/sse",
        help="FastMCP SSE endpoint",
    )
    args = parser.parse_args()
    await TaskMCPClient(args.server_url).smoke_test()


if __name__ == "__main__":
    asyncio.run(main())