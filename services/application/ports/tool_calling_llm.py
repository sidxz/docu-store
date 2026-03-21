"""Port for LLM interactions with tool calling capabilities."""

from __future__ import annotations

from typing import Protocol

from pydantic import BaseModel, Field


class ToolDefinition(BaseModel):
    """Schema for a tool the LLM can invoke."""

    name: str
    description: str
    parameters: dict  # JSON Schema


class ToolCallRequest(BaseModel):
    """A single tool call requested by the LLM."""

    tool_name: str
    tool_args: dict = Field(default_factory=dict)
    tool_call_id: str | None = None  # Present for native tool calling


class ToolCallResult(BaseModel):
    """Result of an LLM invocation with tools.

    Either content (model is done) or tool_calls (model wants to use tools).
    """

    content: str | None = None
    tool_calls: list[ToolCallRequest] = Field(default_factory=list)


class ToolCallingLLMPort(Protocol):
    """Port for making LLM calls that support tool/function calling."""

    async def invoke_with_tools(
        self,
        messages: list[dict],
        tools: list[ToolDefinition],
        system_prompt: str | None = None,
        temperature: float | None = None,
    ) -> ToolCallResult:
        """Invoke the LLM with a set of available tools.

        Args:
            messages: Conversation messages [{"role": ..., "content": ...}]
            tools: Available tool definitions
            system_prompt: Optional system prompt
            temperature: Override temperature for this call

        Returns:
            ToolCallResult with either content or tool_calls populated.
        """
        ...

    @property
    def supports_native_tools(self) -> bool:
        """Whether this adapter uses native tool calling vs ReAct text parsing."""
        ...
