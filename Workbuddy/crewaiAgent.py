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
# Configure LLM (can use OpenAI or a local large model here)
# Remember to replace with your own API Key
#llm = ChatOpenAI(model="gpt-4-turbo", temperature=0.7)
#llm = ChatOllama(model="llama3", temperature=0.7,base_url="http://localhost:11434")

class CrewAIClient:
    """Wraps the CrewAI software development team into a chat client."""

    def __init__(self, model_name="ollama/llama3", qa_model_name="ollama/llama3.2:3b-instruct-fp16"):
        self.llm = LLM(model=model_name, base_url="http://localhost:11434")
        self.qa_llm = LLM(model=qa_model_name, base_url="http://localhost:11434")

    def _create_crew(self, user_input):
        """Create a set of interconnected tasks based on the user's current request."""
        product_manager = Agent(
            role="Senior Product Manager",
            goal="Analyze user requirements and produce a clear, detailed software requirements document (PRD)",
            backstory="You are a product manager with 10 years of experience in internet products, skilled at breaking down vague requirements into technical documents.",
            verbose=True,
            allow_delegation=False,
            llm=self.llm,
        )
        developer = Agent(
            role="Chief Python Architect",
            goal="Write high-quality, runnable Python code based on the requirements document and save it to the project file",
            backstory="You are a top-tier Python expert who only writes elegant, efficient, PEP8-compliant code.",
            verbose=True,
            allow_delegation=False,
            llm=self.llm,
            tools=[save_generated_code],
        )
        qa_engineer = Agent(
            role="Quality Assurance (QA) Expert",
            goal="Review code, fix bugs, and ensure the code runs perfectly and the final version is saved",
            backstory="You are a strict testing expert who checks for syntax, logic, and security issues.",
            verbose=True,
            allow_delegation=False,
            llm=self.qa_llm,
            tools=[save_generated_code],
        )

        task_analysis = Task(
            description=f"User requirement: {user_input}\nPlease analyze the core features, interaction patterns, UI layout, and acceptance criteria.",
            agent=product_manager,
            expected_output="A requirements list with feature points and acceptance criteria.",
        )
        task_coding = Task(
            description=(
                "Based on the requirements analysis, implement the full functionality in Python, producing directly runnable code. "
                "Must call save_generated_code with the default filename to save the complete code to "
                "game_project/."
            ),
            agent=developer,
            expected_output="A complete Python code string.",
        )
        task_review = Task(
            description=(
                "Check the code for syntax, logic, and security; fix issues and call save_generated_code to save the final code, "
                "otherwise also call save_generated_code to confirm the final code has been written to "
                "**.py. The final file must be **.py."
            ),
            agent=qa_engineer,
            expected_output="Reviewed final Python code, or bug fix suggestions.",
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
        return f"{logs}\n\nFinal result:\n{result}" if logs else str(result)

    def streamChat(self, user_input, history=None, model=None, temperature=None, top_p=None, conversation_id=None):
        del model, temperature, top_p, conversation_id
        display_history = list(history or [])
        display_history.append({"role": "user", "content": user_input})
        display_history.append({"role": "assistant", "content": "Running CrewAI software development team..."})
        yield display_history, ""
        try:
            display_history[-1]["content"] = str(self.run(user_input))
        except Exception as error:
            display_history[-1]["content"] = f"CrewAI failed: {error}"
        yield display_history, ""


if __name__ == "__main__":
    print(CrewAIClient().run("Please develop a command-line-based Snake game."))


'''

# 1. Define the Product Manager Agent
product_manager = Agent(
    role='Senior Product Manager',
    goal='Analyze user requirements and produce a clear, detailed software requirements document (PRD)',
    backstory="""You are a product manager with 10 years of experience in internet products.
    You excel at uncovering user pain points and can break down a vague one-sentence requirement
    into a technical document that programmers can understand.
    You demand extreme attention to detail and do not allow logical gaps.""",
    verbose=True, # Let it talk more while working, so we can see it in the terminal
    allow_delegation=False,
    llm=llm
)

# 2. Define the Python Developer Agent
developer = Agent(
    role='Chief Python Architect',
    goal='Write high-quality, runnable Python code based on the requirements document',
    backstory="""You are a top-tier hacker and Python expert.
    You only write elegant, efficient, PEP8-compliant code.
    You can solve complex algorithmic problems and add detailed comments to key logic.""",
    verbose=True,
    allow_delegation=False,
    llm=llm
)

llm2 = LLM(
    model="ollama/llama3.2:3b-instruct-fp16",
    base_url="http://localhost:11434"
)

# 3. Define the Test Engineer Agent
qa_engineer = Agent(
    role='Quality Assurance (QA) Expert',
    goal='Review code, find bugs, and ensure the code runs perfectly',
    backstory="""You are a testing expert who enjoys "finding faults."
    You will rigorously review the developer's code, checking for security risks,
    infinite loops, or syntax errors. If problems are found, you will mercilessly
    send it back for a rewrite.""",
    verbose=True,
    allow_delegation=False,
    llm=llm2
)


# Three: Dispatch Tasks
# Now that we have people, we need work. We need to define tasks and assign them.


    # Task 1: Requirements Analysis
task_analysis = Task(
    description="""
    The user wants a 'command-line-based Snake game.'
    Please analyze the requirement, define game rules, controls (WASD), UI layout, and scoring rules.
    Produce a concise but logically clear requirements list.
    """,
    agent=product_manager,
    expected_output="A requirements list with game rules and feature points."
)

# Task 2: Write Code
task_coding = Task(
    description="""
    Implement the above Snake game using Python's curses library or standard library.
    Note: The code must be a complete, directly runnable .py file.
    Handle snake-wall collision, eating food to grow, etc.
    """,
    agent=developer,
    expected_output="A complete Python code string."
)

# Task 3: Code Review
task_review = Task(
    description="""
    Check the code written by the developer.
    1. Check for syntax errors.
    2. Check whether the logic matches the PM's requirements.
    3. If the code is perfect, output it directly; if there are issues, list fix suggestions.
    """,
    agent=qa_engineer,
    expected_output="Reviewed final Python code, or bug fix suggestions."
)


# Four: Form the Team and Start Working (Crew)
# This is the exciting step. We chain these Agents together to form a Crew.


    # Form the team
dev_team = Crew(
    agents=[product_manager, developer, qa_engineer],
    tasks=[task_analysis, task_coding, task_review],
    process=Process.sequential, # Sequential execution: PM -> Dev -> QA
    verbose=True,
    tracing=True   # Here it is

)


print(" Virtual software development team assembling...")
print(" Boss issues task: make a Snake game")

# Start working!
result = dev_team.kickoff()

print("\n\n########################")
print("Final deliverable:")
print(result)
'''
