from openai import OpenAI
from ronglog import log
import json
from pathlib import Path
from langchain_core.tools import StructuredTool
from rongtools import get_weather, safe_path, read_file, write_file, list_files, TOOLS

MODEL = "llama3.2-vision:latest"


class localOpenAIClient:
    def __init__(self, modelName: str = MODEL, temperature: float = 0.7, memory_file: str = "open AI_memory.json"):
        self.modelName = modelName
        self.temperature = temperature
        self.memory_file = Path(__file__).with_name(memory_file)
        self.llm = OpenAI(
            base_url="http://localhost:11434/v1",
            api_key="ollama",
        )
        weather_tool = StructuredTool.from_function(
            get_weather,
            name="get_weather",
            description="查询指定城市的当前天气，包括温度、湿度、天气状况和风速。",
        )
        self.tools = {tool.name: tool for tool in [weather_tool, *TOOLS]}

    def _tool_schemas(self):
        schemas = []
        for tool in self.tools.values():
            schemas.append({
                "type": "function",
                "function": {
                    "name": tool.name,
                    "description": tool.description or "",
                    "parameters": tool.args_schema.model_json_schema(),
                },
            })
        return schemas

    def _execute_tool_call(self, tool_call):
        tool_name = tool_call.function.name
        tool = self.tools.get(tool_name)
        if tool is None:
            return f"未知工具：{tool_name}"

        try:
            arguments = json.loads(tool_call.function.arguments or "{}")
            return str(tool.invoke(arguments))
        except Exception as error:
            log(f"工具 {tool_name} 调用失败：{error}")
            return f"工具 {tool_name} 调用失败：{error}"

    def _stream_completion(self, messages, model, temperature, top_p):
        return self.llm.chat.completions.create(
            model=model or MODEL,
            messages=messages,
            temperature=temperature if temperature is not None else self.temperature,
            top_p=top_p,
            tools=self._tool_schemas(),
            stream=True,
        )

    def _load_memory(self):
        if not self.memory_file.exists():
            return {}
        try:
            with self.memory_file.open("r", encoding="utf-8") as file:
                memory = json.load(file)
            return memory if isinstance(memory, dict) else {}
        except (OSError, json.JSONDecodeError):
            return {}

    def _save_memory(self, memory):
        temporary_file = self.memory_file.with_suffix(".tmp")
        with temporary_file.open("w", encoding="utf-8") as file:
            json.dump(memory, file, ensure_ascii=False, indent=2)
        temporary_file.replace(self.memory_file)

    def _get_history(self, conversation_id, history):
        memory = self._load_memory()
        saved_history = memory.get(conversation_id, [])
        if isinstance(saved_history, list) and saved_history:
            return saved_history
        return list(history or [])

    def _chatbot_history(self, history):
        return [
            {
                "role": message["role"],
                "content": str(message.get("content") or ""),
            }
            for message in history
            if isinstance(message, dict)
            and message.get("role") in {"user", "assistant"}
        ]

    def chatWithOpenAIStream(
        self, user_input, history, model, temperature, top_p=1.0, conversation_id="default"
    ):
        conversation_id = str(conversation_id or "default").strip() or "default"
        model = model or self.modelName or MODEL
        history = self._get_history(conversation_id, history)
        history = [message for message in history if isinstance(message, dict)]
        request_history = history + [{"role": "user", "content": user_input}]
        display_history = self._chatbot_history(history) + [
            {"role": "user", "content": user_input},
            {"role": "assistant", "content": ""},
        ]
        yield display_history, ""

        try:
            while True:
                response = self._stream_completion(request_history, model, temperature, top_p)
                text = ""
                tool_calls = {}

                for event in response:
                    if not event.choices:
                        continue
                    delta = event.choices[0].delta
                    if delta.content:
                        text += delta.content
                        display_history[-1]["content"] = text
                        yield display_history, ""
                    for tool_delta in delta.tool_calls or []:
                        current = tool_calls.setdefault(
                            tool_delta.index,
                            {"id": "", "type": "function", "function": {"name": "", "arguments": ""}},
                        )
                        if tool_delta.id:
                            current["id"] = tool_delta.id
                        if tool_delta.function.name:
                            current["function"]["name"] += tool_delta.function.name
                        if tool_delta.function.arguments:
                            current["function"]["arguments"] += tool_delta.function.arguments

                if not tool_calls:
                    request_history.append({"role": "assistant", "content": text})
                    break

                assistant_message = {
                    "role": "assistant",
                    "content": text,
                    "tool_calls": [tool_calls[index] for index in sorted(tool_calls)],
                }
                request_history.append(assistant_message)
                for tool_call in assistant_message["tool_calls"]:
                    result = self._execute_tool_call(type("ToolCall", (), {
                        "function": type("Function", (), tool_call["function"])(),
                    })())
                    request_history.append({
                        "role": "tool",
                        "tool_call_id": tool_call["id"],
                        "content": result,
                    })

                display_history[-1]["content"] = ""
        except Exception as error:
            message = f"❌ OpenAI/Ollama 调用失败（模型：{model}）：{error}"
            display_history[-1]["content"] = message
            yield display_history, ""
            return

        memory = self._load_memory()
        memory[conversation_id] = request_history
        self._save_memory(memory)



openai_client = localOpenAIClient(modelName=MODEL, temperature=0.7)