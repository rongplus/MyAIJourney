"""RoundAgent — 基于 LangChain 1.x + ChatOllama 的多轮流式对话 Agent

封装为 RoundAgent 类，管理：
- LLM 实例（ChatOllama）
- LangChain create_agent（带工具调用能力）
- MemorySaver checkpointer（会话历史管理）
- JSON 文件持久化（自动保存/加载）
- 流式逐 chunk 输出
- 工具调用 — 自动调用 weather_tool 等工具完成回答

用法:
    # 基本用法（默认绑定 weather_tool）
    agent = RoundAgent()
    for chunk in agent.round_stream("北京今天天气怎么样？"):
        print(chunk, end="", flush=True)

    # 自定义模型和参数
    agent = RoundAgent(model="qwen2.5:7b", temperature=0.7)
    for chunk in agent.round_stream("写首诗", system_prompt="你是诗人"):
        print(chunk, end="", flush=True)

注意:
    工具调用需要使用支持 tools 的模型（如 qwen2.5:7b、llama3.2:3b 等）。
    llama3 不支持 tools，如需工具调用请换用支持 tools 的模型。
"""


import os
from typing import Dict, Generator, Optional, List, Any

from langchain_ollama import ChatOllama
from langchain_core.chat_history import InMemoryChatMessageHistory
from langchain_core.messages import HumanMessage, AIMessage
from langchain_core.tools import BaseTool
from langchain.agents import create_agent
from langgraph.checkpoint.memory import MemorySaver

from weather_tool import TOOLS as WEATHER_TOOLS

from myfunctions import _load_history_file, _save_history_file, _json_to_messages,_messages_to_json
from mylog import log




# ==================================================
# 默认配置
# ==================================================
DEFAULT_HISTORY_FILE = "chat_history.json"
DEFAULT_SESSION_ID = "user-1"
# 默认模型用支持 tools 的模型（llama3 不支持 tools）
DEFAULT_MODEL = "qwen2.5:7b"
DEFAULT_TEMPERATURE = 0.3
DEFAULT_SYSTEM_PROMPT = (
    "You are a helpful assistant. Use the conversation history. "
    "When the user asks about weather, use the get_weather tool to fetch real-time data."
)


