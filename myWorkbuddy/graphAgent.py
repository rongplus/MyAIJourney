"""LangGraph 图定义 — 通用 Agent + Tools 节点 + 条件路由

基于 agent-graph-tool.py 的架构模式，使用 Ollama 作为 LLM 后端。

图结构（单 Agent 模式）：
  [START] → model → route? ──(有 tool_calls)──→ tools → model → ...
                         └──(无 tool_calls)──→ [END]

图结构（Develop Team 模式）：
  [START] → designer → developer → dev_route? ──(tools)──→ dev_tools → developer → ...
                                                 └──(no calls)──→ qa → qa_route? ──(tools)──→ qa_tools → qa → ...
                                                                     └──(no calls)──→ [END]

  designer 纯文本输出，developer 和 qa 各自有独立的工具循环（dev_tools / qa_tools）。

图结构（Team 模式）：
  [START] → analyst → designer ⇄ design_tools → developer ⇄ dev_tools → qa ⇄ qa_tools → [END]

  用于 IT 项目交付，从需求分析、项目设计、编码实现到 QA 验证完整串行协作。
"""
from typing import Literal

from langchain_core.messages import SystemMessage, HumanMessage
from langchain_ollama import ChatOllama
from langgraph.graph import StateGraph, MessagesState, START, END
from langgraph.prebuilt import ToolNode
from langgraph.checkpoint.memory import InMemorySaver

from agentTools import get_weather

try:
    from code_tools import CODE_TOOLS
except ModuleNotFoundError:
    CODE_TOOLS = []

try:
    from product_tools import PRODUCT_TOOLS
except ModuleNotFoundError:
    PRODUCT_TOOLS = []

try:
    from qa_tools import QA_TOOLS
except ModuleNotFoundError:
    QA_TOOLS = []

try:
    from biz_tools import BIZ_TOOLS
except ModuleNotFoundError:
    BIZ_TOOLS = []

# Agent 配置：系统提示 + 工具集
AGENT_CONFIGS = {
    "weather": {
        "system_prompt": (
            "你是一个乐于助人的 AI 助手，请用中文回答。"
            "当用户询问天气时，请调用 get_weather 工具查询。"
        ),
        "tools": [get_weather],
    },
    "code": {
        "system_prompt": (
            "你是一个专业的编程助手（Code Agent）。\n"
            "你可以使用以下工具来帮助用户完成编程任务：\n"
            "- list_files: 列出目录内容\n"
            "- read_file: 读取文件内容\n"
            "- write_file: 写入文件\n"
            "- run_python: 执行 Python 代码\n\n"
            "工作准则（必须严格遵守）：\n"
            "1. 先理解用户需求，再决定使用哪个工具\n"
            "2. 读文件前先用 list_files 了解项目结构\n"
            "3. 写文件前先 read_file 确认现有内容\n"
            "4. **生成的代码必须使用 write_file 保存到文件**，不要只在对话中输出代码\n"
            "5. 保存文件后用 run_python 执行验证，有错误则修复后重试\n"
            "6. 文件默认保存到当前工作目录下的 output/ 子目录\n"
            "7. 用中文解释你的操作和结果\n"
        ),
        "tools": CODE_TOOLS,
    },
    "product": {
        "system_prompt": (
            "你是一个专业的产品设计助手（Product Agent）。\n"
            "你可以使用以下工具来帮助用户完成产品设计工作：\n"
            "- create_prd:          生成产品需求文档（PRD）\n"
            "- create_user_story:   生成标准格式的用户故事\n"
            "- create_wireframe:    生成页面线框图描述\n"
            "- analyze_competitor:  生成竞品分析模板\n\n"
            "工作准则：\n"
            "1. 先理解用户的产品设计需求，再决定使用哪个工具\n"
            "2. 生成 PRD 前先确认产品名称、描述、目标用户和核心功能\n"
            "3. 生成用户故事时需明确角色、目标和价值\n"
            "4. 竞品分析时提供竞品名称列表，会生成结构化对比矩阵\n"
            "5. 用中文输出，格式清晰，便于团队评审\n"
        ),
        "tools": PRODUCT_TOOLS,
    },
}

