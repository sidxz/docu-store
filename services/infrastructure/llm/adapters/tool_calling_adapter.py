"""Dual-mode tool-calling adapter: native (OpenAI) + ReAct text-parsing (Ollama).

Wraps the same LangChain ChatOllama/ChatOpenAI instances used elsewhere.
"""

from __future__ import annotations

import json
import re
from typing import TYPE_CHECKING, Any

import structlog

from application.ports.tool_calling_llm import (
    ToolCallRequest,
    ToolCallResult,
    ToolDefinition,
)

if TYPE_CHECKING:
    pass

log = structlog.get_logger(__name__)

# ── ReAct parsing ──
_ACTION_RE = re.compile(
    r"Action:\s*(?P<tool>\S+)\s*\n"
    r"Action Input:\s*(?P<input>.+?)(?:\n|$)",
    re.DOTALL,
)


def _build_react_tool_descriptions(tools: list[ToolDefinition]) -> str:
    """Format tool definitions for injection into the ReAct system prompt."""
    parts: list[str] = []
    for t in tools:
        params = t.parameters.get("properties", {})
        param_lines = []
        for pname, pschema in params.items():
            desc = pschema.get("description", "")
            ptype = pschema.get("type", "string")
            param_lines.append(f"    - {pname} ({ptype}): {desc}")
        param_block = "\n".join(param_lines) if param_lines else "    (no parameters)"
        parts.append(f"- {t.name}: {t.description}\n  Parameters:\n{param_block}")
    return "\n\n".join(parts)


REACT_SUFFIX = """
You have access to the following tools:

{tool_descriptions}

To use a tool, respond with EXACTLY this format (no markdown fences):
Thought: <your reasoning>
Action: <tool_name>
Action Input: {{"param": "value"}}

When you have gathered enough information, respond with:
Thought: I have enough information.
Action: finish_retrieval
Action Input: {{}}

IMPORTANT: You must use the exact tool names listed above. Output ONLY ONE action per response.
"""


def _parse_react_response(text: str) -> ToolCallResult:
    """Parse a ReAct-formatted response into a ToolCallResult."""
    match = _ACTION_RE.search(text)
    if not match:
        # No action found — treat as the model being done (safe fallback)
        return ToolCallResult(content=text)

    tool_name = match.group("tool").strip()
    raw_input = match.group("input").strip()

    # Try to parse as JSON
    try:
        tool_args = json.loads(raw_input)
    except (json.JSONDecodeError, ValueError):
        # Wrap bare string as {"query": value}
        tool_args = {"query": raw_input.strip('"').strip("'")}

    return ToolCallResult(
        tool_calls=[
            ToolCallRequest(tool_name=tool_name, tool_args=tool_args),
        ],
    )


class NativeToolCallingAdapter:
    """Uses LangChain's native bind_tools() for providers that support it (OpenAI)."""

    def __init__(
        self,
        provider: str,
        model_name: str,
        api_key: str | None = None,
        base_url: str = "http://localhost:11434",
        temperature: float = 0.3,
        langfuse_handler: Any | None = None,  # noqa: ANN401
    ) -> None:
        self._provider = provider
        self._model_name = model_name
        self._api_key = api_key
        self._base_url = base_url
        self._temperature = temperature
        self._langfuse_handler = langfuse_handler
        self._llm: Any | None = None

    def _get_llm(self) -> Any:  # noqa: ANN401
        if self._llm is None:
            if self._provider == "openai":
                from langchain_openai import ChatOpenAI  # noqa: PLC0415

                self._llm = ChatOpenAI(
                    model=self._model_name,
                    api_key=self._api_key,
                    temperature=self._temperature,
                )
            else:
                from langchain_ollama import ChatOllama  # noqa: PLC0415

                self._llm = ChatOllama(
                    model=self._model_name,
                    base_url=self._base_url,
                    temperature=self._temperature,
                )
        return self._llm

    @property
    def supports_native_tools(self) -> bool:
        return True

    async def invoke_with_tools(
        self,
        messages: list[dict],
        tools: list[ToolDefinition],
        system_prompt: str | None = None,
        temperature: float | None = None,
    ) -> ToolCallResult:
        from langchain_core.messages import (  # noqa: PLC0415
            AIMessage,
            HumanMessage,
            SystemMessage,
            ToolMessage,
        )
        from langchain_core.tools import StructuredTool  # noqa: PLC0415

        llm = self._get_llm()
        if temperature is not None:
            llm = llm.bind(temperature=temperature)

        # Convert ToolDefinitions to LangChain tool schemas
        lc_tools = []
        for td in tools:
            lc_tools.append({
                "type": "function",
                "function": {
                    "name": td.name,
                    "description": td.description,
                    "parameters": td.parameters,
                },
            })

        llm_with_tools = llm.bind_tools(lc_tools)

        # Build LangChain messages
        lc_messages = []
        if system_prompt:
            lc_messages.append(SystemMessage(content=system_prompt))

        for msg in messages:
            role = msg["role"]
            if role == "system":
                lc_messages.append(SystemMessage(content=msg["content"]))
            elif role == "user":
                lc_messages.append(HumanMessage(content=msg["content"]))
            elif role == "assistant":
                if msg.get("tool_calls"):
                    lc_messages.append(AIMessage(
                        content=msg.get("content", ""),
                        tool_calls=msg["tool_calls"],
                    ))
                else:
                    lc_messages.append(AIMessage(content=msg["content"]))
            elif role == "tool":
                lc_messages.append(ToolMessage(
                    content=msg["content"],
                    tool_call_id=msg.get("tool_call_id", ""),
                ))

        config = {"callbacks": [self._langfuse_handler]} if self._langfuse_handler else {}
        response: AIMessage = await llm_with_tools.ainvoke(lc_messages, config=config)

        # Parse response
        if response.tool_calls:
            calls = [
                ToolCallRequest(
                    tool_name=tc["name"],
                    tool_args=tc["args"],
                    tool_call_id=tc.get("id"),
                )
                for tc in response.tool_calls
            ]
            return ToolCallResult(
                content=str(response.content) if response.content else None,
                tool_calls=calls,
            )

        return ToolCallResult(content=str(response.content))


