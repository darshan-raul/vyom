"""Reviewed tools of the upstream Kubernetes MCP server (containers/kubernetes-mcp-server).

Reviewed against v0.0.67 on Kind on 2026-10-12. The digest below is of the input schema
that release advertises; a release that advertises anything else disables the tool until
it is reviewed again.
"""

import re

from pydantic import Field

from vyom.evidence import ErrorKind, ItemDraft
from vyom.mcp_client.tools import Projection, ToolArguments, ToolOutput, ToolSpec

SERVER_ID = "kubernetes"

# The columns Vyom keeps from the upstream's table. Everything else in a row (IP, node,
# labels, age) is dropped here and never reaches evidence.
_REQUIRED = ("NAMESPACE", "KIND", "NAME", "READY", "STATUS", "RESTARTS")
_HEADER_CELL = re.compile(r"\S+(?: \S+)*")  # cells are separated by two or more spaces


class PodsListArguments(ToolArguments):
    # Same pattern the upstream advertises for this argument.
    labelSelector: str | None = Field(  # noqa: N815 - the upstream argument name
        default=None, max_length=253, pattern=r"^([/_.\-A-Za-z0-9=, ()!])+$"
    )


def project_pod_table(output: ToolOutput) -> Projection:
    """Parse the upstream's fixed-width pod table. An empty result is an empty string."""
    lines = [line for line in output.text.splitlines() if line.strip()]
    if not lines:
        return Projection(items=())
    cells = list(_HEADER_CELL.finditer(lines[0]))
    starts = {cell.group(): cell.start() for cell in cells}
    if any(name not in starts for name in _REQUIRED):
        raise ValueError("unexpected pod table header")
    ends = [cell.start() for cell in cells[1:]] + [None]
    bounds = {cell.group(): (cell.start(), end) for cell, end in zip(cells, ends, strict=True)}

    items = []
    for line in lines[1:]:
        row = {name: line[slice(*bounds[name])].strip() for name in _REQUIRED}
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


def _error_kind(text: str) -> ErrorKind:
    return ErrorKind.FORBIDDEN if " is forbidden: " in text else ErrorKind.UPSTREAM_ERROR


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
    scope_arguments={"namespace": "namespace"},
    max_items=200,
    error_kind=_error_kind,
)

SPECS = (PODS_LIST_IN_NAMESPACE,)
