# client_ollama.py
import json
import ollama
from ollama import chat, ChatResponse 
from fastmcp import Client as MCPClient
import asyncio
import sys,requests
from gradio import ChatMessage
from langchain.agents import AgentExecutor, create_openai_tools_agent
from langchain_community.agent_toolkits.load_tools import load_tools
# Configuration
OLLAMA_MODEL = "mistral:latest"
MCP_SERVER_URL = "http://127.0.0.1:8080/sse"
MCP_SERVER_URL2 = "http://127.0.0.1:8081/sse"

# ------------------------------------------------------------
# Step 1: Discover available tools from MCP server
# ------------------------------------------------------------
async def load_mcp_tools():
    """Connect to MCP server and get list of available tools"""
    try:
        ollama_tools = []
        async with MCPClient(MCP_SERVER_URL) as mcp:
            # Ask server: "What tools do you have?"
            tools_list = await mcp.list_tools()

            # Convert to format Ollama understands
            
            for tool in tools_list:
                ollama_tools.append({
                    "type": "function",
                    "function": {
                        "name": tool.name,
                        "description": tool.description,
                        "parameters": tool.inputSchema,
                    },
                })

        async with MCPClient(MCP_SERVER_URL2) as mcp:
            # Ask server: "What tools do you have?"
            tools_list = await mcp.list_tools()

            # Convert to format Ollama understands
            
            for tool in tools_list:
                ollama_tools.append({
                    "type": "function",
                    "function": {
                        "name": tool.name,
                        "description": tool.description,
                        "parameters": tool.inputSchema,
                    },
                })

        return ollama_tools
    except Exception as e:
        print(f"❌ ERROR connecting to MCP server: {e}")
        print(f"\nMake sure the server is running:")
        print("  python mcp_server.py")
        sys.exit(1)

# ------------------------------------------------------------
# Step 2: Execute a tool when AI requests it
# ------------------------------------------------------------
async def execute_tool(tool_name: str, arguments: dict):
    """Call a tool on the MCP server with given arguments"""
    try:
        async with MCPClient(MCP_SERVER_URL) as mcp:
            result = await mcp.call_tool(tool_name, arguments)
            return result
    except Exception as e:
        print(f"❌ ERROR executing tool {tool_name}: {e}")
        pass
    
    try:
        async with MCPClient(MCP_SERVER_URL2) as mcp:
            result = await mcp.call_tool(tool_name, arguments)
            return result
    except Exception as e:
        print(f"❌ ERROR executing tool {tool_name}: {e}")
        return {"error": f"Unknown tool: {tool_name}"}

# -----------------------------
# Chat Logic
# -----------------------------
async def agent_chat(user_message):

    tools = await load_mcp_tools()

    response = ollama.chat(
        model=OLLAMA_MODEL,
        messages=[
            {"role": "user", "content": user_message}
        ],
        tools=tools
    )

    messages = [
        {"role": "user", "content": user_message},
        response["message"]
    ]

    tool_output = ""

    # Tool calls
    if response["message"].get("tool_calls"):

        for tool_call in response["message"]["tool_calls"]:

            name = tool_call["function"]["name"]
            args = tool_call["function"]["arguments"]

            if isinstance(args, str):
                args = json.loads(args)

            result = await execute_tool(name, args)

            tool_output += f"\n🔧 {name} → {result}"

            messages.append({
                "role": "tool",
                "name": name,
                "content": json.dumps(result)
            })

    final = ollama.chat(
        model=OLLAMA_MODEL,
        messages=messages
    )

    return tool_output + "\n\n🤖 " + final["message"]["content"]


# -----------------------------
# Gradio Wrapper
# -----------------------------
def g_chat(message, history):

    response = asyncio.run(agent_chat(message))

    return response

def convert_messages(messages):
    converted = []

    for msg in messages:
        if hasattr(msg, "role"):
            converted.append({
                "role": msg.role,
                "content": msg.content
            })
        else:
            converted.append(msg)

    return converted