# ────────────────────── Develop Team 角色提示 ──────────────────────

DESIGNER_PROMPT = (
    "你是开发团队中的【设计师】角色。\n"
    "你的职责是理解用户需求，输出产品设计方案。\n"
    "你可以使用以下工具：\n"
    "- create_prd:          生成产品需求文档\n"
    "- create_user_story:   生成用户故事\n"
    "- create_wireframe:    生成页面线框图\n"
    "- analyze_competitor:  竞品分析\n\n"
    "工作准则：\n"
    "1. 分析用户需求，拆解为具体的设计任务\n"
    "2. 使用工具生成 PRD、用户故事或线框图\n"
    "3. 输出简洁的设计方案摘要，供开发人员参考\n"
    "4. 完成后以「设计阶段完成」结尾，交接给开发\n"
)

DEVELOPER_PROMPT = (
    "你是开发团队中的【开发工程师】角色。\n"
    "你的职责是根据设计方案实现代码。\n"
    "你可以使用以下工具：\n"
    "- list_files:  列出目录内容\n"
    "- read_file:   读取文件内容\n"
    "- write_file:  写入文件\n"
    "- run_python:  执行 Python 代码\n\n"
    "工作准则（必须严格遵守）：\n"
    "1. 参考上游设计方案的上下文\n"
    "2. 编写清晰、可维护的代码\n"
    "3. **生成的代码必须使用 write_file 保存到文件**，不要只在对话中输出代码\n"
    "4. 文件默认保存到当前工作目录下的 output/ 子目录\n"
    "5. 用 run_python 验证代码可运行，有错误则修复后重试\n"
    "6. 完成后以「开发阶段完成」结尾，交接给 QA\n"
)

QA_PROMPT = (
    "你是开发团队中的【QA 测试工程师】角色。\n"
    "你的职责是对开发成果进行测试和审查。\n"
    "你可以使用以下工具：\n"
    "- generate_test_cases: 生成测试用例\n"
    "- review_code:         审查代码质量\n"
    "- report_bug:          提交缺陷报告\n"
    "- run_python:          执行验证脚本\n\n"
    "工作准则：\n"
    "1. 根据上游设计和开发内容生成测试用例\n"
    "2. 使用 review_code 审查代码\n"
    "3. 如发现问题用 report_bug 提交 Bug 报告\n"
    "4. 完成后输出最终质量评估结论\n"
)

# ────────────────────── IT Team 角色提示 ──────────────────────

REQUIREMENT_ANALYST_PROMPT = (
    "你是 IT 项目团队中的【需求分析师】角色。\n"
    "你的职责是把用户的一句话需求整理成可执行的项目需求。\n\n"
    "工作准则：\n"
    "1. 明确项目目标、目标用户、核心业务流程和成功标准\n"
    "2. 拆分功能需求、非功能需求、约束条件和风险\n"
    "3. 输出清晰的需求分析摘要，供项目设计师继续细化\n"
    "4. 如信息不足，先基于合理假设推进，并在输出中列出假设\n"
    "5. 完成后以「需求分析阶段完成」结尾，交接给项目设计\n"
)

PROJECT_DESIGNER_PROMPT = (
    "你是 IT 项目团队中的【项目设计师】角色。\n"
    "你的职责是根据需求分析输出项目设计方案。\n"
    "你可以使用以下工具：\n"
    "- create_prd:          生成产品需求文档\n"
    "- create_user_story:   生成用户故事\n"
    "- create_wireframe:    生成页面线框图\n"
    "- analyze_competitor:  竞品分析\n\n"
    "工作准则：\n"
    "1. 参考需求分析师的上下文\n"
    "2. 设计项目结构、核心模块、数据流、接口和关键页面或命令流程\n"
    "3. 必要时使用产品工具生成 PRD、用户故事或线框图\n"
    "4. 输出可交给开发工程师执行的设计说明\n"
    "5. 完成后以「项目设计阶段完成」结尾，交接给 Coding\n"
)

