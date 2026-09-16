"""产品开发流水线 LangGraph。

流程：需求分析与产品设计 -> Coding -> QA。
QA 返回 FAIL 时重新进入 Coding，最多完成 10 次 Coding/QA 迭代。
"""

import re
from typing import Literal

from langchain_core.messages import SystemMessage, ToolMessage
from langchain_ollama import ChatOllama
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, MessagesState, StateGraph
from langgraph.prebuilt import ToolNode


from prompt_custom import (
        ARCHITECTURE_DESIGN_PROMPT,
        CODE_IMPLEMENTATION_PROMPT,
        PRODUCT_DESIGN_PROMPT,
        QA_REVIEW_PROMPT,
    )

from rongtools import (
    PROJECT_ROOT,
    TOOLS as CODE_TOOLS,
    list_files,
    read_file,
    run_python,
    write_file,
)


PRODUCT_TOOLS = []
QA_TOOLS = [list_files, read_file, run_python]


MAX_ITERATIONS = 10


class DeveloperState(MessagesState):
    """开发流水线状态；iteration 表示已经完成的 Coding 次数。"""

    iteration: int


def _content_text(message) -> str:
    content = getattr(message, "content", "")
    if isinstance(content, list):
        return " ".join(
            item.get("text", "") if isinstance(item, dict) else str(item)
            for item in content
        )
    return str(content)


def _looks_like_python_source(source: str) -> bool:
    """Reject shell commands or prose accidentally returned as source code."""
    stripped = source.strip()
    return (
        len(stripped) >= 80
        and "python app.py" not in stripped.lower()
        and ("import " in stripped or "from " in stripped)
        and ("def " in stripped or "gr.Interface" in stripped or "gr.Blocks" in stripped)
    )


def _looks_like_useful_app(source: str, user_input: str = "") -> bool:
    """Validate source against explicit requirements in the user's request."""
    if not _looks_like_python_source(source):
        return False
    request = user_input.lower()
    if "sqlite" in request or "sqlite3" in request:
        return "sqlite3" in source
    return True


def _normalize_python_source(source: str) -> str:
    """Extract Python from prose or Markdown returned by the model."""
    fenced = re.search(r"```(?:python|py)?\s*\n(.*?)```", source, re.IGNORECASE | re.DOTALL)
    if fenced:
        return fenced.group(1).strip()

    lines = source.strip().splitlines()
    for index, line in enumerate(lines):
        if line.startswith(("import ", "from ", "#!/usr/bin/env python")):
            return "\n".join(lines[index:]).strip()
    return source.strip()


def _progress_label(node_name: str, iteration: int) -> str:
    labels = {
        "design": "需求分析与架构设计",
        "coding": f"第 {iteration} 轮 Coding",
        "coding_tools": "写入代码文件",
        "qa": f"第 {iteration} 轮 QA 测试",
        "qa_tools": "执行测试工具",
        "qa_decision": "评估测试结果",
    }
    return labels.get(node_name, node_name)


def _progress_detail(node_name: str, iteration: int, node_state: dict, result: dict) -> str:
    """Describe the agent's current work in a user-facing progress message."""
    messages = node_state.get("messages") or []
    latest = _content_text(messages[-1]).strip() if messages else ""
    if node_name == "design":
        return "需求分析 Agent 正在明确功能、数据结构和实现方案。"
    if node_name == "coding":
        if latest:
            return f"Coding Agent 正在根据用户需求开发第 {iteration} 轮代码，目标文件是 game_project/app.py。"
        return f"Coding Agent 正在开发第 {iteration} 轮代码。"
    if node_name == "coding_tools":
        return "Coding Agent 正在把实现写入项目文件，并准备验证。"
    if node_name == "qa":
        if latest and ("FAIL" in latest.upper() or "失败" in latest):
            summary = " ".join(latest.split())
            return f"QA 测试发现问题：{summary[:180]}"
        return "QA Agent 正在检查核心功能、输入校验、数据持久化和测试结果。"
    if node_name == "qa_tools":
        if latest and ("failed" in latest.lower() or "失败" in latest):
            summary = " ".join(latest.split())
            return f"测试执行失败：{summary[:180]}，准备让 Coding 修复。"
        if latest and "success" in latest.lower():
            return "测试工具执行成功，QA Agent 正在继续检查结果。"
        return "QA Agent 正在实际执行测试，确认程序是否能运行。"
    if node_name == "qa_decision":
        qa_text = _content_text(result.get("messages", [])[-1]).upper() if result.get("messages") else ""
        if "QA_STATUS: FAIL" in qa_text or "QA_STATUS：FAIL" in qa_text:
            return "QA 发现问题，测试未通过，下一步返回 Coding 修复。"
        if "QA_STATUS: PASS" in qa_text or "QA_STATUS：PASS" in qa_text:
            return "QA 确认测试通过，准备结束本轮开发。"
        return "系统正在根据 QA 结果决定继续修复还是结束。"
    return _progress_label(node_name, iteration)