# -----------------------------
# Streaming Chat
# -----------------------------
async def stream_agent(user_message):

    tools = await load_mcp_tools()

    response = ollama.chat(
        model=OLLAMA_MODEL,
        messages=[
            {"role": "user", "content": user_message}
        ],
        tools=tools,
        stream=True
    )

    full_text = ""

    for chunk in response:

        if "message" in chunk and "content" in chunk["message"]:

            token = chunk["message"]["content"]
            full_text += token
            yield full_text

    # check tool calls after streaming
    response = ollama.chat(
        model=OLLAMA_MODEL,
        messages=[
            {"role": "user", "content": user_message}
        ],
        tools=tools
    )

    messages = [
        {"role": "user", "content": user_message},
        response["message"]
    ]

    if response["message"].get("tool_calls"):

        tool_text = "\n\n🔧 Running Tools...\n"
        yield full_text + tool_text

        for tool_call in response["message"]["tool_calls"]:

            name = tool_call["function"]["name"]
            args = tool_call["function"]["arguments"]

            if isinstance(args, str):
                args = json.loads(args)

            result = await execute_tool(name, args)

            tool_result = f"\n{name} → {result}"
            yield full_text + tool_text + tool_result

            messages.append({
                "role": "tool",
                "name": name,
                "content": json.dumps(result)
            })

        final_stream = ollama.chat(
            model=OLLAMA_MODEL,
            messages=messages,
            stream=True
        )

        final_text = ""

        for chunk in final_stream:

            if "message" in chunk:
                token = chunk["message"]["content"]
                final_text += token

                yield full_text + tool_text + final_text

async def interact_with_langchain_agent(prompt, messages):
    messages.append(ChatMessage(role="user", content=prompt))
    yield messages
    tools = await load_mcp_tools()
    response: ChatResponse = ollama.chat(
    model="mistral:latest",
    messages=convert_messages(messages),
    tools=[tools], # Python SDK supports passing tools as functions
    stream=True
    )
    
    async for chunk in response:
        
        if "output" in chunk:
            messages.append(ChatMessage(role="assistant", content=chunk["output"]))
            yield messages

    final = ollama.chat(
        model=OLLAMA_MODEL,
        messages=messages,
    )

    yield final["message"]["content"]
# -----------------------------
# Gradio Wrapper
# -----------------------------
def stream_chat(message, history):

    for text in asyncio.run(stream_agent(message)):
        yield text



OLLAMA_URL = "http://127.0.0.1:11434/api/chat"

def ollama_chat_stream(messages, model=OLLAMA_MODEL, temperature=0.2, num_ctx=None):
   """Yield streaming text chunks from Ollama /api/chat."""
   payload = {
       "model": model,
       "messages": messages,
       "stream": True,
       "options": {"temperature": float(temperature)}
   }
   if num_ctx:
       payload["options"]["num_ctx"] = int(num_ctx)
   with requests.post(OLLAMA_URL, json=payload, stream=True) as r:
       r.raise_for_status()
       for line in r.iter_lines():
           if not line:
               continue
           data = json.loads(line.decode("utf-8"))
           if "message" in data and "content" in data["message"]:
               yield data["message"]["content"]
           if data.get("done"):
               break
# ------------------------------------------------------------
# Step 3: Main conversation loop
# ------------------------------------------------------------
async def main():
    print("🔍 Loading MCP tools...")
    tools = await load_mcp_tools()
    print(f"✅ Loaded {len(tools)} tools:")
    for tool in tools:
        print(f"   - {tool['function']['name']}: {tool['function']['description']}")
    print()

    # The user's question
    user_msg = "Please greet John and then add 150 + 75. And get weather in Tokyo"
    print(f"👤 User: {user_msg}\n")

    # Send to Ollama with tools available
    try:
        response = ollama.chat(
            model=OLLAMA_MODEL,
            messages=[{"role": "user", "content": user_msg}],
            tools=tools,  # ← AI now knows these tools exist!
            stream=False,
        )
    except Exception as e:
        print(f"❌ ERROR calling Ollama: {e}")
        print(f"\nMake sure:")
        print(f"  1. Ollama is running (ollama serve)")
        print(f"  2. Model is installed (ollama pull {OLLAMA_MODEL})")
        sys.exit(1)

    # Check: Did AI want to use tools?
    if not response.get("message", {}).get("tool_calls"):
        print("🤖 AI answered directly (no tools needed):")
        print(response["message"]["content"])
        return

    # Process tool calls
    messages = [
        {"role": "user", "content": user_msg},
        response["message"]
    ]

    for tool_call in response["message"]["tool_calls"]:
        tool_name = tool_call["function"]["name"]
        args = tool_call["function"]["arguments"]

        # Parse if arguments are JSON string
        if isinstance(args, str):
            args = json.loads(args)

        print(f"🔧 Tool requested: {tool_name}")
        print(f"📝 Arguments: {args}")

        # Execute the tool
        tool_result = await execute_tool(tool_name, args)
        print(f"✅ Tool result: {tool_result}\n")

        # Add tool response to conversation
        messages.append({
            "role": "tool",
            "content": json.dumps(tool_result) if isinstance(tool_result, dict) else str(tool_result),
        })

    # Send tool results back to AI for final answer
    final = ollama.chat(
        model=OLLAMA_MODEL,
        messages=messages,
    )

    print("🤖 Final AI response:")
    print(final["message"]["content"])

if __name__ == "__main__":
    asyncio.run(main())