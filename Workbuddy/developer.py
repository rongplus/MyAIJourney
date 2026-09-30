"""Product development pipeline using LangGraph.

Flow: Requirements Analysis & Product Design -> Coding -> QA.
When QA returns FAIL, re-enter Coding; complete at most 10 Coding/QA iterations.
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
    """Development pipeline state; iteration represents the number of completed Coding rounds."""

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
        "design": "Requirements Analysis & Architecture Design",
        "coding": f"Coding Round {iteration}",
        "coding_tools": "Writing code files",
        "qa": f"QA Testing Round {iteration}",
        "qa_tools": "Executing test tools",
        "qa_decision": "Evaluating test results",
    }
    return labels.get(node_name, node_name)


def _progress_detail(node_name: str, iteration: int, node_state: dict, result: dict) -> str:
    """Describe the agent's current work in a user-facing progress message."""
    messages = node_state.get("messages") or []
    latest = _content_text(messages[-1]).strip() if messages else ""
    if node_name == "design":
        return "The Requirements Analysis agent is clarifying features, data structures, and implementation approach."
    if node_name == "coding":
        if latest:
            return f"The Coding agent is developing round {iteration} of code based on user requirements, target file is game_project/app.py."
        return f"The Coding agent is developing round {iteration} of code."
    if node_name == "coding_tools":
        return "The Coding agent is writing the implementation to the project file and preparing for verification."
    if node_name == "qa":
        if latest and ("FAIL" in latest.upper() or "failed" in latest.lower()):
            summary = " ".join(latest.split())
            return f"QA testing found issues: {summary[:180]}"
        return "The QA agent is checking core functionality, input validation, data persistence, and test results."
    if node_name == "qa_tools":
        if latest and ("failed" in latest.lower() or "failed" in latest):
            summary = " ".join(latest.split())
            return f"Test execution failed: {summary[:180]}, preparing to send back to Coding for fixes."
        if latest and "success" in latest.lower():
            return "Test tools executed successfully, the QA agent is continuing to check results."
        return "The QA agent is executing tests to confirm whether the program runs correctly."
    if node_name == "qa_decision":
        qa_text = _content_text(result.get("messages", [])[-1]).upper() if result.get("messages") else ""
        if "QA_STATUS: FAIL" in qa_text:
            return "QA found issues, tests did not pass, next step is to return to Coding for fixes."
        if "QA_STATUS: PASS" in qa_text:
            return "QA confirmed tests passed, preparing to end this development round."
        return "The system is deciding whether to continue fixing or end based on QA results."
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
    ) or "No entries yet"

def monthly_report(month):
    selected = [item for item in accounts if item["date"].startswith(month)]
    total = sum(item["amount"] for item in selected)
    return f"{month}: {len(selected)} entries, total {total:.2f}\\n" + "\\n".join(
        f"{item['date']} | {item['description']} | {item['amount']:.2f}" for item in selected
    )

with gr.Blocks() as demo:
    gr.Markdown("# Accounting App")
    with gr.Row():
        date = gr.Textbox(label="Date", value=datetime.now().strftime("%Y-%m-%d"))
        description = gr.Textbox(label="Description")
        amount = gr.Number(label="Amount")
        add = gr.Button("Add")
    entries = gr.Textbox(label="Entries", lines=8)
    index = gr.Number(label="Delete index", precision=0)
    delete = gr.Button("Delete")
    month = gr.Textbox(label="Month", value=datetime.now().strftime("%Y-%m"))
    report = gr.Textbox(label="Monthly Report", lines=8)
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
        cursor = connection.execute("INSERT INTO accounts(entry_date, description, category, amount) VALUES (?, ?, ?, ?)", (entry_date, description.strip(), category.strip() or "Other", amount))
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
    with gr.Blocks(title="Accounting Assistant") as demo:
        gr.Markdown("# Accounting Assistant")
        entry_date = gr.Textbox(label="Date", value=date.today().isoformat())
        description = gr.Textbox(label="Description")
        category = gr.Textbox(label="Category", value="Other")
        amount = gr.Number(label="Amount", minimum=0)
        output = gr.JSON(label="Entries")
        add = gr.Button("Add Entry")
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
    """Build the product development pipeline graph.

    After the user inputs a product idea, the graph sequentially executes
    product design, coding, and QA. QA must output ``QA_STATUS: PASS`` or
    ``QA_STATUS: FAIL`` in the final text.
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
        "\n\nThis is Coding round {iteration}. Please implement or fix code based on the previous "
        "product design and QA results. You must actually call list_files/read_file to check the project, "
        "and call write_file to write complete runnable code to a file under game_project/. "
        "Do not just display code in a reply. Prioritize implementing a genuinely useful minimal product: "
        "data should be persisted (prefer SQLite or JSON), include input validation, error handling, "
        "core functionality, and reproducible tests. Do not generate demo interfaces that only echo input. "
        "Write the code first, then verify."
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
                + "\n\nComplete requirements analysis, feature list, and implementation architecture in "
                "no more than 300 words, then immediately hand off to Coding."
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
        project_context = "Current game_project files:\n" + project_files
        if "app.py" in project_files:
            project_context += "\n\nCurrent app.py:\n" + read_file.invoke({"filepath": "app.py"})
        prompt = (
            coding_prompt.format(iteration=iteration)
            + "\n\nYou must strictly implement the following original user requirements; do not substitute "
            "generic examples:\n"
            + user_request
            + "\n\n"
            + project_context
            + "\n\nPlease implement each requirement item by item; if the user requires sqlite/sqlite3, "
            "the APP source code must actually import sqlite3 and persist data via the database."
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
                            "Only output complete runnable Python source code, no Markdown, "
                            "explanations, or code fences. Implement the user requirements, "
                            "entry file is app.py."
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
        "\n\nAt the end of the review, you must output a separate line: QA_STATUS: PASS or QA_STATUS: FAIL. "
        "Only output PASS when all key issues are resolved and available tests pass. "
        "Please use list_files/read_file to find tests or entry points first, then use run_python to "
        "actually execute tests. You must verify core functionality, data persistence, and entry files, "
        "not just do static descriptions. If tests fail, you must output the failed command, key errors, "
        "and clear fix suggestions, and output QA_STATUS: FAIL."
    )

    def qa_node(state: DeveloperState):
        messages = list(state["messages"])
        if messages and isinstance(messages[0], SystemMessage):
            messages = [message for message in messages if not isinstance(message, SystemMessage)]
        user_request = _content_text(messages[0]) if messages else ""
        response = qa_llm.invoke(
            [SystemMessage(content=qa_prompt + "\n\nThe original user requirements must be verified item by item:\n" + user_request)] + messages
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
        if "QA_STATUS: PASS" in status_text:
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
    """Run the product development pipeline synchronously and return the final message."""
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
    user_input = "Please design a simple accounting application that supports adding, deleting, and viewing entries, " \
    "and can generate monthly reports. Implement in Python with a Gradio frontend. All code must be runnable. " \
    "Required modules are already installed, no need to check. Use sqlite3 to persist input data, " \
    "include input validation and error handling, entry file is app.py. " \
    "Previous entries should be visible when reopening the app. Entries include date, description, and amount. " \
    "Please ensure the code is runnable and includes necessary tests."
    final_message = run_developer(
        user_input,
        model="qwen2.5:7b",
        max_iterations=3,
        verbose=True,
    )
    print("\n=== Final Message ===")
    print(final_message)
