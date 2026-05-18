"""Base LLM provider protocol and types."""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from pydantic import BaseModel


class Message(BaseModel):
    """A message in a conversation."""

    role: str  # "user", "assistant", "system"
    content: str


class Tool(BaseModel):
    """A tool definition for function calling."""

    name: str
    description: str
    parameters: dict[str, Any]


class ToolCall(BaseModel):
    """A tool call from the LLM."""

    name: str
    arguments: dict[str, Any]


class Response(BaseModel):
    """Response from an LLM."""

    content: str | None = None
    tool_calls: list[ToolCall] = []
    usage: dict[str, int] = {}  # tokens used


@runtime_checkable
class LLMProvider(Protocol):
    """Protocol for LLM providers."""

    async def complete(
        self,
        messages: list[Message],
        tools: list[Tool] | None = None,
        temperature: float = 0.0,
    ) -> Response:
        """Generate a completion.

        Args:
            messages: Conversation history.
            tools: Optional tools for function calling.
            temperature: Sampling temperature.

        Returns:
            LLM response with content and/or tool calls.
        """
        ...
