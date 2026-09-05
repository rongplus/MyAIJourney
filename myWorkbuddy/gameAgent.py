
import os
import asyncio
from autogen_ext.models.ollama import OllamaChatCompletionClient
from autogen_ext.models.openai import OpenAIChatCompletionClient
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
file_lock = threading.Lock()
logger = logging.getLogger(EVENT_LOGGER_NAME + ".augo.game")

# 配置日志
logger = logging.getLogger(__name__)

"""
llm_client = HelloAgentsLLM(
    provider="vllm",
    model="qwen3.5:latest", # 需与服务启动时指定的模型一致
    base_url="http://localhost:8000/v1",
    api_key="vllm" # 本地服务通常不需要真实API Key，可填任意非空字符串
)
"""


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
    logger.info("正在启动safe_path...")
    ensure_project_root()

    full_path = (PROJECT_ROOT / filepath).resolve()

    if not str(full_path).startswith(str(PROJECT_ROOT)):
        raise ValueError("Access denied: path outside project root")

    return full_path


def read_file(filepath: str) -> str:
    """
    读取项目文件

    Args:
        filepath: 相对路径，例如:
            index.html
            js/player.js

    Returns:
        文件内容
    """
    logger.info("正在启动read_file...")
    try:
        path = safe_path(filepath)

        if not path.exists():
            return f"File not found: {filepath}"

        with open(path, "r", encoding="utf-8") as f:
            return f.read()

    except Exception as e:
        return f"Error reading file: {e}"


def write_file(filepath: str, content: str) -> str:
    """
    写入项目文件

    Args:
        filepath: 相对路径
        content: 文件内容

    Returns:
        执行结果
    """
    logger.info("正在启动write_file...")
    logger.info(f"[TOOL]Writing {filepath}")
    logger.info(f"Content length: {len(content)}")

    try:
        path = safe_path(filepath)

        path.parent.mkdir(parents=True, exist_ok=True)

        with open(path, "w", encoding="utf-8") as f:
            f.write(content)

        return f"Successfully wrote file: {filepath}"

    except Exception as e:
        return f"Error writing file: {e}"


def list_files(subdir: str = "") -> str:
    """
    列出项目目录文件

    Args:
        subdir: 子目录

    Returns:
        文件树
    """
    logger.info("正在启动list_files...")
    try:
        root = safe_path(subdir)

        if not root.exists():
            return "Directory does not exist"

        results = []

        for current_root, dirs, files in os.walk(root):

            rel_root = os.path.relpath(current_root, PROJECT_ROOT)

            for file in files:
                results.append(
                    os.path.join(rel_root, file)
                )

        if not results:
            return "No files found"

        return "\n".join(sorted(results))

    except Exception as e:
        return f"Error listing files: {e}"




# Create an agent that uses the OpenAI GPT-4o model.
MODEL_NAME  = 'llama3.2:3b-instruct-fp16'
#MODEL_NAME  = 'gemma4:latest'
# Text
model_client_ollama = OllamaChatCompletionClient(
    model=MODEL_NAME,
    # api_key="LLAMA_API_KEY"
)


"""
市场分析
    ↓
游戏设计师
    ↓
技术架构师
    ↓
游戏程序员
    ↓
自动测试
    ↓
继续迭代
"""
def createMarketResearcher(model_client):
    """创建市场调研员智能体"""
    system_message = """
   你是一位经验丰富的 AAA 级游戏市场分析师 + 创意总监。

**第一步：市场调研**
- 分析当前热门网页/小游戏趋势（Roguelike、Idle、Roguelite、像素风、放置、生存等）
- 找出玩家痛点和爆款共性（上瘾机制、即时反馈、成就感、社交分享等）
- 考虑网页游戏特性：无需安装、5分钟上手、手机友好

**第二步：产出爆款游戏方案**
必须严格按以下格式输出：

**游戏名称**：
**核心卖点**（一句话，为什么会上瘾）：
**目标玩家**：
**美术风格**：
**核心循环**（详细描述 3-5 步）：
**元进度系统**：
**变现点建议**（可选，网页游戏友好）：
**MVP 范围**（控制在 800-1200 行代码可完成）：
**核心机制具体描述**（必须可直接实现）：

禁止空洞口号，必须给出可执行的具体规则和数值设计。
"""
    return AssistantAgent(
        name="MarketResearcher",
        model_client=model_client,
        system_message=system_message,
    )

def createArchitectAgent(model_client):
    system_message = """
你是一位严谨的游戏技术架构师。

你的职责是：
1. 根据游戏方案设计清晰、可维护的项目结构
2. 确保模块解耦，便于后续迭代
3. 控制代码规模，防止失控
4. 优先选择 HTML5 Canvas + 原生 JS 实现

请按以下格式输出：

**项目结构：**
game_project/
├── index.html
├── css/style.css
├── js/
│   ├── main.js
│   ├── player.js
│   ├── enemy.js
│   ├── weapon.js
│   ├── ui.js
│   ├── game.js
│   └── utils.js
├── assets/ (描述需要的图片/音效)
└── README.md
**技术选型与实现要点：**
**潜在风险与规避方案：**
**开发优先级顺序：**

输出完成后说：**"架构设计完成，请产品经理继续"**
"""
    return AssistantAgent(
        name="ArchitectAgent",
        model_client=model_client,
        system_message=system_message,
    )



