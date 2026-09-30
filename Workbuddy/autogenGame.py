import os
import asyncio
from autogen_ext.models.ollama import OllamaChatCompletionClient
from autogen_agentchat.agents import AssistantAgent
from autogen_agentchat.agents import UserProxyAgent 

from autogen_agentchat.teams import RoundRobinGroupChat
from autogen_agentchat.conditions import TextMentionTermination

from autogen_agentchat.ui import Console

import threading
import logging

from autogen_core import EVENT_LOGGER_NAME

logging.basicConfig(
    filename="autogen.log",
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(EVENT_LOGGER_NAME + ".auto.game")

# Logging configuration
logger = logging.getLogger(__name__)

import os
from pathlib import Path

# Project root directory
PROJECT_ROOT = Path("./game_project").resolve()

def ensure_project_root():
    PROJECT_ROOT.mkdir(parents=True, exist_ok=True)

def safe_path(filepath: str) -> Path:
    """
    Prevent the Agent from accessing files outside the project directory.
    """
    ensure_project_root()
    full_path = (PROJECT_ROOT / filepath).resolve()
    if not str(full_path).startswith(str(PROJECT_ROOT)):
        raise ValueError("Access denied: path outside project root")
    return full_path

def read_file(filepath: str) -> str:
    """
    Read a project file.
    """
    try:
        path = safe_path(filepath)
        if not path.exists():
            return f"File not found: {filepath}"
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    except Exception as e:
        return f"Error reading file: {e}"

def write_file(filepath: str, content: str, complete: bool = True) -> str:
    """
    Write to a project file.
    """
    logger.info(f"[TOOL] Writing {filepath} | Content length: {len(content)}")
    try:
        path = safe_path(filepath)
        normalized_content = content.rstrip()
        if complete and filepath.lower().endswith(('.html', '.htm')):
            required_markers = ('<html', '</html>', '<body', '</body>')
            if not all(marker in normalized_content.lower() for marker in required_markers):
                return (
                    f"Error writing file: {filepath} appears incomplete. "
                    "For HTML, include complete html/body tags and retry."
                )
        if complete and normalized_content.endswith(('<', '</', '"', "'", '=', ':')):
            return f"Error writing file: {filepath} appears truncated; retry with a complete chunk."
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        return f"Successfully wrote file: {filepath}"
    except Exception as e:
        return f"Error writing file: {e}"

def append_file(filepath: str, content: str) -> str:
    """Append a small code block to the end of a project file, suitable for incrementally generating large files."""
    logger.info(f"[TOOL] Appending {filepath} | Content length: {len(content)}")
    try:
        path = safe_path(filepath)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "a", encoding="utf-8") as f:
            f.write(content)
        return f"Successfully appended file: {filepath}"
    except Exception as e:
        return f"Error appending file: {e}"

def validate_project() -> str:
    """Check whether the web entry file exists and HTML tags are basically complete."""
    index_path = safe_path("index.html")
    if not index_path.exists():
        return "Validation failed: index.html does not exist"
    content = index_path.read_text(encoding="utf-8").lower()
    required_markers = ("<html", "</html>", "<body", "</body>")
    missing = [marker for marker in required_markers if marker not in content]
    if missing:
        return f"Validation failed: index.html is incomplete; missing {missing}"
    return "Validation passed: index.html is complete"

def list_files(subdir: str = "") -> str:
    """
    List files in the project directory.
    """
    try:
        root = safe_path(subdir)
        if not root.exists():
            return "Directory does not exist"
        results = []
        for current_root, dirs, files in os.walk(root):
            rel_root = os.path.relpath(current_root, PROJECT_ROOT)
            for file in files:
                results.append(os.path.join(rel_root, file))
        if not results:
            return "No files found"
        return "\n".join(sorted(results))
    except Exception as e:
        return f"Error listing files: {e}"

# ==================== Model Configuration ====================
MODEL_NAME = 'llama3.2:3b-instruct-fp16'

# ==================== Agent Definitions ====================

