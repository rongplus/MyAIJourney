import os
from typing import TypedDict

from langchain_ollama import ChatOllama
from langgraph.graph import END, START, StateGraph


OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "gpt-oss:latest")
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")


class MultiAgentState(TypedDict):
	question: str
	analysis: str
	risks: str
	actions: str
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


def ask_role(instructions: str, question: str) -> str:
	response = build_model().invoke(
		[("system", instructions), ("user", question)]
	)
	return text_content(response)


def analyst_agent(state: MultiAgentState) -> dict:
	return {
		"analysis": ask_role(
			"你是研究分析员。用中文梳理问题的背景、关键事实和主要观点。"
			"区分已知信息与假设，不要编造数据。",
			state["question"],
		)
	}


def critic_agent(state: MultiAgentState) -> dict:
	return {
		"risks": ask_role(
			"你是严格的风险审查员。用中文指出问题中的歧义、潜在风险、"
			"反例和需要验证的假设；给出具体理由，不要只说‘存在风险’。",
			state["question"],
		)
	}


def planner_agent(state: MultiAgentState) -> dict:
	return {
		"actions": ask_role(
			"你是务实的执行顾问。针对用户问题用中文给出清晰、可操作的建议，"
			"按优先级组织步骤，并指出如何验证结果。",
			state["question"],
		)
	}


def editor_agent(state: MultiAgentState) -> dict:
	answer = ask_role(
		"你是最终编辑。整合分析、风险审查和行动建议，给出连贯、准确、"
		"可执行的中文答复。解决观点冲突，保留必要的不确定性；不要重复内容，"
		"也不要提及内部角色或协作过程。",
		f"用户问题：\n{state['question']}\n\n"
		f"分析员：\n{state['analysis']}\n\n"
		f"风险审查员：\n{state['risks']}\n\n"
		f"执行顾问：\n{state['actions']}",
	)
	return {"final_answer": answer}


def build_multi_agent_graph():
	graph = StateGraph(MultiAgentState)
	graph.add_node("analyst", analyst_agent)
	graph.add_node("critic", critic_agent)
	graph.add_node("planner", planner_agent)
	graph.add_node("editor", editor_agent)
	graph.add_edge(START, "analyst")
	graph.add_edge(START, "critic")
	graph.add_edge(START, "planner")
	graph.add_edge(["analyst", "critic", "planner"], "editor")
	graph.add_edge("editor", END)
	return graph.compile()


def run(question: str) -> None:
	team = build_multi_agent_graph()
	state = team.invoke(
		{
			"question": question,
			"analysis": "",
			"risks": "",
			"actions": "",
			"final_answer": "",
		}
	)
	print("\n[分析员]\n" + state["analysis"])
	print("\n[风险审查员]\n" + state["risks"])
	print("\n[执行顾问]\n" + state["actions"])
	print("\n[最终答复]\n" + state["final_answer"])


if __name__ == "__main__":
	question = os.getenv(
		"MULTI_AGENT_QUESTION",
		"我们想为一个小型开发团队引入 AI 代码助手。请分析收益、风险和落地步骤。",
	)
	print(f"模型：{OLLAMA_MODEL}")
	print(f"问题：{question}")
	run(question)