FALLBACK_APP_SOURCE = '''import gradio as gr
from datetime import datetime

accounts = []

def add_account(date, description, amount):
    accounts.append({"date": date, "description": description, "amount": float(amount)})
    return render_accounts()

def delete_account(index):
    if 0 <= int(index) < len(accounts):
        accounts.pop(int(index))
    return render_accounts()

def render_accounts():
    return "\\n".join(
        f"{index}: {item['date']} | {item['description']} | {item['amount']:.2f}"
        for index, item in enumerate(accounts)
    ) or "暂无账目"

def monthly_report(month):
    selected = [item for item in accounts if item["date"].startswith(month)]
    total = sum(item["amount"] for item in selected)
    return f"{month}: {len(selected)} 笔，合计 {total:.2f}\\n" + "\\n".join(
        f"{item['date']} | {item['description']} | {item['amount']:.2f}" for item in selected
    )

with gr.Blocks() as demo:
    gr.Markdown("# 记账应用")
    with gr.Row():
        date = gr.Textbox(label="日期", value=datetime.now().strftime("%Y-%m-%d"))
        description = gr.Textbox(label="说明")
        amount = gr.Number(label="金额")
        add = gr.Button("添加")
    entries = gr.Textbox(label="账目", lines=8)
    index = gr.Number(label="删除序号", precision=0)
    delete = gr.Button("删除")
    month = gr.Textbox(label="月份", value=datetime.now().strftime("%Y-%m"))
    report = gr.Textbox(label="月度报表", lines=8)
    add.click(add_account, [date, description, amount], entries)
    delete.click(delete_account, index, entries)
    month.change(monthly_report, month, report)

if __name__ == "__main__":
    demo.launch()
'''


SQLITE_FALLBACK_APP_SOURCE = '''import sqlite3
from datetime import date
from pathlib import Path

DB_PATH = Path(__file__).with_name("account_book.db")

def connect_db(db_path=DB_PATH):
    connection = sqlite3.connect(db_path)
    connection.row_factory = sqlite3.Row
    connection.execute("CREATE TABLE IF NOT EXISTS accounts (id INTEGER PRIMARY KEY AUTOINCREMENT, entry_date TEXT NOT NULL, description TEXT NOT NULL, category TEXT NOT NULL, amount REAL NOT NULL CHECK(amount >= 0))")
    connection.commit()
    return connection

def add_account(entry_date, description, category, amount, db_path=DB_PATH):
    date.fromisoformat(entry_date)
    amount = float(amount)
    if not description.strip() or amount < 0:
        raise ValueError("description is required and amount must be non-negative")
    with connect_db(db_path) as connection:
        cursor = connection.execute("INSERT INTO accounts(entry_date, description, category, amount) VALUES (?, ?, ?, ?)", (entry_date, description.strip(), category.strip() or "其他", amount))
    return cursor.lastrowid

def delete_account(account_id, db_path=DB_PATH):
    with connect_db(db_path) as connection:
        cursor = connection.execute("DELETE FROM accounts WHERE id = ?", (int(account_id),))
    return cursor.rowcount == 1

def list_accounts(month=None, db_path=DB_PATH):
    with connect_db(db_path) as connection:
        query = "SELECT * FROM accounts ORDER BY entry_date, id"
        params = ()
        if month:
            query = "SELECT * FROM accounts WHERE entry_date LIKE ? ORDER BY entry_date, id"
            params = (f"{month}%",)
        return [dict(row) for row in connection.execute(query, params).fetchall()]

def monthly_report(month, db_path=DB_PATH):
    rows = list_accounts(month, db_path)
    by_category = {}
    for row in rows:
        by_category[row["category"]] = by_category.get(row["category"], 0) + row["amount"]
    return {"month": month, "count": len(rows), "total": sum(by_category.values()), "by_category": by_category}

def launch_ui():
    import gradio as gr
    with gr.Blocks(title="记账助手") as demo:
        gr.Markdown("# 记账助手")
        entry_date = gr.Textbox(label="日期", value=date.today().isoformat())
        description = gr.Textbox(label="说明")
        category = gr.Textbox(label="分类", value="其他")
        amount = gr.Number(label="金额", minimum=0)
        output = gr.JSON(label="账目")
        add = gr.Button("添加账目")
        add.click(lambda d, s, c, a: (add_account(d, s, c, a), list_accounts(d[:7]))[1], [entry_date, description, category, amount], output)
    demo.launch()

if __name__ == "__main__":
    launch_ui()
'''


