# mcp_server.py
import httpx
from fastmcp import FastMCP

# Create the MCP server instance
mcp = FastMCP("My Third MCP Server")


@mcp.tool()
def wikipedia(q):
    try:
        response = httpx.get(
            "https://en.wikipedia.org/w/api.php",
            params={
                "action": "query",
                "list": "search",
                "srsearch": q,
                "format": "json"
            },
            headers={
                "User-Agent": "LLMAgent/1.0 (learning-project)"
            },
            timeout=10
        )

        if response.status_code == 403:
            return "Wikipedia blocked automated access (403)."

        # Raise error on HTTP failures (403, 429, 500, etc.)
        response.raise_for_status()

        # Wikipedia sometimes returns empty content
        if not response.content:
            return "Wikipedia returned an empty response."

        data = response.json()

        results = data.get("query", {}).get("search", [])
        if not results:
            return f"No Wikipedia results found for '{q}'."

        return results[0]["snippet"]

    except httpx.HTTPError as e:
        return f"Wikipedia HTTP error: {e}"

    except ValueError:
        # JSON decoding failed
        return "Wikipedia returned non-JSON content."


if __name__ == "__main__":
    # Start the server
    mcp.run(transport="sse", port=8082)