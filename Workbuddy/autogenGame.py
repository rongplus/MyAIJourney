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

# 配置日志
logger = logging.getLogger(__name__)

import os
from pathlib import Path

# 项目根目录
PROJECT_ROOT = Path("./game_project").resolve()

def ensure_project_root():
    PROJECT_ROOT.mkdir(parents=True, exist_ok=True)

def safe_path(filepath: str) -> Path:
    """
    防止Agent访问项目目录之外的文件
    """
    ensure_project_root()
    full_path = (PROJECT_ROOT / filepath).resolve()
    if not str(full_path).startswith(str(PROJECT_ROOT)):
        raise ValueError("Access denied: path outside project root")
    return full_path

def read_file(filepath: str) -> str:
    """
    读取项目文件
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
    写入项目文件
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
    """向项目文件末尾追加一个小代码块，适合模型分块生成大文件。"""
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
    """检查网页入口文件是否存在且 HTML 标签基本完整。"""
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
    列出项目目录文件
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

# ==================== 模型配置 ====================
MODEL_NAME = 'llama3.2:3b-instruct-fp16'

# ==================== Agent 定义 ====================

def createMarketResearcher(model_client):
    """创建市场调研员智能体 - 真正做调研"""
    system_message = """
你是一位经验丰富的 AAA 级游戏市场分析师 + 创意总监。

**第一步：市场调研**
- 当前热门网页/小游戏趋势（Roguelike、Idle、Roguelite、像素风、放置、生存、弹幕、跑酷等）
- 玩家痛点与爆款共性（即时反馈、上瘾机制、成就感、进度保存、手机友好）
- 网页游戏特性：无需安装、秒开即玩、5-15分钟一局

**第二步：产出具体爆款游戏方案**
必须严格按以下格式输出，不要添加多余解释：

**游戏名称**：
**核心卖点**（一句话，为什么玩家会上瘾）：
**目标玩家**：
**美术风格**：
**核心循环**（详细 4-6 步）：
**元进度系统**：
**变现点建议**（网页友好）：
**MVP 范围**（控制在 800-1500 行代码）：
**核心机制具体描述**（数值、规则、胜利/失败条件，必须可直接实现）：

输出完成后说：**"市场调研与方案完成，请 Architect 设计架构"**
"""
    return AssistantAgent(
        name="MarketResearcher",
        model_client=model_client,
        system_message=system_message,
    )


def createArchitectAgent(model_client):
    """技术架构师"""
    system_message = """
你是一位严谨的游戏技术架构师。

根据游戏方案设计清晰、可维护的项目结构。

输出格式：

**项目结构：**
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
├── assets/ (描述需要的资源)
└── README.md

**技术选型与实现要点：**
**模块划分与解耦方案：**
**潜在风险与规避：**
**开发优先级顺序：**

输出完成后说：**"架构设计完成，请 GameDesigner 进行详细设计"**
"""
    return AssistantAgent(
        name="ArchitectAgent",
        model_client=model_client,
        system_message=system_message,
    )


def createGameDesigner(model_client):
    """游戏设计师"""
    system_message = """
你是一位顶级游戏设计师。

接收到方案后，按以下结构输出：

1. **游戏世界与叙事**
2. **玩家系统**（属性、控制、成长曲线）
3. **敌人与关卡设计**
4. **战斗/核心玩法系统**（详细数值、状态机）
5. **UI/UX 设计**（布局、输入）
6. **音效与视觉反馈**