class RoundAgent:
    """多轮流式对话 Agent（支持工具调用）。

    使用 LangChain 1.x 的 create_agent API 构建 agent graph，
    内置 MemorySaver checkpointer 管理会话历史，支持 JSON 持久化。

    Attributes:
        model:          默认模型名（需支持 tools）
        temperature:    默认温度
        system_prompt:  默认系统提示词
        session_id:     默认会话 ID
        history_file:   持久化历史 JSON 文件路径
        tools:          绑定的工具列表
    """

    def __init__(
        self,
        model: str = DEFAULT_MODEL,
        temperature: float = DEFAULT_TEMPERATURE,
        system_prompt: str = DEFAULT_SYSTEM_PROMPT,
        session_id: str = DEFAULT_SESSION_ID,
        history_file: str = DEFAULT_HISTORY_FILE,
        tools: Optional[List[BaseTool]] = None,
    ):
        self.model = model
        self.temperature = temperature
        self.system_prompt = system_prompt
        self.session_id = session_id
        self.history_file = history_file

        # ---- 工具列表（默认绑定 weather_tool） ----
        self.tools: List[BaseTool] = list(tools) if tools is not None else list(WEATHER_TOOLS)

        # ---- 持久化历史数据（从文件加载） ----
        self._history_data: Dict[str, list] = _load_history_file(self.history_file)

        # ---- checkpointer（LangGraph 内存检查点，管理会话历史） ----
        self._checkpointer = MemorySaver()

        # ---- 跟踪哪些 session 已经从 JSON 恢复到 checkpointer ----
        self._restored_sessions: set = set()

        # ---- 构建 LLM ----
        self._llm = ChatOllama(
            model=self.model,
            temperature=self.temperature,
            streaming=True,
        )

        # ---- 构建 Agent ----
        self._agent = self._build_agent(self._llm, self.system_prompt, self.tools)

    # ==================================================
    # 内部方法
    # ==================================================

    def _build_agent(
        self,
        llm: ChatOllama,
        system_prompt: str,
        tools: List[BaseTool],
    ):
        """使用 langchain 1.x create_agent 构建 agent graph。

        create_agent 返回 CompiledStateGraph（LangGraph），
        内置工具调用循环：LLM 判断是否需要调工具 → 自动执行 → 结果喂回 → 最终回复。
        """
        return create_agent(
            llm,
            tools=tools,
            system_prompt=system_prompt,
            checkpointer=self._checkpointer,
        )

    def _restore_history_if_needed(self, session_id: str, agent, system_prompt: str):
        """如果 session 的历史还没从 JSON 恢复到 checkpointer，恢复它。

        通过把旧历史消息 + 一条占位消息传入 agent.invoke，
       让 checkpointer 记录这些消息，这样后续 round_stream 调用就能带着历史上下文。
        """
        if session_id in self._restored_sessions:
            return

        messages_json = self._history_data.get(session_id, [])
        if not messages_json:
            self._restored_sessions.add(session_id)
            return

        # 把历史消息作为 input 传给 agent，让 checkpointer 自动保存
        try:
            input_msgs = []
            for item in messages_json:
                input_msgs.append({"role": item["role"], "content": item["content"]})
            # 加一条占位消息触发 agent 执行（checkpointer 会保存所有消息）
            input_msgs.append({"role": "user", "content": "(continue)"})
            agent.invoke(
                {"messages": input_msgs},
                config={"configurable": {"thread_id": session_id}},
            )
        except Exception:
            pass

        self._restored_sessions.add(session_id)

    def _persist_history(self, session_id: str):
        """从 checkpointer 提取历史并写入 JSON 文件"""
        tid = session_id
        log("Save History:" + tid)
        try:
            state = self._agent.get_state(config={"configurable": {"thread_id": tid}})
            if state and hasattr(state, "values") and "messages" in state.values:
                messages = state.values["messages"]
                # 只存 HumanMessage 和 AIMessage（跳过 ToolMessage 等）
                self._history_data[tid] = _messages_to_json(messages)
                _save_history_file(self.history_file, self._history_data)
        except Exception:
            # 持久化失败不影响对话
            pass

    # ==================================================
    # 对外接口
    # ==================================================

    def round_stream(
        self,
        user_input: str,
        system_prompt: str = "",
        model: str = "",
        temperature: Optional[float] = None,
        top_p: Optional[float] = None,
        session_id: Optional[str] = None,
    ) -> Generator[str, None, str]:
        """流式多轮对话，逐 chunk yield 文本片段。

        如果绑定了工具且 LLM 判断需要调用工具（如查天气），
        agent 会自动执行工具并把结果喂回 LLM，最终流式产出回复。

        stream_mode='updates' 的 chunk 格式：
            {node_name: {"messages": [AIMessage | ToolMessage]}}
        - node="model":  LLM 返回 AIMessage（可能含 tool_calls，content 为空）
        - node="tools":  工具执行返回 ToolMessage（含结果）
        - node="model":  LLM 拿到结果后返回最终 AIMessage（content 有文本）

        我们只 yield 最终 AIMessage 的 content 文本。

        Args:
            user_input:    用户本轮输入
            system_prompt:  自定义系统提示词（为空则用实例默认值）
            model:          模型名（为空则用实例默认值）
            temperature:    温度（None 则用实例默认值）
            top_p:          top_p（None 则不显式设置）
            session_id:     会话 ID（None 则用实例默认值）

        Yields:
            str: 每个流式 chunk 的文本片段
        """
        if not user_input or not user_input.strip():
            return ""
        if user_input.strip().lower() in ("exit", "quit"):
            return ""

        log("Convesation:" + user_input)

        sid = session_id or self.session_id
        config = {"configurable": {"thread_id": sid}}

        # ---- 决定用哪个 agent（是否需要动态重建） ----
        effective_model = model or self.model
        effective_temp = temperature if temperature is not None else self.temperature
        effective_prompt = system_prompt if system_prompt and system_prompt.strip() else self.system_prompt

        need_rebuild = (
            effective_model != self.model
            or effective_temp != self.temperature
            or top_p is not None
            or effective_prompt != self.system_prompt
        )

        if need_rebuild:
            runtime_llm = ChatOllama(
                model=effective_model,
                temperature=effective_temp,
                top_p=top_p if top_p is not None else None,
                streaming=True,
            )
            runtime_agent = self._build_agent(runtime_llm, effective_prompt, self.tools)
        else:
            runtime_agent = self._agent

        # ---- 恢复历史到 checkpointer（首次使用该 session 时） ----
        self._restore_history_if_needed(sid, runtime_agent, effective_prompt)

        # ---- 流式产出 ----
        full_response = ""
        for chunk in runtime_agent.stream(
            {"messages": [{"role": "user", "content": user_input}]},
            config=config,
            stream_mode="updates",
        ):
            # chunk 格式: {node_name: {"messages": [msg, ...]}}
            if not isinstance(chunk, dict):
                # 某些情况 chunk 可能直接是 message
                if hasattr(chunk, "content") and chunk.content:
                    full_response += chunk.content
                    yield chunk.content
                continue

            for node_name, node_output in chunk.items():
                if not isinstance(node_output, dict) or "messages" not in node_output:
                    continue

                for msg in node_output["messages"]:
                    # 只处理 AIMessage 的文本内容
                    # 跳过 ToolMessage（工具结果，不需要直接 yield 给用户）
                    # 跳过带 tool_calls 但 content 为空的 AIMessage（那是工具调用请求）
                    if not isinstance(msg, AIMessage):
                        continue

                    content = getattr(msg, "content", "")
                    # 如果这条消息有 tool_calls 且 content 为空，跳过
                    tool_calls = getattr(msg, "tool_calls", None)
                    if tool_calls and not content:
                        continue

                    if content:
                        full_response += content
                        yield content

        # ---- 持久化历史 ----
        self._persist_history(sid)

        return full_response

    def clear_history(self, session_id: Optional[str] = None):
        """清空指定 session 的内存历史和持久化历史。

        Args:
            session_id: 会话 ID（None 则清空默认 session）
        """
        sid = session_id or self.session_id
        # 重置恢复标记（下次使用时会重新从 JSON 恢复——但 JSON 也清了，所以等于全新会话）
        self._restored_sessions.discard(sid)
        # checkpointer 的 thread 历史会随新会话自然覆盖，这里不手动操作底层 API
        # 清空持久化
        if sid in self._history_data:
            del self._history_data[sid]
            _save_history_file(self.history_file, self._history_data)

    def get_history(self, session_id: Optional[str] = None) -> list[dict]:
        """获取指定 session 的对话历史（JSON 格式）"""
        sid = session_id or self.session_id
        # 优先从 checkpointer 获取最新状态
        try:
            state = self._agent.get_state(config={"configurable": {"thread_id": sid}})
            if state and hasattr(state, "values") and "messages" in state.values:
                return _messages_to_json(state.values["messages"])
        except Exception:
            pass
        # fallback 到持久化文件
        return self._history_data.get(sid, [])

    def add_tool(self, tool: BaseTool):
        """运行时添加工具并重建 Agent"""
        if tool not in self.tools:
            self.tools.append(tool)
        self._agent = self._build_agent(self._llm, self.system_prompt, self.tools)


# ==================================================
# 模块级便捷实例（向后兼容）
# ==================================================
_default_agent = RoundAgent()

roundStream = _default_agent.round_stream
clear_session_history = _default_agent.clear_history
DEFAULT_SESSION_ID = DEFAULT_SESSION_ID  # re-export


# ==================================================
# CLI 测试入口
# ==================================================
if __name__ == "__main__":
    print("💬 RoundAgent CLI with Tools (type 'exit' to quit)")
    print(f"   模型: {DEFAULT_MODEL}")
    print(f"   工具: {[t.name for t in WEATHER_TOOLS]}")
    print()
    agent = RoundAgent()
    while True:
        user_input = input("You: ").strip()
        if user_input.lower() in ("exit", "quit"):
            break
        print("Assistant: ", end="", flush=True)
        for chunk in agent.round_stream(user_input):
            print(chunk, end="", flush=True)
        print("\n")
