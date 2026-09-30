import os
import re
from typing import TypedDict

from langchain_ollama import ChatOllama
from langgraph.graph import END, START, StateGraph


OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "gpt-oss:latest")
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")


class SelfAskState(TypedDict):
	question: str
	subquestions: list[str]
	answers: list[str]
	current_index: int
	final_answer: str


def text_content(response) -> str:
	content = response.content
	return content if isinstance(content, str) else str(content)


def build_model() -> ChatOllama:
	return ChatOllama(
		model=OLLAMA_MODEL,
		base_url=OLLAMA_BASE_URL,
		temperature=0,
	)


def split_subquestions(text: str) -> list[str]:
	"""Extract numbered questions from the planner's response."""
	questions = []
	for line in text.splitlines():
		match = re.match(r"^\s*(?:\d+[.)]|[-*])\s*(.+?)\s*$", line)
		if match:
			questions.append(match.group(1).strip())
	return questions


def decompose_question(state: SelfAskState) -> dict:
	model = build_model()
	response = model.invoke(
		[
			(
				"system",
				"你是 Self-Ask 分析器。把用户的复杂问题拆成 2 到 4 个必要的子问题。"
				"只输出编号列表，每行一个问题，不要回答这些问题。",
			),
			("user", state["question"]),
		]
	)
	content = text_content(response)
	subquestions = split_subquestions(content)
	if not subquestions:
		subquestions = [state["question"]]
	return {"subquestions": subquestions[:4], "current_index": 0}


def answer_next_subquestion(state: SelfAskState) -> dict:
	index = state["current_index"]
	subquestion = state["subquestions"][index]
	previous_answers = "\n".join(
		f"子问题 {item + 1}：{question}\n回答：{state['answers'][item]}"
		for item, question in enumerate(state["subquestions"][:index])
	)
	model = build_model()
	response = model.invoke(
		[
			(
				"system",
				"你是 Self-Ask 子问题回答器。准确回答当前子问题。"
				"可以利用之前的回答，但不要臆造缺失事实。",
			),
			(
				"user",
				f"主问题：{state['question']}\n"
				f"之前的回答：\n{previous_answers or '无'}\n\n"
				f"当前子问题：{subquestion}",
			),
		]
	)
	return {
		"answers": state["answers"] + [text_content(response)],
		"current_index": index + 1,
	}


def has_more_subquestions(state: SelfAskState) -> str:
	if state["current_index"] < len(state["subquestions"]):
		return "answer_next"
	return "synthesize"


def synthesize_answer(state: SelfAskState) -> dict:
	facts = "\n\n".join(
		f"子问题 {index + 1}：{question}\n回答：{state['answers'][index]}"
		for index, question in enumerate(state["subquestions"])
	)
	model = build_model()
	response = model.invoke(
		[
			(
				"system",
				"你是最终回答助手。根据子问题和回答，整理出完整、准确、清晰的中文答案。"
				"不要提及 Self-Ask、子问题或内部推理过程。",
			),
			("user", f"主问题：{state['question']}\n\n已知信息：\n{facts}"),
		]
	)
	return {"final_answer": text_content(response)}


def build_self_ask_graph():
	graph = StateGraph(SelfAskState)
	graph.add_node("decompose", decompose_question)
	graph.add_node("answer_next", answer_next_subquestion)
	graph.add_node("synthesize", synthesize_answer)
	graph.add_edge(START, "decompose")
	graph.add_edge("decompose", "answer_next")
	graph.add_conditional_edges(
		"answer_next",
		has_more_subquestions,
		{"answer_next": "answer_next", "synthesize": "synthesize"},
	)
	graph.add_edge("synthesize", END)
	return graph.compile()


def run(question: str) -> None:
	agent = build_self_ask_graph()
	state = agent.invoke(
		{
			"question": question,
			"subquestions": [],
			"answers": [],
			"current_index": 0,
			"final_answer": "",
		}
	)
	print("\n拆分出的子问题：")
	for index, subquestion in enumerate(state["subquestions"], start=1):
		print(f"{index}. {subquestion}")
	print(f"\n最终答案：\n{state['final_answer']}")


if __name__ == "__main__":
	question = os.getenv(
		"SELF_ASK_QUESTION",
		"为什么团队应该使用 Git？请说明它解决的主要问题、核心工作方式和适用场景。",
	)
	print(f"模型：{OLLAMA_MODEL}")
	print(f"问题：{question}")
	run(question)
