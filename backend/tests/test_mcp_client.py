# re = regular expressions; Path = file paths.
import re
from pathlib import Path

# Imported only to find where the vyom package lives on disk.
import vyom

# Matches a line that imports MCP's *server* side (``from mcp.server...``). re.MULTILINE
# makes ``^`` match at the start of every line, not just the first.
_SERVER_IMPORT = re.compile(r"^\s*(from|import)\s+mcp\.server\b", re.MULTILINE)


# Architecture rule: Vyom is an MCP client only, so no source file may import server code.
def test_backend_never_imports_the_mcp_server_side():
    # rglob("*.py") finds every .py file below the package folder, recursively.
    sources = Path(vyom.__file__).parent.rglob("*.py")

    # A list comprehension: paths of offending files. The test passes when the list is empty.
    assert [str(path) for path in sources if _SERVER_IMPORT.search(path.read_text())] == []


# Tests the test: the check must flag a real server import and ignore look-alike text.
def test_the_guard_recognizes_a_server_import():
    assert _SERVER_IMPORT.search("import os\nfrom mcp.server.mcpserver import MCPServer\n")
    assert not _SERVER_IMPORT.search('attributes = {"vyom.mcp.server": server}\n')
