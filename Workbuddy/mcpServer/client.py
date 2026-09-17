"""Client for the FastMCP task server in app.py.

Start the server first with ``python app.py``. The client connects to the
server's SSE endpoint on localhost:8001.
"""

import argparse
import asyncio
from typing import Any

from fastmcp import Client


class TaskMCPClient:
    """Async client for the TaskTracker MCP server."""

    def __init__(self, server_url: str = "http://localhost:8001/sse"):
        self.server_url = server_url

    async def list_tools(self) -> list[Any]:
        async with Client(self.server_url) as client:
            return await client.list_tools()

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