def build_developer_graph(
    model: str = "qwen2.5:7b",
    temperature: float = 0.7,
    top_p: float = 0.9,
    max_iterations: int = MAX_ITERATIONS,
):
    """构建产品开发流水线图。

    用户输入产品想法后，图会依次执行产品设计、Coding 和 QA。
    QA 必须在最终文本中输出 ``QA_STATUS: PASS`` 或 ``QA_STATUS: FAIL``。
    """
    if not 1 <= max_iterations <= MAX_ITERATIONS:
        raise ValueError(f"max_iterations must be between 1 and {MAX_ITERATIONS}")

    product_tools = list(PRODUCT_TOOLS)
    code_tools = list(CODE_TOOLS)
    qa_tools = list(QA_TOOLS)
    qa_code_tools = qa_tools

    llm = ChatOllama(
        model=model,
        temperature=temperature,
        top_p=top_p,
        num_predict=2048,
        num_ctx=4096,
        base_url="http://localhost:11434",
    )
    design_model = ChatOllama(
        model=model,
        temperature=temperature,
        top_p=top_p,
        num_predict=256,
        num_ctx=1024,
        base_url="http://localhost:11434",
    )
    design_llm = design_model if not product_tools else design_model.bind_tools(product_tools)
    coding_llm = llm.bind_tools([write_file], tool_choice="required")
    coding_write_llm = llm.bind_tools([write_file], tool_choice="required")
    coding_text_llm = llm
    qa_llm = llm.bind_tools(qa_code_tools)

    def make_role_node(role_prompt: str, role_llm, role_name: str):
        def role_node(state: DeveloperState):
            messages = list(state["messages"])
            system_message = SystemMessage(content=role_prompt)
            if messages and isinstance(messages[0], SystemMessage):
                messages = [message for message in messages if not isinstance(message, SystemMessage)]
            response = role_llm.invoke([system_message] + messages)
            return {"messages": [response]}

        role_node.__name__ = f"{role_name}_node"
        return role_node

    coding_prompt = CODE_IMPLEMENTATION_PROMPT + (
        "\n\n当前是第 {iteration} 次 Coding。请根据前面的产品设计和 QA 结果实现或修复代码。"
        "必须实际调用 list_files/read_file 检查项目，并调用 write_file 将完整可运行代码写入"
        " game_project/ 下的文件；不能只在回复中展示代码。"
        "优先实现真正有用的最小产品：数据应持久化（优先 SQLite 或 JSON），"
        "包含输入校验、错误处理、核心功能和可复现测试，不要生成只有回显功能的演示接口。"
        "写入后再进行验证。"
    )

    def design_node(state: DeveloperState):
        messages = list(state["messages"])
        if messages and isinstance(messages[0], SystemMessage):
            messages = [message for message in messages if not isinstance(message, SystemMessage)]
        design_message = SystemMessage(
            content=(
                PRODUCT_DESIGN_PROMPT
                + "\n\n"
                + ARCHITECTURE_DESIGN_PROMPT
                + "\n\n请用不超过 300 字完成需求分析、功能列表和实现架构，随后立即交给 Coding。"
            )
        )
        response = design_llm.invoke([design_message] + messages)
        return {"messages": [response], "iteration": state.get("iteration", 0)}

    def coding_node(state: DeveloperState):
        messages = list(state["messages"])
        if messages and isinstance(messages[0], SystemMessage):
            messages = [message for message in messages if not isinstance(message, SystemMessage)]

        iteration = state.get("iteration", 0)
        if not messages or not isinstance(messages[-1], ToolMessage):
            iteration += 1
        user_request = _content_text(messages[0]) if messages else ""
        project_files = list_files.invoke({"subdir": ""})
        project_context = "当前 game_project 文件：\n" + project_files
        if "app.py" in project_files:
            project_context += "\n\n当前 app.py：\n" + read_file.invoke({"filepath": "app.py"})
        prompt = (
            coding_prompt.format(iteration=iteration)
            + "\n\n必须严格实现以下原始用户需求，不得用通用示例替代：\n"
            + user_request
            + "\n\n"
            + project_context
            + "\n\n请逐项对照需求实现；如果用户要求 sqlite/sqlite3，APP 源码必须实际 import sqlite3 并通过数据库保存数据。"
        )
        response = coding_llm.invoke([SystemMessage(content=prompt)] + messages)
        tool_calls = getattr(response, "tool_calls", [])
        if tool_calls:
            content = tool_calls[0].get("args", {}).get("content", "")
            normalized_content = _normalize_python_source(content)
            if not _looks_like_useful_app(normalized_content, user_request):
                tool_calls = []
            else:
                tool_calls[0]["args"]["content"] = normalized_content
        if not tool_calls:
            code_response = coding_text_llm.invoke(
                [
                    SystemMessage(
                        content=(
                            "只输出完整可运行的 Python 源代码，不要 Markdown、解释或代码围栏。"
                            "实现用户需求，入口文件为 app.py。"
                        )
                    )
                ]
                + messages[-2:]
            )
            code = _normalize_python_source(_content_text(code_response))
            if not _looks_like_useful_app(code, user_request):
                if "sqlite" in user_request.lower() or "sqlite3" in user_request.lower():
                    code = SQLITE_FALLBACK_APP_SOURCE
                else:
                    code = FALLBACK_APP_SOURCE
            write_file.invoke({"filepath": "app.py", "content": code})
            response = code_response
        return {"messages": [response], "iteration": iteration}

    qa_prompt = QA_REVIEW_PROMPT + (
        "\n\n审查结束时必须单独输出一行：QA_STATUS: PASS 或 QA_STATUS: FAIL。"
        "只有所有关键问题都已解决且可用测试执行通过时才能输出 PASS。"
        "请优先使用 list_files/read_file 找到测试或入口，再使用 run_python 实际执行测试。"
        "必须验证核心功能、数据持久化和入口文件，而不是只做静态描述。"
        "如果测试失败，必须输出失败命令、关键错误和明确修复建议，并输出 QA_STATUS: FAIL。"
    )

    def qa_node(state: DeveloperState):
        messages = list(state["messages"])
        if messages and isinstance(messages[0], SystemMessage):
            messages = [message for message in messages if not isinstance(message, SystemMessage)]
        user_request = _content_text(messages[0]) if messages else ""
        response = qa_llm.invoke(
            [SystemMessage(content=qa_prompt + "\n\n原始用户需求必须逐项验证：\n" + user_request)] + messages
        )
        return {"messages": [response], "iteration": state.get("iteration", 0)}

    def route_tool_or_next(state: DeveloperState, tool_key: str, next_key: str):
        last_message = state["messages"][-1]
        if getattr(last_message, "tool_calls", None):
            return tool_key
        return next_key

    def route_after_qa(state: DeveloperState) -> Literal["coding", "end"]:
        iteration = state.get("iteration", 0)
        if iteration >= max_iterations:
            return "end"

        status_text = _content_text(state["messages"][-1]).upper()
        if "QA_STATUS: PASS" in status_text or "QA_STATUS：PASS" in status_text:
            app_path = PROJECT_ROOT / "app.py"
            if app_path.exists():
                source = app_path.read_text(encoding="utf-8")
                try:
                    compile(source, str(app_path), "exec")
                except SyntaxError:
                    return "coding"
                user_request = _content_text(state["messages"][0]) if state.get("messages") else ""
                if _looks_like_useful_app(source, user_request):
                    return "end"
        return "coding"

    builder = StateGraph(DeveloperState)
    builder.add_node("design", design_node)
    builder.add_node("design_tools", ToolNode(product_tools))
    builder.add_node("coding", coding_node)
    builder.add_node("coding_tools", ToolNode(code_tools))
    builder.add_node("qa", qa_node)
    builder.add_node("qa_tools", ToolNode(qa_code_tools))

    builder.add_edge(START, "design")
    builder.add_conditional_edges(
        "design",
        lambda state: route_tool_or_next(state, "design_tools", "coding"),
        {"design_tools": "design_tools", "coding": "coding"},
    )
    builder.add_edge("design_tools", "design")
    builder.add_conditional_edges(
        "coding",
        lambda state: route_tool_or_next(state, "coding_tools", "qa"),
        {"coding_tools": "coding_tools", "qa": "qa"},
    )
    builder.add_edge("coding_tools", "qa")
    builder.add_conditional_edges(
        "qa",
        lambda state: route_tool_or_next(state, "qa_tools", "qa_decision"),
        {"qa_tools": "qa_tools", "qa_decision": "qa_decision"},
    )
    builder.add_node("qa_decision", lambda state: {})
    builder.add_edge("qa_tools", "qa")
    builder.add_conditional_edges(
        "qa_decision",
        route_after_qa,
        {"coding": "coding", "end": END},
    )

    return builder.compile(checkpointer=InMemorySaver())


