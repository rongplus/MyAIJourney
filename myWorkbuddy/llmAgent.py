"""Provider-agnostic LLM agent management."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Dict, Iterable, List, Mapping, Optional, Union
import inspect
import logging


ToolFunction = Callable[..., Any]


@dataclass
class Tool:
	name: str
	function: ToolFunction
	description: str = ""
	parameters: Mapping[str, Any] = field(default_factory=dict)
	enabled: bool = True

	def schema(self) -> Dict[str, Any]:
		return {
			"name": self.name,
			"description": self.description or inspect.getdoc(self.function) or "",
			"parameters": dict(self.parameters),
		}


@dataclass
class Message:
	role: str
	content: Any
	timestamp: datetime = field(default_factory=datetime.utcnow)
	metadata: Dict[str, Any] = field(default_factory=dict)


class Agent:
	"""Manage model settings, prompts, tools, conversation history, and calls."""

	def __init__(
		self,
		model_name: str = "gpt-4o-mini",
		system_prompt: str = "You are a helpful assistant.",
		*,
		tools: Optional[Iterable[Union[Tool, ToolFunction]]] = None,
		llm: Optional[Callable[..., Any]] = None,
		temperature: float = 0.2,
		max_tokens: Optional[int] = None,
		metadata: Optional[Mapping[str, Any]] = None,
		logger: Optional[logging.Logger] = None,
	) -> None:
		self.model_name = model_name
		self.system_prompt = system_prompt
		self.llm = llm
		self.temperature = temperature
		self.max_tokens = max_tokens
		self.metadata = dict(metadata or {})
		self.logger = logger or logging.getLogger(__name__)
		self.tools: Dict[str, Tool] = {}
		self.history: List[Message] = []
		for tool in tools or ():
			self.register_tool(tool)

	def register_tool(self, tool: Union[Tool, ToolFunction], **kwargs: Any) -> Tool:
		if isinstance(tool, Tool):
			spec = tool
		else:
			spec = Tool(name=kwargs.pop("name", tool.__name__), function=tool, **kwargs)
		if not spec.name or not callable(spec.function):
			raise ValueError("A tool must have a name and callable function")
		self.tools[spec.name] = spec
		return spec

	def remove_tool(self, name: str) -> None:
		self.tools.pop(name, None)

	def tool_schemas(self) -> List[Dict[str, Any]]:
		return [tool.schema() for tool in self.tools.values() if tool.enabled]

	def execute_tool(self, name: str, **arguments: Any) -> Any:
		tool = self.tools.get(name)
		if tool is None or not tool.enabled:
			raise KeyError(f"Unknown or disabled tool: {name}")
		return tool.function(**arguments)

	def add_message(self, role: str, content: Any, **metadata: Any) -> Message:
		message = Message(role, content, metadata=metadata)
		self.history.append(message)
		return message

	def clear_history(self) -> None:
		self.history.clear()

	def messages(self) -> List[Dict[str, Any]]:
		result = ([{"role": "system", "content": self.system_prompt}]
				  if self.system_prompt else [])
		result.extend({"role": m.role, "content": m.content} for m in self.history)
		return result

	def run(self, user_input: str, **options: Any) -> Any:
		if self.llm is None:
			raise RuntimeError("No llm callable configured")
		self.add_message("user", user_input)
		request = {
			"model": self.model_name,
			"messages": self.messages(),
			"tools": self.tool_schemas(),
			"temperature": self.temperature,
			"max_tokens": self.max_tokens,
			**options,
		}
		response = self.llm(**request)
		self.add_message("assistant", response)
		return response


AgentManager = Agent
