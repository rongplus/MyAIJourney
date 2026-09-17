from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path

from crewai import Agent, Task, Crew, Process
from crewai import LLM
from crewai.tools import tool


PROJECT_ROOT = Path(__file__).resolve().parent / "game_project"


@tool("save_generated_code")
def save_generated_code(code: str, filepath: str = "shooting_game.py") -> str:
    """Save generated source code under the local project directory.

    Args:
        code: Complete source code to write to the file.
        filepath: Relative path. Defaults to ``shooting_game.py``.
    """
    if filepath != "shooting_game.py":
        return "Error: this task must save the code as shooting_game.py."

    project_root = PROJECT_ROOT.resolve()
    target_path = (project_root / filepath).resolve()
    if target_path != project_root and project_root not in target_path.parents:
        return "Error: filepath must stay inside the project directory."
    if not target_path.name:
        return "Error: filepath must name a file."

    try:
        target_path.parent.mkdir(parents=True, exist_ok=True)
        target_path.write_text(code, encoding="utf-8")
        return f"Successfully saved generated code to {target_path.relative_to(project_root)}"
    except OSError as error:
        return f"Error saving generated code: {error}"
# 配置LLM（这里可以用OpenAI，也可以用本地的大模型）
# 记得换成你自己的API Key
#llm = ChatOpenAI(model="gpt-4-turbo", temperature=0.7)
#llm = ChatOllama(model="llama3", temperature=0.7,base_url="http://localhost:11434")

class CrewAIClient:
    """将 CrewAI 软件开发团队包装成聊天客户端。"""

    def __init__(self, model_name="ollama/llama3", qa_model_name="ollama/llama3.2:3b-instruct-fp16"):
        self.llm = LLM(model=model_name, base_url="http://localhost:11434")
        self.qa_llm = LLM(model=qa_model_name, base_url="http://localhost:11434")

    def _create_crew(self, user_input):
        """根据本次用户需求创建一组相互衔接的任务。"""
        product_manager = Agent(
            role="资深产品经理",
            goal="分析用户需求，产出清晰、详细的软件需求文档(PRD)",
            backstory="你是一名拥有10年经验的互联网产品经理，擅长把模糊需求拆解成技术文档。",
            verbose=True,
            allow_delegation=False,
            llm=self.llm,
        )
        developer = Agent(
            role="首席Python架构师",
            goal="根据需求文档，编写高质量、可运行的Python代码并保存到项目文件",
            backstory="你是一名顶级Python专家，只写优雅、高效、符合PEP8规范的代码。",
            verbose=True,
            allow_delegation=False,
            llm=self.llm,
            tools=[save_generated_code],
        )
        qa_engineer = Agent(
            role="质量保证(QA)专家",
            goal="审查代码，修复Bug，确保代码能完美运行并保存最终版本",
            backstory="你是一名严格的测试专家，会检查语法、逻辑和安全问题。",
            verbose=True,
            allow_delegation=False,
            llm=self.qa_llm,
            tools=[save_generated_code],
        )

        task_analysis = Task(
            description=f"用户需求：{user_input}\n请分析核心功能、交互方式、界面布局和验收标准。",
            agent=product_manager,
            expected_output="一份包含功能点和验收标准的需求列表文本。",
        )
        task_coding = Task(
            description=(
                "根据需求分析，使用Python实现完整功能，输出可直接运行的代码。"
                "必须调用 save_generated_code，并使用默认文件名，将完整代码保存到 "
                "game_project/。"
            ),
            agent=developer,
            expected_output="完整的Python代码字符串。",
        )
        task_review = Task(
            description=(
                "检查代码的语法、逻辑和安全性；发现问题时修复并调用 save_generated_code 保存最终代码，"
                "否则也调用 save_generated_code 确认最终代码已经写入 "
                "**.py。最终文件必须是 **.py。"
            ),
            agent=qa_engineer,
            expected_output="经过审查的最终Python代码，或Bug修改建议。",
        )
        return Crew(
            agents=[product_manager, developer, qa_engineer],
            tasks=[task_analysis, task_coding, task_review],
            process=Process.sequential,
            verbose=True,
            tracing=True,
        )

    def run(self, user_input):
        output = StringIO()
        with redirect_stdout(output), redirect_stderr(output):
            result = self._create_crew(user_input).kickoff()

        logs = output.getvalue().strip()
        return f"{logs}\n\n最终结果：\n{result}" if logs else str(result)

    def streamChat(self, user_input, history=None, model=None, temperature=None, top_p=None, conversation_id=None):
        del model, temperature, top_p, conversation_id
        display_history = list(history or [])
        display_history.append({"role": "user", "content": user_input})
        display_history.append({"role": "assistant", "content": "正在执行 CrewAI 软件开发团队..."})
        yield display_history, ""
        try:
            display_history[-1]["content"] = str(self.run(user_input))
        except Exception as error:
            display_history[-1]["content"] = f"❌ CrewAI 调用失败：{error}"
        yield display_history, ""