class ReactToolCallingAdapter:
    """Text-based ReAct parsing for models without native tool calling (Ollama/gemma3)."""

    def __init__(
        self,
        provider: str,
        model_name: str,
        api_key: str | None = None,
        base_url: str = "http://localhost:11434",
        temperature: float = 0.3,
        langfuse_handler: Any | None = None,  # noqa: ANN401
    ) -> None:
        self._provider = provider
        self._model_name = model_name
        self._api_key = api_key
        self._base_url = base_url
        self._temperature = temperature
        self._langfuse_handler = langfuse_handler
        self._llm: Any | None = None

    def _get_llm(self) -> Any:  # noqa: ANN401
        if self._llm is None:
            if self._provider == "openai":
                from langchain_openai import ChatOpenAI  # noqa: PLC0415

                self._llm = ChatOpenAI(
                    model=self._model_name,
                    api_key=self._api_key,
                    temperature=self._temperature,
                )
            else:
                from langchain_ollama import ChatOllama  # noqa: PLC0415

                self._llm = ChatOllama(
                    model=self._model_name,
                    base_url=self._base_url,
                    temperature=self._temperature,
                )
        return self._llm

    @property
    def supports_native_tools(self) -> bool:
        return False

    async def invoke_with_tools(
        self,
        messages: list[dict],
        tools: list[ToolDefinition],
        system_prompt: str | None = None,
        temperature: float | None = None,
    ) -> ToolCallResult:
        from langchain_core.messages import (  # noqa: PLC0415
            AIMessage,
            HumanMessage,
            SystemMessage,
        )

        llm = self._get_llm()
        if temperature is not None:
            llm = llm.bind(temperature=temperature)

        # Inject tool descriptions into system prompt
        tool_desc = _build_react_tool_descriptions(tools)
        react_instruction = REACT_SUFFIX.format(tool_descriptions=tool_desc)

        effective_system = (system_prompt or "") + "\n" + react_instruction

        lc_messages: list = [SystemMessage(content=effective_system)]

        for msg in messages:
            role = msg["role"]
            if role == "system":
                # Already included via effective_system
                continue
            if role == "user":
                lc_messages.append(HumanMessage(content=msg["content"]))
            elif role == "assistant":
                lc_messages.append(AIMessage(content=msg["content"]))
            elif role == "tool":
                # For ReAct, tool results are injected as user messages
                lc_messages.append(HumanMessage(
                    content=f"Observation: {msg['content']}",
                ))

        config = {"callbacks": [self._langfuse_handler]} if self._langfuse_handler else {}
        response = await llm.ainvoke(lc_messages, config=config)
        raw_text = str(response.content)

        log.debug("react.raw_response", text=raw_text[:500])
        return _parse_react_response(raw_text)
