from openai import OpenAI
from ronglog import log
import json
from pathlib import Path


MODEL = "llama3.2-vision:latest"


class localOpenAIClient:
    def __init__(self, modelName: str = MODEL, temperature: float = 0.7, memory_file: str = "chat_memory.json"):
        self.modelName = modelName
        self.temperature = temperature
        self.memory_file = Path(__file__).with_name(memory_file)
        self.llm = OpenAI(
            base_url="http://localhost:11434/v1",
            api_key="ollama",
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

    def chatWithOpenAIStream(
        self, user_input, history, model, temperature, top_p=1.0, conversation_id="default"
    ):
        conversation_id = str(conversation_id or "default").strip() or "default"
        history = self._get_history(conversation_id, history)
        history = [message for message in history if isinstance(message, dict)]
        request_history = history + [{"role": "user", "content": user_input}]
        response = self.llm.chat.completions.create(
            model=model or MODEL,
            messages=request_history,
            temperature=temperature if temperature is not None else self.temperature,
            top_p=top_p,
            stream=True,
        )

        history = request_history + [{"role": "assistant", "content": ""}]
        full_response = ""
        yield history, ""
        for event in response:
            if not event.choices:
                continue
            delta = event.choices[0].delta.content
            if delta:
                full_response += delta
                history[-1]["content"] = full_response
                memory = self._load_memory()
                memory[conversation_id] = history
                self._save_memory(memory)
                yield history, ""



openai_client = localOpenAIClient(modelName=MODEL, temperature=0.7)