TEAM_DEVELOPER_PROMPT = (
    "你是 IT 项目团队中的【Coding 工程师】角色。\n"
    "你的职责是根据需求分析和项目设计实现代码。\n"
    "你可以使用以下工具：\n"
    "- list_files:  列出目录内容\n"
    "- read_file:   读取文件内容\n"
    "- write_file:  写入文件\n"
    "- run_python:  执行 Python 代码\n\n"
    "工作准则（必须严格遵守）：\n"
    "1. 参考需求分析和项目设计的上下文\n"
    "2. 先规划文件结构，再写入代码\n"
    "3. **生成的代码必须使用 write_file 保存到文件**，不要只在对话中输出代码\n"
    "4. 文件默认保存到当前工作目录下的 output/ 子目录\n"
    "5. 用 run_python 验证关键代码可运行，有错误则修复后重试\n"
    "6. 完成后以「Coding 阶段完成」结尾，交接给 QA\n"
)

TEAM_QA_PROMPT = (
    "你是 IT 项目团队中的【QA 工程师】角色。\n"
    "你的职责是对 Coding 交付物进行测试设计、代码审查和质量结论输出。\n"
    "你可以使用以下工具：\n"
    "- generate_test_cases: 生成测试用例\n"
    "- review_code:         审查代码质量\n"
    "- report_bug:          提交缺陷报告\n"
    "- run_python:          执行验证脚本\n\n"
    "工作准则：\n"
    "1. 根据需求分析、项目设计和 Coding 输出生成测试用例\n"
    "2. 使用 review_code 审查关键代码\n"
    "3. 如发现问题用 report_bug 提交 Bug 报告\n"
    "4. 输出最终质量评估、已验证内容、风险和改进建议\n"
    "5. 完成后以「QA 阶段完成」结尾\n"
)


# ────────────────────── 商业分析 Team 角色提示 ──────────────────────

# 每个 agent 使用不同的 Ollama 模型
BIZ_DATA_ANALYST_MODEL = "qwen2.5:7b"
BIZ_INDUSTRY_PLANNER_MODEL = "llama3:latest"
BIZ_RESEARCH_ANALYST_MODEL = "mistral:latest"

BIZ_DATA_ANALYST_PROMPT = (
    "你是商业分析团队中的【数据分析师】角色（模型：qwen2.5:7b）。\n"
    "你的职责是分析市场数据，挖掘商业洞察。\n"
    "你可以使用以下工具：\n"
    "- analyze_market: 市场规模与趋势分析\n"
    "- generate_industry_report: 行业研究报告生成\n\n"
    "工作准则：\n"
    "1. 理解用户需求，确定分析范围和市场细分\n"
    "2. 使用 analyze_market 生成市场分析框架\n"
    "3. 使用 generate_industry_report 生成行业研究框架\n"
    "4. 输出数据洞察摘要，供行业规划师继续\n"
    "5. 完成后以「数据分析阶段完成」结尾，交接给行业规划\n"
)

BIZ_INDUSTRY_PLANNER_PROMPT = (
    "你是商业分析团队中的【行业规划师】角色（模型：llama3:latest）。\n"
    "你的职责是根据数据分析结果制定行业规划策略。\n"
    "你可以使用以下工具：\n"
    "- analyze_market: 市场规模与趋势分析\n"
    "- generate_industry_report: 行业研究报告生成\n\n"
    "工作准则：\n"
    "1. 参考上游数据分析师的上下文\n"
    "2. 结合行业趋势制定战略规划\n"
    "3. 识别行业关键驱动因素和风险\n"
    "4. 输出行业规划策略，供投资研报师继续\n"
    "5. 完成后以「行业规划阶段完成」结尾，交接给投资研报师\n"
)

BIZ_RESEARCH_ANALYST_PROMPT = (
    "你是商业分析团队中的【投资研报师】角色（模型：mistral:latest）。\n"
    "你的职责是根据上游分析和规划生成投资研究报告。\n"
    "你可以使用以下工具：\n"
    "- generate_research_report: 投资研报生成\n"
    "- generate_industry_report: 行业研究报告\n\n"
    "工作准则：\n"
    "1. 参考上游数据分析和行业规划的上下文\n"
    "2. 使用 generate_research_report 生成研报框架\n"
    "3. 填充基本面分析、估值分析和投资建议\n"
    "4. 输出完整的投资研究报告\n"
    "5. 完成后以「投资研报阶段完成」结尾\n"
)