if __name__ == "__main__":
    print(CrewAIClient().run("请开发一个基于命令行的贪吃蛇游戏。"))


'''

# 1. 定义产品经理 Agent
product_manager = Agent(
    role='资深产品经理',
    goal='分析用户需求，产出清晰、详细的软件需求文档(PRD)',
    backstory="""你是一名拥有10年经验的互联网产品经理。
    你擅长挖掘用户痛点，并且能把模糊的一句话需求，拆解成程序员能看懂的技术文档。
    你对细节要求极高，不允许有逻辑漏洞。""",
    verbose=True, # 让他干活时多唠叨几句，我们在终端能看到
    allow_delegation=False,
    llm=llm
)

# 2. 定义Python开发 Agent
developer = Agent(
    role='首席Python架构师',
    goal='根据需求文档，编写高质量、可运行的Python代码',
    backstory="""你是一名顶级黑客和Python专家。
    你只写优雅、高效、符合PEP8规范的代码。
    你能够解决复杂算法问题，并且会给关键逻辑加上详细注释。""",
    verbose=True,
    allow_delegation=False,
    llm=llm
)

llm2 = LLM(
    model="ollama/llama3.2:3b-instruct-fp16",
    base_url="http://localhost:11434"
)

# 3. 定义测试工程师 Agent
qa_engineer = Agent(
    role='质量保证(QA)专家',
    goal='审查代码，寻找Bug，确保代码能完美运行',
    backstory="""你是一名以“找茬”为乐的测试专家。
    你会严格审查开发人员的代码，检查是否存在安全隐患、逻辑死循环或语法错误。
    如果发现问题，你会毫不留情地打回重写。""",
    verbose=True,
    allow_delegation=False,
    llm=llm2
)


#三、 派发任务 (Tasks)
#有了人，还得有活儿。 我们需要定义任务，并指定谁来做。


    # 任务1：需求分析
task_analysis = Task(
    description="""
    用户想要一个'基于命令行的贪吃蛇游戏'。
    请分析该需求，定义游戏规则、控制方式（WASD）、界面布局以及计分规则。
    产出一份简短但核心逻辑清晰的需求列表。
    """,
    agent=product_manager,
    expected_output="一份包含游戏规则和功能点的需求列表文本。"
)

# 任务2：编写代码
task_coding = Task(
    description="""
    使用Python的curses库或标准库实现上述贪吃蛇游戏。
    注意：代码必须是一个完整的、可直接运行的.py文件内容。
    处理好蛇撞墙、吃到食物变长等逻辑。
    """,
    agent=developer,
    expected_output="完整的Python代码字符串。"
)

# 任务3：代码审查
task_review = Task(
    description="""
    检查开发人员编写的代码。
    1. 检查是否有语法错误。
    2. 检查逻辑是否符合PM的需求。
    3. 如果代码完美，直接输出代码；如果有问题，列出修改建议。
    """,
    agent=qa_engineer,
    expected_output="经过审查的最终Python代码，或Bug修改建议。"
)


#四、 组建团队并开工 (Crew)
#这是最燃的一步。 我们将这些Agent串联起来，组成一个 Crew（团队）。


    # 组建团队
dev_team = Crew(
    agents=[product_manager, developer, qa_engineer],
    tasks=[task_analysis, task_coding, task_review],
    process=Process.sequential, # 顺序执行：PM -> Dev -> QA
    verbose=True,
    tracing=True   # ✅ 就在这里

)

print(" 虚拟软件开发团队正在集结...")
print(" 老板发布任务：做一个贪吃蛇游戏")

# 开工！
result = dev_team.kickoff()

print("\n\n########################")
print("✅ 最终交付结果：")
print(result)
'''

