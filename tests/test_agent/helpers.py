"""Test helpers for MCP tests."""

from collections.abc import Callable
from typing import Any


def get_tool(server: Any, name: str) -> Callable | None:
    """Get a tool function by name from an MCP server.

    Args:
        server: MCP server instance.
        name: Tool name to find.

    Returns:
        The tool function if found, None otherwise.
    """
    tools = server._tool_manager._tools
    tool = tools.get(name)
    return tool.fn if tool else None


def get_prompt(server: Any, name: str) -> Any | None:
    """Get a prompt by name from an MCP server.

    Args:
        server: MCP server instance.
        name: Prompt name to find.

    Returns:
        The prompt object if found, None otherwise.
    """
    prompts = server._prompt_manager._prompts
    return prompts.get(name)