def build_biz_team_graph(
    temperature: float = 0.7,
    top_p: float = 0.9,
    system_prompt: str = "",
):
    """构建商业分析团队图（数据分析师 → 行业规划师 → 投资研报师）

    图结构：
      [START] → analyst → analyst_route? ──(tools)──→ analyst_tools → analyst → ...
                                            └──(end)──→ planner → planner_route? ──(tools)──→ planner_tools → planner → ...
                                                                              └──(end)──→ researcher → researcher_route? ──(tools)──→ researcher_tools → researcher → ...
                                                                                                                └──(end)──→ [END]

    每个角色使用不同的 Ollama 模型：
      - 数据分析师: qwen2.5:7b
      - 行业规划师: llama3:latest
      - 投资研报师: mistral:latest
    """
    base_prompt = system_prompt.strip() if system_prompt.strip() else ""

    # 每个角色独立 LLM
    llm_analyst = ChatOllama(
        model=BIZ_DATA_ANALYST_MODEL,
        temperature=temperature,
        top_p=top_p,
        base_url="http://localhost:11434",
    )
    llm_planner = ChatOllama(
        model=BIZ_INDUSTRY_PLANNER_MODEL,
        temperature=temperature,
        top_p=top_p,
        base_url="http://localhost:11434",
    )
    llm_researcher = ChatOllama(
        model=BIZ_RESEARCH_ANALYST_MODEL,
        temperature=temperature,
        top_p=top_p,
        base_url="http://localhost:11434",
    )

    # 各角色绑定不同工具
    llm_analyst_tools = llm_analyst.bind_tools(BIZ_TOOLS)
    llm_planner_tools = llm_planner.bind_tools(BIZ_TOOLS)
    llm_researcher_tools = llm_researcher.bind_tools(BIZ_TOOLS)

    def make_node(role_prompt: str, role_name: str, role_llm):
        full_prompt = (base_prompt + "\n\n" if base_prompt else "") + role_prompt

        def node_fn(state: MessagesState):
            messages = state["messages"]
            if not messages or not isinstance(messages[0], SystemMessage):
                messages = [SystemMessage(content=full_prompt)] + list(messages)
            else:
                messages = [SystemMessage(content=full_prompt)] + [
                    m for m in messages if not isinstance(m, SystemMessage)
                ]
            response = role_llm.invoke(messages)
            if hasattr(response, "content") and response.content:
                response.content = f"**[{role_name}]**: {response.content}"
            return {"messages": [response]}

        return node_fn

    def make_route(tools_key: str, next_key: str):
        def route_fn(state: MessagesState) -> str:
            last_message = state["messages"][-1]
            if hasattr(last_message, "tool_calls") and last_message.tool_calls:
                return tools_key
            return next_key
        return route_fn

    builder = StateGraph(MessagesState)

    # 三个角色节点
    builder.add_node(
        "biz_analyst",
        make_node(BIZ_DATA_ANALYST_PROMPT, "数据分析师", llm_analyst_tools),
    )
    builder.add_node(
        "biz_planner",
        make_node(BIZ_INDUSTRY_PLANNER_PROMPT, "行业规划师", llm_planner_tools),
    )
    builder.add_node(
        "biz_researcher",
        make_node(BIZ_RESEARCH_ANALYST_PROMPT, "投资研报师", llm_researcher_tools),
    )

    # 三个独立的 ToolNode
    builder.add_node("biz_analyst_tools", ToolNode(BIZ_TOOLS))
    builder.add_node("biz_planner_tools", ToolNode(BIZ_TOOLS))
    builder.add_node("biz_researcher_tools", ToolNode(BIZ_TOOLS))

    # 数据分析师 → 工具循环 → 行业规划师
    builder.add_edge(START, "biz_analyst")
    builder.add_conditional_edges(
        "biz_analyst",
        make_route("biz_analyst_tools", "biz_planner"),
        {"biz_analyst_tools": "biz_analyst_tools", "biz_planner": "biz_planner"},
    )
    builder.add_edge("biz_analyst_tools", "biz_analyst")

    # 行业规划师 → 工具循环 → 投资研报师
    builder.add_conditional_edges(
        "biz_planner",
        make_route("biz_planner_tools", "biz_researcher"),
        {"biz_planner_tools": "biz_planner_tools", "biz_researcher": "biz_researcher"},
    )
    builder.add_edge("biz_planner_tools", "biz_planner")

    # 投资研报师 → 工具循环 → END
    builder.add_conditional_edges(
        "biz_researcher",
        make_route("biz_researcher_tools", "end"),
        {"biz_researcher_tools": "biz_researcher_tools", "end": END},
    )
    builder.add_edge("biz_researcher_tools", "biz_researcher")

    memory = InMemorySaver()
    agent = builder.compile(checkpointer=memory)
    return agent