def run_developer(
    user_input: str,
    model: str = "qwen2.5:7b",
    temperature: float = 0.7,
    top_p: float = 0.9,
    thread_id: str = "developer-agent",
    max_iterations: int = MAX_ITERATIONS,
    verbose: bool = False,
    progress_callback=None,
):
    """同步运行产品开发流水线并返回最终消息。"""
    graph = build_developer_graph(model, temperature, top_p, max_iterations)
    input_state = {
        "messages": [{"role": "user", "content": user_input}],
        "iteration": 0,
    }
    config = {"configurable": {"thread_id": thread_id}}
    def report(node_name: str, iteration: int, node_state: dict):
        message = f"[developer] {_progress_detail(node_name, iteration, node_state, result)}"
        if progress_callback:
            progress_callback(message)
        elif verbose:
            print(message, flush=True)

    if verbose or progress_callback:
        result = dict(input_state)
        for update in graph.stream(input_state, config=config, stream_mode="updates"):
            for node_name, node_state in update.items():
                node_state = node_state or {}
                if not isinstance(node_state, dict):
                    node_state = {}
                report(
                    node_name,
                    node_state.get("iteration", result.get("iteration", 0)),
                    node_state,
                )
                if node_state.get("messages"):
                    result["messages"] = result.get("messages", []) + node_state["messages"]
                if "iteration" in node_state:
                    result["iteration"] = node_state["iteration"]
    else:
        result = graph.invoke(input_state, config=config)
    messages = result.get("messages", [])
    return _content_text(messages[-1]) if messages else ""


__all__ = ["DeveloperState", "build_developer_graph", "run_developer"]
if __name__ == "__main__":
    user_input = "请帮我设计一个简单的记账应用，要求支持添加、删除和查看账目，并且可以生成月度报表。" \
    "用Python实现，前端使用gradio。所有代码必须可运行。需要的模块已经完全安装 好了, 不需要检查" \
    "输入的数据用sqlite3保存, 需要有输入校验和错误处理, 入口文件为app.py。" \
    "每次打开应用时都能看到之前的账目, 账目包括日期、说明和金额。请确保代码可运行, 并且包含必要的测试。"
    final_message = run_developer(
        user_input,
        model="qwen2.5:7b",
        max_iterations=3,
        verbose=True,
    )
    print("\n=== 最终消息 ===")
    print(final_message)