def createMarketResearcher(model_client):
    """Create the Market Researcher agent - does the actual research."""
    system_message = """
You are an experienced AAA game market analyst and creative director.

**Step 1: Market Research**
- Current popular web/casual game trends (Roguelike, Idle, Roguelite, Pixel art, Idle, Survival, Bullet hell, Runner, etc.)
- Player pain points and common traits of hit games (instant feedback, addictive mechanics, sense of achievement, progress saving, mobile-friendly)
- Web game characteristics: no installation required, instant play, 5-15 minute sessions

**Step 2: Produce a specific hit game proposal**
Must output strictly in the following format, with no extra explanations:

**Game Name**:
**Core Selling Point** (one sentence, why players will get addicted):
**Target Players**:
**Art Style**:
**Core Loop** (detailed 4-6 steps):
**Meta-Progression System**:
**Monetization Suggestions** (web-friendly):
**MVP Scope** (keep it within 800-1500 lines of code):
**Core Mechanic Detailed Description** (values, rules, win/lose conditions, must be directly implementable):

When done, say: **"Market research and proposal complete. Architect, please design the architecture."**
"""
    return AssistantAgent(
        name="MarketResearcher",
        model_client=model_client,
        system_message=system_message,
    )


def createArchitectAgent(model_client):
    """Technical Architect."""
    system_message = """
You are a rigorous game technical architect.

Design a clear, maintainable project structure based on the game proposal.

Output format:

**Project Structure:**
game_project/
├── index.html
├── css/style.css
├── js/
│   ├── main.js
│   ├── game.js
│   ├── player.js
│   ├── enemy.js
│   ├── weapon.js
│   ├── ui.js
│   └── utils.js
├── assets/ (describe needed resources)
└── README.md

**Tech Stack & Implementation Notes:**
**Module Breakdown & Decoupling Plan:**
**Potential Risks & Mitigations:**
**Development Priority Order:**

When done, say: **"Architecture design complete. GameDesigner, please proceed with detailed design."**
"""
    return AssistantAgent(
        name="ArchitectAgent",
        model_client=model_client,
        system_message=system_message,
    )


def createGameDesigner(model_client):
    """Game Designer."""
    system_message = """
You are a top-tier game designer.

After receiving the proposal, output in the following structure:

1. **Game World & Narrative**
2. **Player System** (attributes, controls, growth curve)
3. **Enemies & Level Design**
4. **Combat/Core Gameplay System** (detailed values, state machine)
5. **UI/UX Design** (layout, input)
6. **Sound & Visual Feedback**

**Task Breakdown** (must output JSON):
```json
{
  "tasks": [
    {
      "id": "TASK-001",
      "name": "Basic Canvas & Game Loop",
      "files": ["index.html", "js/main.js"],
      "description": "...",
      "acceptance_criteria": ["...", "..."]
    }
  ]
}
Keep each task within 150-300 lines of code.
When done, say: "Design and task breakdown complete. Programmer, please start implementation."
"""
    return AssistantAgent(
    name="GameDesigner",
    model_client=model_client,
    system_message=system_message,
    )
def createGameProgrammar(model_client):
    """Game Programmer - heavily reinforced."""
    system_message = """
    You are an extremely rigorous indie game developer.
    Available tools: read_file, write_file, append_file, list_files, validate_project
    Iron rules (must be strictly followed):

    Before every action, call list_files("") to check the current state
    Before modifying a file, you must first read_file
    Every time you generate/modify a file, immediately call write_file or append_file to save it
    Never output code without saving it
    No TODOs, no pseudo-code, no omitted implementations
    Do not generate large files in one go: write at most 60-100 lines of code per tool call.
    For large files, first use write_file(..., complete=False) to write the first chunk, then use append_file to add chunks incrementally.
    index.html must ultimately be confirmed to include a complete </html> tag; do not save half-finished HTML.
    Use incremental development; prefer modifying existing code
    After completing each TASK, call list_files and validate_project to verify and summarize

    Tech stack: pure HTML5 Canvas + vanilla JavaScript + CSS
    Output format example:
    [First call list_files]

[Call read_file]

[Call write_file]

FILE: js/player.js
<complete code>
When the current phase is done, say: "All code for this phase has been written. QA, please test."
"""
    return AssistantAgent(
        name="GameProgrammar",
        model_client=model_client,
        tools=[read_file, write_file, append_file, list_files, validate_project],
        system_message=system_message,
    )

