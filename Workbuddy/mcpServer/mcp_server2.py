# mcp_server.py
from fastmcp import FastMCP

# Create the MCP server instance
mcp = FastMCP("My Second MCP Server")


@mcp.tool()
def get_weather(city: str) -> str:
    """Get weather information for a city"""
    # In real app, call a weather API
    # For demo, return fake data
    weather_data = {
        "New York": "Sunny, 72°F",
        "London": "Rainy, 15°C",
        "Tokyo": "Cloudy, 20°C"
    }
    return weather_data.get(city, f"Weather data not available for {city}")

@mcp.tool()
def save_note(title: str, content: str) -> str:
    """Save a note to a file"""
    import os
    filename = f"notes/{title.replace(' ', '_')}.txt"
    os.makedirs("notes", exist_ok=True)
    with open(filename, "w") as f:
        f.write(content)
    return f"Note saved to {filename}"

@mcp.tool()
def list_notes() -> list:
    """List all saved notes"""
    import os
    if not os.path.exists("notes"):
        return []
    return os.listdir("notes")

@mcp.tool()
def search_users(name: str) -> list:
    """Search for users by name"""
    # Connect to your database
    # For demo, return fake data
    users = [
        {"id": 1, "name": "Alice", "email": "alice@example.com"},
        {"id": 2, "name": "Bob", "email": "bob@example.com"}
    ]
    return [u for u in users if name.lower() in u["name"].lower()]



if __name__ == "__main__":
    # Start the server
    mcp.run(transport="sse", port=8081)