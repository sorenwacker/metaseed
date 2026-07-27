"""Identifying the caller a tool is currently serving.

A host that serves several people over HTTP needs to know whose session a tool
call belongs to. It cannot bind that itself from middleware: the MCP server
dispatches each handler from its own task group, created when the app starts, so
a ContextVar set around the HTTP request is not visible inside the tool body.

What *is* visible is the SDK's own per-request context, set immediately before
each handler runs. This module exposes the one piece of it a host needs, so the
host does not have to import ``mcp.server.lowlevel`` internals and track their
changes.

Typical use, from a host's resolver::

    def resolve() -> MCPContext:
        request = current_request()
        if request is None:
            raise ContextUnavailableError("no MCP request in scope")
        return context_for(authenticate(request))

Note the absence of a fallback: a host that cannot identify its caller must
fail, because the only thing left to fall back to is another caller's session.
"""

from __future__ import annotations

from typing import Any


def current_request() -> Any | None:
    """The transport request behind the tool call being served, if any.

    Returns:
        The Starlette ``Request`` for an HTTP-transport call, from which a host
        reads headers to authenticate. ``None`` under stdio, where there is no
        request and only one caller anyway, and ``None`` when called outside a
        tool invocation.
    """
    try:
        from mcp.server.lowlevel.server import request_ctx
    except ImportError:  # pragma: no cover - the SDK is a hard dependency
        return None

    try:
        return getattr(request_ctx.get(), "request", None)
    except LookupError:
        # No MCP request in scope: stdio, or a call outside a tool body.
        return None