def createGameDesigner(model_client):
    """创建游戏设计师智能体"""
    system_message = """
   你是一位顶级游戏设计师。

接收到 MarketResearcher 的方案后，**必须**按以下结构输出：

1. **游戏世界与叙事**
2. **玩家系统**（属性、控制方式、成长曲线）
3. **敌人与关卡设计**
4. **战斗/核心玩法系统**（详细数值、状态机）
5. **UI/UX 设计**（屏幕布局、输入方式）
6. **音效与视觉反馈需求**
7. **任务分解**（JSON 格式）

**任务分解格式**（必须严格遵守）：
```json
{
  "tasks": [
    {
      "id": "TASK-001",
      "name": "基础画布与游戏循环",
      "files": ["index.html", "js/main.js"],
      "description": "...",
      "acceptance_criteria": [...]
    }
  ]
}
每个任务控制在 150-250 行代码，可独立测试。
输出完成后说："设计完成，请 Architect 确认结构"
"""
    return AssistantAgent(
        name="GameDesigner",
        model_client=model_client,
        system_message=system_message,
    )


def createGameProgrammar(model_client):
    """创建游戏程序员智能体"""
    system_message = """
你是一位极度严谨的独立游戏开发者。

你拥有工具：read_file、write_file、list_files

**铁律**：
1. **永远先**调用 list_files("") 查看当前项目状态
2. 修改任何文件前**必须** read_file
3. 每生成/修改一个文件**立即**调用 write_file
4. 禁止只输出代码不保存
5. 禁止 TODO、伪代码、省略实现
6. 必须输出**完整可运行**代码
7. 采用**增量开发**，不要重写整个文件（除非必要）
8. 每完成一个 TASK 后，调用 list_files 验证，并总结当前完成度

技术栈：**纯 HTML5 + Canvas + 原生 JavaScript + CSS**

输出示例：
[工具调用 write_file ...]
FILE: js/player.js
JavaScript// 完整代码
完成当前阶段后说："本阶段代码已写入，请 QA 测试"
"""
    return AssistantAgent(
        name="GameProgrammar",
        model_client=model_client,
        tools=[ read_file, write_file, list_files ],
        system_message=system_message,
    )


def createQA(model_client):
    """创建质量保证智能体"""
    system_message = """
你是专业的网页游戏 PlayTest AI。

你有权限执行以下测试：
- 检查是否能正常打开 index.html
- 浏览器控制台是否有 JS 错误
- 游戏是否能正常运行（移动/键盘控制）
- FPS 是否稳定（目标 ≥ 45）
- 核心循环是否通畅
- 是否存在明显 Bug 或卡死

**输出格式**（必须严格）：

**测试结果**：PASS / FAIL

**详细报告**：
```json
{
  "bugs": [...],
  "performance": {...},
  "suggestions": [...],
  "next_actions": [...]
}
如果发现严重问题，输出 "需要程序员修复" 并详细描述。
"""
    return AssistantAgent(
        name="QA",
        model_client=model_client,
        system_message=system_message,
    )

def create_user_proxy():
    """创建用户代理智能体"""
    return UserProxyAgent(
        name="UserProxy",
        description="""用户代理，负责以下职责：
1. 代表用户提出开发需求
2. 执行最终的代码实现
3. 验证功能是否符合预期
4. 提供用户反馈和建议

完成测试后请回复 TERMINATE。""",
    )
tools=[
    read_file,
    write_file,
    list_files
]

MarketResearcher = createMarketResearcher(model_client_ollama)
Architect = createArchitectAgent(model_client_ollama)
GameDesigner = createGameDesigner(model_client_ollama)
Programmer = createGameProgrammar(model_client_ollama)
QA = createQA(model_client_ollama)

team_chat = RoundRobinGroupChat(
    participants=[MarketResearcher, Architect, GameDesigner, Programmer, QA],
    termination_condition=TextMentionTermination("TERMINATE"),
    max_turns=30,   # 增加轮次
)


async def run_game_agent(task: str) -> str:
    """Run the game development team and return its messages as plain text."""
    messages = []
    async for event in team_chat.run_stream(task=task):
        source = getattr(event, "source", "")
        content = getattr(event, "content", "")
        if isinstance(content, list):
            content = "\n".join(
                str(item.get("text", item)) if isinstance(item, dict) else str(item)
                for item in content
            )
        if content:
            prefix = f"{source}: " if source else ""
            messages.append(f"{prefix}{content}")
    return "\n\n".join(messages)


def run_game_agent_sync(task: str) -> str:
    """Synchronous adapter for Gradio's regular Python callbacks."""
    return asyncio.run(run_game_agent(task))

async def run_software_development_team():
    # ... 初始化客户端和智能体 ...
    
    # 定义任务描述
    task = """
请严格按照以下流程开发一个**完整可玩的网页游戏**：

1. MarketResearcher → 产出爆款游戏方案
2. Architect → 设计项目结构
3. GameDesigner → 详细设计 + 任务拆解
4. Programmer → 按任务顺序实现代码（必须使用工具写入文件）
5. QA → 测试并反馈
6. 循环迭代直到 QA 给出 PASS 且游戏可玩

最终必须生成一个**可以直接用浏览器打开 index.html 游玩**的游戏。
"""
    
    # 异步执行团队协作，并流式输出对话过程
    result = await Console(team_chat.run_stream(task=task))
    await model_client_ollama.close()
    return result

# 主程序入口
if __name__ == "__main__":
    result = asyncio.run(run_software_development_team())