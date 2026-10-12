"""Projection of the upstream pod table. The sample is the shape v0.0.67 returned on Kind
on 2026-10-12, with one row edited to show a restart suffix. Offline only."""

from pathlib import Path

import pytest

from vyom.evidence import ErrorKind
from vyom.mcp_client.kubernetes import PODS_LIST_IN_NAMESPACE, project_pod_table
from vyom.mcp_client.tools import ToolOutput

TABLE = (Path(__file__).parent / "data" / "pods_table_v0.0.67.txt").read_text()


def test_table_rows_become_minimal_pod_items():
    projection = project_pod_table(ToolOutput(text=TABLE))

    assert [(item.namespace, item.name, item.attributes) for item in projection.items] == [
        (
            "demo",
            "broken-57f448799-h669z",
            {"ready": "0/1", "status": "ImagePullBackOff", "restarts": 0},
        ),
        ("demo", "web-769fb547f5-kxxc6", {"ready": "1/1", "status": "Running", "restarts": 4}),
    ]
    # Node, IP and labels are in the table and are not kept.
    assert "10.244" not in str(projection) and "vyom-control-plane" not in str(projection)
    assert all(item.uid is None and item.observed_at is None for item in projection.items)


def test_an_empty_result_is_no_items_not_an_error():
    assert project_pod_table(ToolOutput(text="")).items == ()


@pytest.mark.parametrize(
    "text",
    [
        "apiVersion: v1\nitems:\n- kind: Pod\n",  # the upstream's yaml list format
        "NAMESPACE   NAME   STATUS\ndemo   web   Running\n",  # a column Vyom needs is gone
        TABLE.replace("Pod    web", "Secret web"),
    ],
)
def test_any_other_shape_is_rejected(text):
    with pytest.raises(ValueError):
        project_pod_table(ToolOutput(text=text))


def test_a_kubernetes_denial_is_told_apart_from_other_tool_errors():
    denied = 'failed to list pods in namespace x: pods is forbidden: User "sa" cannot list'

    assert PODS_LIST_IN_NAMESPACE.error_kind(denied) is ErrorKind.FORBIDDEN
    assert PODS_LIST_IN_NAMESPACE.error_kind("connection refused") is ErrorKind.UPSTREAM_ERROR