def build_develop_team_graph(
    model: str = "qwen2.5:7b",
    temperature: float = 0.7,
    top_p: float = 0.9,
    system_prompt: str = "",
):
    """构建开发团队协作图（Designer → Developer ⇄ Tools → QA ⇄ Tools）

    图结构：
      [START] → designer → dev_route? ──(tools)──→ tools → developer → ...
                                       └──(end)──→ qa → qa_route? ──(tools)──→ tools → qa → ...
                                                                         └──(end)──→ [END]

    designer 不调用工具，纯文本输出设计方案。
    developer 和 qa 各自有工具循环，可以反复调用工具。

    Args:
        model:         Ollama 模型名称
        temperature:   温度参数
        top_p:         Top-P 采样参数
        system_prompt: 自定义系统提示（为空则使用预设）

    Returns:
        编译后的 LangGraph 可执行图（带 InMemorySaver）
    """
    all_tools = PRODUCT_TOOLS + CODE_TOOLS + QA_TOOLS

    llm = ChatOllama(
        model=model,
        temperature=temperature,
        top_p=top_p,
        base_url="http://localhost:11434",
    )
    llm_with_tools = llm.bind_tools(all_tools)

    base_prompt = system_prompt.strip() if system_prompt.strip() else ""

    def make_node(role_prompt: str, role_name: str):
        """生成角色节点函数"""
        full_prompt = (base_prompt + "\n\n" if base_prompt else "") + role_prompt

        def node_fn(state: MessagesState):
            messages = state["messages"]
            # 替换 SystemMessage 为当前角色的
            if not messages or not isinstance(messages[0], SystemMessage):
                messages = [SystemMessage(content=full_prompt)] + list(messages)
            else:
                messages = [SystemMessage(content=full_prompt)] + [
                    m for m in messages if not isinstance(m, SystemMessage)
                ]
            response = llm_with_tools.invoke(messages)
            # 在 AI 消息前加上角色标记，方便 UI 区分
            if hasattr(response, "content") and response.content:
                response.content = f"**[{role_name}]**: {response.content}"
            return {"messages": [response]}

        return node_fn

    designer_node = make_node(DESIGNER_PROMPT, "设计师")
    developer_node = make_node(DEVELOPER_PROMPT, "开发工程师")
    qa_node = make_node(QA_PROMPT, "QA")

    # 两个独立的 ToolNode，各自回到不同的角色节点
    dev_tool_node = ToolNode(all_tools)
    qa_tool_node = ToolNode(all_tools)

    # 通用路由函数：有 tool_calls → tools，无 → next
    def make_route(tools_key: str, next_key: str):
        """生成路由函数，有 tool_calls 去 tools，否则去 next"""
        def route_fn(state: MessagesState) -> str:
            last_message = state["messages"][-1]
            if hasattr(last_message, "tool_calls") and last_message.tool_calls:
                return tools_key
            return next_key
        return route_fn

    builder = StateGraph(MessagesState)

    builder.add_node("designer", designer_node)
    builder.add_node("developer", developer_node)
    builder.add_node("qa", qa_node)
    builder.add_node("dev_tools", dev_tool_node)
    builder.add_node("qa_tools", qa_tool_node)

    # designer → developer（设计师纯文本输出，不调用工具）
    builder.add_edge(START, "designer")
    builder.add_edge("designer", "developer")

    # developer 工具循环：developer → dev_route → dev_tools → developer
    builder.add_conditional_edges(
        "developer",
        make_route("dev_tools", "qa"),
        {"dev_tools": "dev_tools", "qa": "qa"},
    )
    builder.add_edge("dev_tools", "developer")

    # QA 工具循环：qa → qa_route → qa_tools → qa
    builder.add_conditional_edges(
        "qa",
        make_route("qa_tools", "end"),
        {"qa_tools": "qa_tools", "end": END},
    )
    builder.add_edge("qa_tools", "qa")

    memory = InMemorySaver()
    agent = builder.compile(checkpointer=memory)
    return agent


