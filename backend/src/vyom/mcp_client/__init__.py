"""Outbound MCP client boundary.

Vyom is an MCP host and client: it connects to upstream servers through the official SDK
and never serves the MCP protocol itself. ``registry`` holds the operator-configured
endpoints, ``tools`` the host-side tool definitions and ``host`` the connect, discover and
call lifecycle with its limits.
"""

import httpx2
from mcp import Client
from mcp.client.streamable_http import streamable_http_client
from mcp.types import Implementation

from vyom import __version__

CLIENT_INFO = Implementation(name="vyom", version=__version__)


def client_for(
    url: str,
    *,
    read_timeout_seconds: float = 10.0,
    http_client: httpx2.AsyncClient | None = None,
    max_sse_event_size: int = 1024 * 1024,
) -> Client:
    """Build an unconnected Streamable HTTP client; enter it with ``async with`` to connect.

    ``url`` must come from operator configuration, never from a prompt or request.
    ``http_client`` carries the host's credential and response limits.
    """
    return Client(
        streamable_http_client(url, http_client=http_client, max_sse_event_size=max_sse_event_size),
        client_info=CLIENT_INFO,
        read_timeout_seconds=read_timeout_seconds,
        cache=None,
    )
