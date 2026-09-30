import os
from typing import TypedDict

from langchain_ollama import ChatOllama
from langgraph.graph import END, START, StateGraph


OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "gpt-oss:latest")
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
MAX_REVISIONS = 2


class ReflectionState(TypedDict):
	question: str
	draft: str
	critique: str
	answer: str
	revision_count: int


def text_content(response) -> str:
	"""Normalize an Ollama response to plain text."""
	content = response.content
	if isinstance(content, str):
		return content
	return str(content)


def build_model() -> ChatOllama:
	return ChatOllama(
		model=OLLAMA_MODEL,
		base_url=OLLAMA_BASE_URL,
		temperature=0,
	)


def generate_draft(state: ReflectionState) -> dict:
	model = build_model()
	response = model.invoke(
		[
			(
				"system",
				"你是一个中文技术方案作者。请先给出准确、具体、可执行的初稿。",
			),
			("user", state["question"]),
		]
	)
	return {"draft": text_content(response), "revision_count": 0}


def review_draft(state: ReflectionState) -> dict:
	model = build_model()
	response = model.invoke(
		[
			(
				"system",
				"你是严格的审查者。检查初稿的事实性、完整性、可执行性和表达。"
				"列出具体问题，并给出对应的修改建议。如果没有问题，请明确写‘没有需要修改的问题’。",
			),
			(
				"user",
				f"原问题：{state['question']}\n\n初稿：\n{state['draft']}",
			),
		]
	)
	return {"critique": text_content(response)}


def revise_draft(state: ReflectionState) -> dict:
	model = build_model()
	response = model.invoke(
		[
			(
				"system",
				"你是最终编辑。根据审查意见修订答案，不要提及内部审查过程。"
				"保留正确内容，修复具体问题，直接输出最终答案。",
			),
			(
				"user",
				f"原问题：{state['question']}\n"
				f"当前初稿：\n{state['draft']}\n\n"
				f"审查意见：\n{state['critique']}",
			),
		]
	)
	return {
		"draft": text_content(response),
		"revision_count": state["revision_count"] + 1,
	}


def should_revise(state: ReflectionState) -> str:
	if "没有需要修改的问题" in state["critique"]:
		return "finish"
	if state["revision_count"] >= MAX_REVISIONS:
		return "finish"
	return "revise"


def build_reflection_graph():
	graph = StateGraph(ReflectionState)
	graph.add_node("generate", generate_draft)
	graph.add_node("review", review_draft)
	graph.add_node("revise", revise_draft)
	graph.add_edge(START, "generate")
	graph.add_edge("generate", "review")
	graph.add_conditional_edges(
		"review",
		should_revise,
		{"revise": "revise", "finish": END},
	)
	graph.add_edge("revise", "review")
	return graph.compile()


def run(question: str) -> None:
	agent = build_reflection_graph()
	state = agent.invoke(
		{
			"question": question,
			"draft": "",
			"critique": "",
			"answer": "",
			"revision_count": 0,
		}
	)
	print(f"\n最终答案：\n{state['draft']}")
	print(f"\n修订次数：{state['revision_count']}")


if __name__ == "__main__":
	question = os.getenv(
		"REFLECTION_QUESTION",
		"请解释 Python 中的异步编程，并给出一个适合初学者的代码示例。",
	)
	print(f"模型：{OLLAMA_MODEL}")
	print(f"问题：{question}")
	run(question)


"""

"""