def build_team_graph(
    model: str = "qwen2.5:7b",
    temperature: float = 0.7,
    top_p: float = 0.9,
    system_prompt: str = "",
):
    """构建 IT 项目团队图（需求分析 → 项目设计 → Coding → QA）"""
    all_tools = PRODUCT_TOOLS + CODE_TOOLS + QA_TOOLS

    llm = ChatOllama(
        model=model,
        temperature=temperature,
        top_p=top_p,
        base_url="http://localhost:11434",
    )
    llm_with_product_tools = llm.bind_tools(PRODUCT_TOOLS)
    llm_with_code_tools = llm.bind_tools(CODE_TOOLS)
    llm_with_qa_tools = llm.bind_tools(QA_TOOLS + [tool for tool in CODE_TOOLS if tool.name == "run_python"])

    base_prompt = system_prompt.strip() if system_prompt.strip() else ""

    def make_node(role_prompt: str, role_name: str, role_llm):
        full_prompt = (base_prompt + "\n\n" if base_prompt else "") + role_prompt

        def node_fn(state: MessagesState):
            messages = state["messages"]
            if not messages or not isinstance(messages[0], SystemMessage):
                messages = [SystemMessage(content=full_prompt)] + list(messages)
            else:
                messages = [SystemMessage(content=full_prompt)] + [
                    message for message in messages if not isinstance(message, SystemMessage)
                ]
            response = role_llm.invoke(messages)
            if hasattr(response, "content") and response.content:
                response.content = f"**[{role_name}]**: {response.content}"
            return {"messages": [response]}

        return node_fn

    def make_route(tools_key: str, next_key: str):
        def route_fn(state: MessagesState) -> str:
            last_message = state["messages"][-1]
            if hasattr(last_message, "tool_calls") and last_message.tool_calls:
                return tools_key
            return next_key
        return route_fn

    builder = StateGraph(MessagesState)

    builder.add_node(
        "analyst",
        make_node(REQUIREMENT_ANALYST_PROMPT, "需求分析师", llm),
    )
    builder.add_node(
        "designer",
        make_node(PROJECT_DESIGNER_PROMPT, "项目设计师", llm_with_product_tools),
    )
    builder.add_node(
        "developer",
        make_node(TEAM_DEVELOPER_PROMPT, "Coding 工程师", llm_with_code_tools),
    )
    builder.add_node("qa", make_node(TEAM_QA_PROMPT, "QA 工程师", llm_with_qa_tools))
    builder.add_node("design_tools", ToolNode(PRODUCT_TOOLS))
    builder.add_node("dev_tools", ToolNode(CODE_TOOLS))
    builder.add_node(
        "qa_tools",
        ToolNode(QA_TOOLS + [tool for tool in CODE_TOOLS if tool.name == "run_python"]),
    )

    builder.add_edge(START, "analyst")
    builder.add_edge("analyst", "designer")
    builder.add_conditional_edges(
        "designer",
        make_route("design_tools", "developer"),
        {"design_tools": "design_tools", "developer": "developer"},
    )
    builder.add_edge("design_tools", "designer")
    builder.add_conditional_edges(
        "developer",
        make_route("dev_tools", "qa"),
        {"dev_tools": "dev_tools", "qa": "qa"},
    )
    builder.add_edge("dev_tools", "developer")
    builder.add_conditional_edges(
        "qa",
        make_route("qa_tools", "end"),
        {"qa_tools": "qa_tools", "end": END},
    )
    builder.add_edge("qa_tools", "qa")

    memory = InMemorySaver()
    agent = builder.compile(checkpointer=memory)
    return agent


