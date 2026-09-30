import os
from typing import TypedDict

from langchain_ollama import ChatOllama
from langgraph.graph import END, START, StateGraph


OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "gpt-oss:latest")
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")


class WorkflowState(TypedDict):
	topic: str
	audience: str
	analysis: str
	outline: str
	draft: str
	review: str
	final_report: str


def text_content(response) -> str:
	content = response.content
	return content if isinstance(content, str) else str(content)


def build_model() -> ChatOllama:
	return ChatOllama(
		model=OLLAMA_MODEL,
		base_url=OLLAMA_BASE_URL,
		temperature=0,
	)


def ask_model(instructions: str, context: str) -> str:
	response = build_model().invoke(
		[("system", instructions), ("user", context)]
	)
	return text_content(response)


def analyze_task(state: WorkflowState) -> dict:
	analysis = ask_model(
		"你是内容策划。分析主题的目标、需要覆盖的重点和读者可能关心的问题。"
		"只总结任务要求，不要开始写正文。",
		f"主题：{state['topic']}\n目标读者：{state['audience']}",
	)
	print("[1/5] 已完成任务分析")
	return {"analysis": analysis}


def create_outline(state: WorkflowState) -> dict:
	outline = ask_model(
		"你是内容编辑。根据任务分析设计一个逻辑清楚、层次适当的中文提纲。"
		"只输出提纲，包含标题和主要章节。",
		f"主题：{state['topic']}\n目标读者：{state['audience']}\n"
		f"任务分析：\n{state['analysis']}",
	)
	print("[2/5] 已完成提纲")
	return {"outline": outline}


def write_draft(state: WorkflowState) -> dict:
	draft = ask_model(
		"你是中文作者。严格依据给定提纲撰写清晰、准确、适合目标读者的初稿。"
		"不要编造统计数据、来源或具体事实；不确定处应谨慎表述。",
		f"主题：{state['topic']}\n目标读者：{state['audience']}\n"
		f"提纲：\n{state['outline']}",
	)
	print("[3/5] 已完成初稿")
	return {"draft": draft}


def review_draft(state: WorkflowState) -> dict:
	review = ask_model(
		"你是严格的质量审查员。检查初稿是否回应主题、符合提纲和读者需求，"
		"并检查逻辑、清晰度、遗漏及无依据的事实。列出具体问题和修改建议；"
		"若没有明显问题，请明确写‘没有需要修改的问题’。",
		f"主题：{state['topic']}\n提纲：\n{state['outline']}\n\n初稿：\n{state['draft']}",
	)
	print("[4/5] 已完成质量检查")
	return {"review": review}


def finalize_report(state: WorkflowState) -> dict:
	final_report = ask_model(
		"你是最终编辑。根据审查意见修订初稿，保留正确且有用的内容，"
		"修复指出的问题，输出可以直接交付的最终稿。不要提及审查过程。",
		f"主题：{state['topic']}\n目标读者：{state['audience']}\n"
		f"初稿：\n{state['draft']}\n\n审查意见：\n{state['review']}",
	)
	print("[5/5] 已完成最终稿")
	return {"final_report": final_report}


def build_workflow():
	graph = StateGraph(WorkflowState)
	graph.add_node("analyze", analyze_task)
	graph.add_node("outline", create_outline)
	graph.add_node("draft", write_draft)
	graph.add_node("review", review_draft)
	graph.add_node("finalize", finalize_report)
	graph.add_edge(START, "analyze")
	graph.add_edge("analyze", "outline")
	graph.add_edge("outline", "draft")
	graph.add_edge("draft", "review")
	graph.add_edge("review", "finalize")
	graph.add_edge("finalize", END)
	return graph.compile()


def run(topic: str, audience: str) -> None:
	workflow = build_workflow()
	state = workflow.invoke(
		{
			"topic": topic,
			"audience": audience,
			"analysis": "",
			"outline": "",
			"draft": "",
			"review": "",
			"final_report": "",
		}
	)
	print(f"\n最终稿：\n{state['final_report']}")


if __name__ == "__main__":
	topic = os.getenv(
		"WORKFLOW_TOPIC",
		"为刚接触生成式 AI 的开发者介绍如何安全地使用 AI 编程助手",
	)
	audience = os.getenv("WORKFLOW_AUDIENCE", "初级软件开发者")
	print(f"模型：{OLLAMA_MODEL}")
	print(f"主题：{topic}")
	print(f"目标读者：{audience}\n")
	run(topic, audience)
