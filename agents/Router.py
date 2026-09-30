import os
from typing import TypedDict

from langchain_ollama import ChatOllama
from langgraph.graph import END, START, StateGraph


OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "gpt-oss:latest")
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
ROUTES = {"coding", "learning", "general"}


class RouterState(TypedDict):
	question: str
	route: str
	answer: str


def text_content(response) -> str:
	content = response.content
	return content if isinstance(content, str) else str(content)


def build_model() -> ChatOllama:
	return ChatOllama(
		model=OLLAMA_MODEL,
		base_url=OLLAMA_BASE_URL,
		temperature=0,
	)


def route_question(state: RouterState) -> dict:
	response = build_model().invoke(
		[
			(
				"system",
				"你是请求路由器。判断用户问题最适合交给哪个专家，只输出一个标签："
				"coding（写代码、调试、程序设计）、learning（解释知识、学习概念）、"
				"general（计划、建议及其他问题）。不要输出理由或标点。",
			),
			("user", state["question"]),
		]
	)
	route = text_content(response).strip().lower().strip("`'\".。 ")
	if route not in ROUTES:
		route = "general"
	print(f"[Router] 选择分支：{route}")
	return {"route": route}


def coding_agent(state: RouterState) -> dict:
	response = build_model().invoke(
		[
			(
				"system",
				"你是资深编程助手。用中文回答编程问题，优先给出准确、可运行的代码；"
				"调试时先解释原因，再给出小而明确的修复。",
			),
			("user", state["question"]),
		]
	)
	return {"answer": text_content(response)}


def learning_agent(state: RouterState) -> dict:
	response = build_model().invoke(
		[
			(
				"system",
				"你是耐心的技术导师。用中文循序渐进地解释概念，先讲直觉，再讲关键细节，"
			"必要时给出简短例子。",
			),
			("user", state["question"]),
		]
	)
	return {"answer": text_content(response)}


def general_agent(state: RouterState) -> dict:
	response = build_model().invoke(
		[
			(
				"system",
				"你是通用问题助手。用中文给出清晰、实用、结构合理的答复；"
			"不确定的信息要说明，不要臆造事实。",
			),
			("user", state["question"]),
		]
	)
	return {"answer": text_content(response)}


def build_router_graph():
	graph = StateGraph(RouterState)
	graph.add_node("router", route_question)
	graph.add_node("coding", coding_agent)
	graph.add_node("learning", learning_agent)
	graph.add_node("general", general_agent)
	graph.add_edge(START, "router")
	graph.add_conditional_edges(
		"router",
		lambda state: state["route"],
		{"coding": "coding", "learning": "learning", "general": "general"},
	)
	graph.add_edge("coding", END)
	graph.add_edge("learning", END)
	graph.add_edge("general", END)
	return graph.compile()


def run(question: str) -> None:
	app = build_router_graph()
	state = app.invoke(
		{"question": question, "route": "", "answer": ""}
	)
	print(f"\n[专家答复 / {state['route']}]\n{state['answer']}")


if __name__ == "__main__":
	question = os.getenv(
		"ROUTER_QUESTION",
		"请用 Python 写一个函数，判断字符串是否为回文。",
	)
	print(f"模型：{OLLAMA_MODEL}")
	print(f"问题：{question}")
	run(question)
