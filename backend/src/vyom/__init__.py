"""Vyom backend: API, agent, MCP client and direct-SDK collectors in one workload."""

# importlib.metadata reads facts about installed packages (name, version, ...).
from importlib.metadata import version

# Take the version from the installed package (set in pyproject.toml) so it is written once.
__version__ = version("vyom")
