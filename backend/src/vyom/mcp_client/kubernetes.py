"""Reviewed tools of the upstream Kubernetes MCP server (containers/kubernetes-mcp-server).

Reviewed against v0.0.67 on Kind on 2026-10-12. The digest below is of the input schema
that release advertises; a release that advertises anything else disables the tool until
it is reviewed again.
"""

import re  # regular expressions

from pydantic import Field  # extra validation rules for one field

from vyom.evidence import ErrorKind, ItemDraft
from vyom.mcp_client.tools import Projection, ToolArguments, ToolOutput, ToolSpec

SERVER_ID = "kubernetes"  # the name this server has in operator configuration

# The columns Vyom keeps from the upstream's table. Everything else in a row (IP, node,
# labels, age) is dropped here and never reaches evidence.
_REQUIRED = ("NAMESPACE", "KIND", "NAME", "READY", "STATUS", "RESTARTS")
# re.compile prepares a regex once for reuse. ``\S+`` is a run of non-space characters, and the
# optional group lets a name with single spaces (like "READY" or "POD NAME") be one cell.
_HEADER_CELL = re.compile(r"\S+(?: \S+)*")  # cells are separated by two or more spaces


# The only argument the model may supply for this tool.
class PodsListArguments(ToolArguments):
    # Same pattern the upstream advertises for this argument.
    labelSelector: str | None = Field(  # noqa: N815 - the upstream argument name
        default=None, max_length=253, pattern=r"^([/_.\-A-Za-z0-9=, ()!])+$"
    )


def project_pod_table(output: ToolOutput) -> Projection:
    """Parse the upstream's fixed-width pod table. An empty result is an empty string."""
    # The tool replies with text laid out like a table (columns lined up by spaces). First,
    # split into lines and drop blank ones.
    lines = [line for line in output.text.splitlines() if line.strip()]
    if not lines:
        return Projection(items=())
    # Find every column title in the header line, remembering where each one starts.
    cells = list(_HEADER_CELL.finditer(lines[0]))
    # A dict comprehension: {column title: character position where it starts}.
    starts = {cell.group(): cell.start() for cell in cells}
    if any(name not in starts for name in _REQUIRED):
        raise ValueError("unexpected pod table header")
    # A column ends where the next begins; the last column runs to the end of the line (None).
    ends = [cell.start() for cell in cells[1:]] + [None]
    # zip pairs each start with its end; strict=True errors if the lists differ in length.
    bounds = {cell.group(): (cell.start(), end) for cell, end in zip(cells, ends, strict=True)}

    items = []
    for line in lines[1:]:  # lines[1:] = every line after the header
        # Cut each wanted column out of the row by position. ``slice(*pair)`` turns a
        # (start, end) pair into a slice, and strip() removes padding spaces.
        row = {name: line[slice(*bounds[name])].strip() for name in _REQUIRED}
        # Anything that is not a well-formed Pod row means the format changed: fail loudly.
        if row["KIND"] != "Pod" or not row["NAME"] or not row["NAMESPACE"]:
            raise ValueError("unexpected pod table row")
        items.append(
            ItemDraft(
                kind="Pod",
                namespace=row["NAMESPACE"],
                name=row["NAME"],
                attributes={
                    "ready": row["READY"],
                    "status": row["STATUS"],
                    # kubectl prints "4 (2m ago)" once a container has restarted.
                    "restarts": int(row["RESTARTS"].split()[0]),
                },
            )
        )
    return Projection(items=tuple(items))


# Used to tell "permission denied" apart from other tool errors. Only the type is kept.
def _error_kind(text: str) -> ErrorKind:
    return ErrorKind.FORBIDDEN if " is forbidden: " in text else ErrorKind.UPSTREAM_ERROR


# The complete definition of the one tool Vyom allows, tying all the pieces above together.
PODS_LIST_IN_NAMESPACE = ToolSpec(
    server_id=SERVER_ID,
    name="pods_list_in_namespace",
    description=(
        "List the pods in the configured namespace with readiness, status and restart "
        "count. Optionally filter with a Kubernetes label selector."
    ),
    arguments=PodsListArguments,
    input_schema_sha256="1c2a5fedc083688088f7a54fd950d43513bd83c07f738d0526984ffafbbe394d",
    project=project_pod_table,
    # The host fills the upstream ``namespace`` argument from the trusted context itself.
    scope_arguments={"namespace": "namespace"},
    max_items=200,
    error_kind=_error_kind,
)

# All tools this module offers. The trailing comma makes it a one-item tuple.
SPECS = (PODS_LIST_IN_NAMESPACE,)
