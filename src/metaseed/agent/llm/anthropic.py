"""Anthropic Claude LLM provider."""

from __future__ import annotations

import os
from typing import Any

from metaseed.agent.llm.base import LLMProvider, Message, Response, Tool, ToolCall


class AnthropicProvider:
    """Claude API provider."""

    def __init__(
        self,
        model: str = "claude-opus-4-8",
        api_key: str | None = None,
    ):
        """Initialize Anthropic provider.

        Args:
            model: Model to use.
            api_key: API key. Defaults to ANTHROPIC_API_KEY env var.
        """
        self.model = model
        self.api_key = api_key or os.environ.get("ANTHROPIC_API_KEY")
        self._client: Any = None

    def _get_client(self) -> Any:
        """Lazy-load the Anthropic client."""
        if self._client is None:
            try:
                import anthropic
            except ImportError as e:
                raise ImportError(
                    "anthropic package required. Install with: pip install anthropic"
                ) from e
            self._client = anthropic.Anthropic(api_key=self.api_key)
        return self._client

    async def complete(
        self,
        messages: list[Message],
        tools: list[Tool] | None = None,
        temperature: float = 0.0,
    ) -> Response:
        """Generate a completion using Claude.

        Args:
            messages: Conversation history.
            tools: Optional tools for function calling.
            temperature: Sampling temperature.

        Returns:
            LLM response.
        """
        client = self._get_client()

        # Convert messages to Anthropic format
        system_message = None
        anthropic_messages = []
        for msg in messages:
            if msg.role == "system":
                system_message = msg.content
            else:
                anthropic_messages.append({"role": msg.role, "content": msg.content})

        # Build request kwargs
        kwargs: dict[str, Any] = {
            "model": self.model,
            "max_tokens": 4096,
            "temperature": temperature,
            "messages": anthropic_messages,
        }
        if system_message:
            kwargs["system"] = system_message

        # Add tools if provided
        if tools:
            kwargs["tools"] = [
                {
                    "name": tool.name,
                    "description": tool.description,
                    "input_schema": tool.parameters,
                }
                for tool in tools
            ]

        # Make request (sync for now, can wrap in asyncio.to_thread)
        import asyncio

        response = await asyncio.to_thread(client.messages.create, **kwargs)

        # Parse response
        content = None
        tool_calls = []

        for block in response.content:
            if block.type == "text":
                content = block.text
            elif block.type == "tool_use":
                tool_calls.append(
                    ToolCall(
                        name=block.name,
                        arguments=block.input,
                    )
                )

        return Response(
            content=content,
            tool_calls=tool_calls,
            usage={
                "input_tokens": response.usage.input_tokens,
                "output_tokens": response.usage.output_tokens,
            },
        )


# Type assertion
_: type[LLMProvider] = AnthropicProvider