def build_graph(
    agent_type: str = "weather",
    model: str = "qwen2.5:7b",
    temperature: float = 0.7,
    top_p: float = 0.9,
    system_prompt: str = "",
):
    """构建 LangGraph 聊天图

    Args:
        agent_type:   Agent 类型 ("weather" / "code" / "product" / "develop_team" / "team")
        model:        Ollama 模型名称
        temperature:  温度参数
        top_p:        Top-P 采样参数
        system_prompt: 自定义系统提示（为空则使用预设）

    Returns:
        编译后的 LangGraph 可执行图（带 InMemorySaver）
    """
    # develop_team 使用独立的多节点协作图
    if agent_type == "develop_team":
        return build_develop_team_graph(
            model=model,
            temperature=temperature,
            top_p=top_p,
            system_prompt=system_prompt,
        )
    if agent_type == "team":
        return build_team_graph(
            model=model,
            temperature=temperature,
            top_p=top_p,
            system_prompt=system_prompt,
        )
    if agent_type == "biz_team":
        return build_biz_team_graph(
            temperature=temperature,
            top_p=top_p,
            system_prompt=system_prompt,
        )

    config = AGENT_CONFIGS.get(agent_type, AGENT_CONFIGS["weather"])
    tools = config["tools"]
    prompt = system_prompt.strip() if system_prompt.strip() else config["system_prompt"]

    # 初始化 LLM 并绑定工具
    llm = ChatOllama(
        model=model,
        temperature=temperature,
        top_p=top_p,
        base_url="http://localhost:11434",
    )
    llm_with_tools = llm.bind_tools(tools)

    # Agent 节点：调用 LLM
    def call_model(state: MessagesState):
        messages = state["messages"]
        # 确保第一条是 SystemMessage
        if not messages or not isinstance(messages[0], SystemMessage):
            messages = [SystemMessage(content=prompt)] + list(messages)
        response = llm_with_tools.invoke(messages)
        return {"messages": [response]}

    # Tools 节点
    tool_node = ToolNode(tools)

    # 条件路由：判断是否有 tool_calls
    def route(state: MessagesState) -> Literal["tools", "end"]:
        last_message = state["messages"][-1]
        if hasattr(last_message, "tool_calls") and last_message.tool_calls:
            return "tools"
        return "end"

    # 构建图
    builder = StateGraph(MessagesState)
    builder.add_node("model", call_model)
    builder.add_node("tools", tool_node)

    builder.add_edge(START, "model")
    builder.add_conditional_edges(
        "model",
        route,
        {
            "tools": "tools",
            "end": END,
        },
    )
    builder.add_edge("tools", "model")  # 工具执行完回到 model 继续推理

    # 带内存的编译图
    memory = InMemorySaver()
    agent = builder.compile(checkpointer=memory)
    return agent


def run_graph_agent_sync(
    user_input: str,
    model: str,
    temperature: float = 0.7,
    top_p: float = 0.9,
    system_prompt: str = "",
) -> str:
    """Run the default LangGraph agent for one user request."""
    graph = build_graph(
        agent_type="weather",
        model=model,
        temperature=temperature,
        top_p=top_p,
        system_prompt=system_prompt,
    )
    result = graph.invoke(
        {"messages": [HumanMessage(content=user_input)]},
        config={"configurable": {"thread_id": "graph-agent"}},
    )
    messages = result.get("messages", [])
    if not messages:
        return ""

    content = getattr(messages[-1], "content", messages[-1])
    if isinstance(content, list):
        return "".join(
            str(item.get("text", item)) if isinstance(item, dict) else str(item)
            for item in content
        )
    return str(content)
