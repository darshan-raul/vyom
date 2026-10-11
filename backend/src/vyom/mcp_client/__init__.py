"""Outbound MCP client boundary.

Vyom is an MCP host and client: it connects to upstream servers through the
official SDK and never serves the MCP protocol itself. The endpoint registry,
allowlists, argument and output validation and limits arrive in S1.2.
"""

from mcp import Client
from mcp.types import Implementation

from vyom import __version__

CLIENT_INFO = Implementation(name="vyom", version=__version__)


def client_for(url: str, *, read_timeout_seconds: float = 10.0) -> Client:
    """Build an unconnected Streamable HTTP client; enter it with ``async with`` to connect.

    ``url`` must come from operator configuration, never from a prompt or request.
    """
    return Client(
        url,
        client_info=CLIENT_INFO,
        read_timeout_seconds=read_timeout_seconds,
        cache=None,
    )