def createQA(model_client):
    """Quality Assurance."""
    system_message = """
    You are a professional web game PlayTest AI.
    Testing focus:

    Whether index.html can open normally
    Whether there are JS errors in the browser console
    Whether the game is operable (keyboard/touch)
    Whether FPS is stable (>=45)
    Whether the core loop is smooth
    Whether there are serious issues like freezing, memory leaks, etc.

    Output format:
    Test result: PASS / FAIL / NEEDS_FIX
    Detailed report:
    {
  "bugs": [{"file": "...", "description": "...", "severity": "high/medium/low"}],
  "performance": {"fps": "...", "issues": "..."},
  "suggestions": ["..."],
  "next_actions": [
  When serious problems are found, clearly say "The programmer needs to fix the following issues"
"""
    return AssistantAgent(
        name="QA",
        model_client=model_client,
        system_message=system_message,
    )

def create_user_proxy():
    return UserProxyAgent(
        name="UserProxy",
        description="User proxy, responsible for final verification and terminating the workflow. Reply TERMINATE after tests pass.",
    )


class AutoGenGameClient:
    """Wraps the AutoGen game development team into an interface compatible with the regular chat client."""

    def __init__(self, model_name: str = MODEL_NAME):
        self.model_name = model_name
        self.model_client = OllamaChatCompletionClient(
            model=model_name,
            options={
                "num_ctx": 16384,
                "num_predict": 4096,
                "temperature": 0.2,
            },
        )
        self.team_chat = self._create_team()

    def _create_team(self):
        agents = [
            createMarketResearcher(self.model_client),
            createArchitectAgent(self.model_client),
            createGameDesigner(self.model_client),
            createGameProgrammar(self.model_client),
            createQA(self.model_client),
        ]
        return RoundRobinGroupChat(
            participants=agents,
            termination_condition=TextMentionTermination("TERMINATE"),
            max_turns=35,
        )

    async def run(self, task: str):
        """Run a complete game development workflow and return the team's messages."""
        result = await self.team_chat.run(task=task)
        messages = getattr(result, "messages", [])
        return "\n\n".join(
            f"{getattr(message, 'source', 'agent')}: {getattr(message, 'content', message)}"
            for message in messages
        )

    async def stream(self, task: str):
        """Output team events one by one for real-time UI display."""
        async for message in self.team_chat.run_stream(task=task):
            source = getattr(message, "source", "system")
            content = getattr(message, "content", message)
            if isinstance(content, list):
                content = "\n".join(str(item) for item in content)
            yield f"[{source}]\n{content}"

    def streamChat(
        self,
        user_input,
        history=None,
        model=None,
        temperature=None,
        top_p=1.0,
        conversation_id="default",
    ):
        """Compatible with the regular client calling convention, executes the game expert task and returns results."""
        del model, temperature, top_p, conversation_id
        display_history = list(history or [])
        display_history.append({"role": "user", "content": user_input})
        display_history.append({"role": "assistant", "content": ""})
        yield display_history, ""
        task = f"""
        User requirement:
        {user_input}

        Please strictly follow the workflow below to develop a complete, playable web game:
        MarketResearcher -> Conduct market research and produce a specific game proposal
        ArchitectAgent -> Design a reasonable project structure
        GameDesigner -> Complete detailed design + task breakdown
        GameProgrammar -> Implement code incrementally using tools (must write real files)
        QA -> Test and provide feedback
        If issues are found, loop back to Programmer for fixes until QA passes

        Final goal: Generate a complete game that can be played directly by opening game_project/index.html in a browser.
        Support keyboard or touch controls, with core loop, progress, scoring, and other basic elements.
        """
        loop = asyncio.new_event_loop()
        stream = self.stream(task)
        try:
            progress = []
            while True:
                try:
                    message = loop.run_until_complete(stream.__anext__())
                except StopAsyncIteration:
                    break
                progress.append(message)
                display_history[-1]["content"] = "\n\n".join(progress)
                yield display_history, ""
        except Exception as error:
            display_history[-1]["content"] = f"Game Expert failed: {error}"
            yield display_history, ""
        finally:
            loop.run_until_complete(stream.aclose())
            loop.close()

    def close(self):
        """Release AutoGen model client resources."""
        return asyncio.run(self.model_client.close())


async def run_software_development_team(task=None):
    """Retains the async calling convention for the command-line entry point."""
    client = AutoGenGameClient()
    task = task or "Please develop a complete, playable web game."
    try:
        return await client.run(task)
    finally:
        await client.model_client.close()



if __name__ == "__main__":
    print("Starting Auto Game development team...")
    ensure_project_root()
    result = asyncio.run(run_software_development_team())
    print(result)
    print("Development workflow complete.")
