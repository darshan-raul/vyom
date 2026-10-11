import asyncio
import socket
from pathlib import Path

import pytest

import vyom
from vyom.mcp_client import client_for


def test_unreachable_endpoint_fails_instead_of_hanging():
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]

    async def connect():
        async with client_for(f"http://127.0.0.1:{port}/mcp", read_timeout_seconds=2):
            pass

    # The SDK surfaces transport failures as an exception group; S1.2 normalizes them.
    with pytest.raises(ExceptionGroup) as raised:
        asyncio.run(asyncio.wait_for(connect(), timeout=5))

    assert [type(error).__name__ for error in raised.value.exceptions] == ["ConnectError"]


def test_backend_never_imports_the_mcp_server_side():
    sources = Path(vyom.__file__).parent.rglob("*.py")

    assert [str(path) for path in sources if "mcp.server" in path.read_text()] == []