**任务分解**（必须输出 JSON）：
```json
{
  "tasks": [
    {
      "id": "TASK-001",
      "name": "基础画布与游戏循环",
      "files": ["index.html", "js/main.js"],
      "description": "...",
      "acceptance_criteria": ["...", "..."]
    }
  ]
}
每个任务控制在 150-300 行代码。
输出完成后说："设计与任务拆解完成，请 Programmer 开始实现"
"""
    return AssistantAgent(
    name="GameDesigner",
    model_client=model_client,
    system_message=system_message,
    )
def createGameProgrammar(model_client):
    """游戏程序员 - 重点强化"""
    system_message = """
    你是一位极度严谨的独立游戏开发者。
    可用工具：read_file、write_file、append_file、list_files、validate_project
    铁律（必须严格遵守）：

    每次行动前必须先调用 list_files("") 查看当前状态
    修改文件前必须先 read_file
    每生成/修改一个文件立即调用 write_file 或 append_file 保存
    禁止只输出代码不保存
    禁止 TODO、伪代码、省略实现
    不要一次生成大文件：每次工具调用最多写入 60-100 行代码。
    大文件必须先用 write_file(..., complete=False) 写入第一块，再用 append_file 逐块追加。
    index.html 必须最后确认包含完整的 </html>，不能保存半截 HTML。
    采用增量开发，优先修改现有代码
    每完成一个 TASK 后调用 list_files 和 validate_project 验证并总结

    技术栈：纯 HTML5 Canvas + 原生 JavaScript + CSS
    输出格式示例：
    [先调用 list_files]

[调用 read_file]

[调用 write_file]

FILE: js/player.js
<完整代码>
完成当前阶段后说："本阶段代码已全部写入，请 QA 测试"
"""
    return AssistantAgent(
    name="GameProgrammar",
    model_client=model_client,
    tools=[read_file, write_file, append_file, list_files, validate_project],
    system_message=system_message,
    )

def createQA(model_client):
    """质量保证"""
    system_message = """
    你是专业的网页游戏 PlayTest AI。
    测试重点：

    index.html 是否能正常打开
    浏览器控制台是否有 JS 错误
    游戏是否可操作（键盘/触屏）
    FPS 是否稳定（≥45）
    核心循环是否通畅
    是否存在卡死、内存泄漏等严重问题

    输出格式：
    测试结果：PASS / FAIL / NEEDS_FIX
    详细报告：
    {
  "bugs": [{"file": "...", "description": "...", "severity": "high/medium/low"}],
  "performance": {"fps": "...", "issues": "..."},
  "suggestions": ["..."],
  "next_actions": [
  发现严重问题时明确说 "需要程序员修复以下问题"
"""
    return AssistantAgent(
    name="QA",
    model_client=model_client,
    system_message=system_message,
    )

def create_user_proxy():
    return UserProxyAgent(
    name="UserProxy",
    description="用户代理，负责最终验证和终止流程。测试通过后回复 TERMINATE。",
    )


class AutoGenGameClient:
    """将 AutoGen 游戏开发团队包装成与普通聊天客户端兼容的接口。"""

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
        """运行一次完整的游戏开发流程并返回团队消息。"""
        result = await self.team_chat.run(task=task)
        messages = getattr(result, "messages", [])
        return "\n\n".join(
            f"{getattr(message, 'source', 'agent')}: {getattr(message, 'content', message)}"
            for message in messages
        )

    async def stream(self, task: str):
        """逐条输出团队事件，供 UI 实时显示进度。"""
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
        """兼容普通客户端的调用方式，执行游戏专家任务并返回结果。"""
        del model, temperature, top_p, conversation_id
        display_history = list(history or [])
        display_history.append({"role": "user", "content": user_input})
        display_history.append({"role": "assistant", "content": ""})
        yield display_history, ""
        task = f"""
        用户需求：
        {user_input}

        请严格按照以下流程开发一个完整可玩的网页游戏：
        MarketResearcher → 进行市场调研并产出具体游戏方案
        ArchitectAgent → 设计合理项目结构
        GameDesigner → 完成详细设计 + 任务拆解
        GameProgrammar → 按任务顺序使用工具 incrementally 实现代码（必须写入真实文件）
        QA → 进行测试并反馈
        如有问题则循环回 Programmer 修复，直到 QA 通过

        最终目标：生成一个可以直接用浏览器打开 game_project/index.html 游玩的完整游戏。
        支持键盘或触屏操作，具备核心循环、进度、得分等基本元素。
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
            display_history[-1]["content"] = f"❌ Game专家调用失败：{error}"
            yield display_history, ""
        finally:
            loop.run_until_complete(stream.aclose())
            loop.close()

    def close(self):
        """释放 AutoGen 模型客户端资源。"""
        return asyncio.run(self.model_client.close())


async def run_software_development_team(task=None):
    """保留命令行入口的异步调用方式。"""
    client = AutoGenGameClient()
    task = task or "请开发一个完整可玩的网页游戏。"
    try:
        return await client.run(task)
    finally:
        await client.model_client.close()



if __name__ == "__main__":
    print("🚀 启动 Auto Game 开发团队...")
    ensure_project_root()
    result = asyncio.run(run_software_development_team())
    print(result)
    print("✅ 开发流程结束")