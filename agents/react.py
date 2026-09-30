import os
from datetime import date

from langchain_core.tools import tool
from langchain_ollama import ChatOllama
from langgraph.prebuilt import create_react_agent


OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "gpt-oss:latest")
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")


@tool
def get_today() -> str:
	"""Return today's date in ISO format."""
	return date.today().isoformat()


@tool
def add_numbers(left: float, right: float) -> str:
	"""Add two numbers and return the result."""
	return str(left + right)


def build_agent():
	model = ChatOllama(
		model=OLLAMA_MODEL,
		base_url=OLLAMA_BASE_URL,
		temperature=0,
	)
	return create_react_agent(
		model=model,
		tools=[get_today, add_numbers],
		prompt=(
			"你是一个简洁可靠的助手。需要日期时使用 get_today，"
			"需要加法时使用 add_numbers。请用中文回答，并说明工具得到的结果。"
		),
	)


def run(question: str) -> None:
	agent = build_agent()
	result = agent.invoke(
		{"messages": [("user", question)]}
	)

	for message in result["messages"]:
		role = message.type
		if role == "tool":
			print(f"[tool/{message.name}] {message.content}")

	print(f"\n{result['messages'][-1].content}")


if __name__ == "__main__":
	question = os.getenv(
		"REACT_QUESTION",
		"今天是几号？另外请计算 12.5 加 7.5。根据今天天气计划下午活动",
	)
	print(f"模型: {OLLAMA_MODEL}")
	print(f"问题: {question}")
	run(question)

#简单选择建议：

#需要动态调用工具：ReAct
#任务步骤固定：Workflow
#任务很复杂：Plan-and-Execute
#需要检查质量：Reflection
#多种角色协作：Multi-Agent


#Plan-and-Execute
#Reflection
#Self-Ask
#Router
#Multi-Agent
#Workflow