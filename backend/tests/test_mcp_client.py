import re
from pathlib import Path

import vyom

_SERVER_IMPORT = re.compile(r"^\s*(from|import)\s+mcp\.server\b", re.MULTILINE)


def test_backend_never_imports_the_mcp_server_side():
    sources = Path(vyom.__file__).parent.rglob("*.py")

    assert [str(path) for path in sources if _SERVER_IMPORT.search(path.read_text())] == []


def test_the_guard_recognizes_a_server_import():
    assert _SERVER_IMPORT.search("import os\nfrom mcp.server.mcpserver import MCPServer\n")
    assert not _SERVER_IMPORT.search('attributes = {"vyom.mcp.server": server}\n')
