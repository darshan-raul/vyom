"""R3.1 Deployment, ReplicaSet and Pod projections against scripted Table responses.
Fixture evidence only; the R3.6 gate compares the stored inventory with kubectl on Kind."""

import asyncio

import httpx
import pytest

from vyom.collectors.kubernetes import (
    DEPLOYMENT,
    POD,
    REPLICA_SET,
    SWEEP,
    KubernetesApiConfig,
    TableCollector,
)
from vyom.context import TrustedContext
from vyom.evidence import ErrorKind, OwnerRef, State

CONTEXT = TrustedContext(
    workspace_id="ws-local", connection_id="kind-vyom", cluster_uid="c1uster-uid", namespace="demo"
)
SECRET = "literal-env-value-do-not-keep"
# Printer columns as the API server returns them, including the wide ones Vyom never reads.
DEPLOYMENT_COLUMNS = ["Name", "Ready", "Up-to-date", "Available", "Age", "Containers", "Images"]
REPLICA_SET_COLUMNS = ["Name", "Desired", "Current", "Ready", "Age", "Containers", "Images"]


def metadata(name, uid, *, owner=None, revision=None, extra_owner=None):
    annotations = {
        # What `kubectl apply` leaves behind, spec and env values included.
        "kubectl.kubernetes.io/last-applied-configuration": f'{{"env":"{SECRET}"}}',
    }
    if revision is not None:
        annotations["deployment.kubernetes.io/revision"] = str(revision)
    refs = []
    if extra_owner:
        refs.append({"kind": extra_owner[0], "name": extra_owner[1], "uid": extra_owner[2]})
    if owner:
        refs.append({"kind": owner[0], "name": owner[1], "uid": owner[2], "controller": True})
    return {
        "name": name,
        "namespace": "demo",
        "uid": uid,
        "labels": {"app": name, "token": SECRET},
        "annotations": annotations,
        "ownerReferences": refs,
    }


def table(columns, *rows):
    return {
        "kind": "Table",
        "metadata": {},
        "columnDefinitions": [{"name": name} for name in columns],
        "rows": [{"cells": cells, "object": {"metadata": meta}} for cells, meta in rows],
    }


@pytest.fixture
def config(monkeypatch) -> KubernetesApiConfig:
    monkeypatch.setenv("VYOM_TEST_COLLECTOR_TOKEN", "collector-token-0123")
    return KubernetesApiConfig(
        connection_id="kind-vyom",
        url="https://kubernetes.test",
        credential_ref="env:VYOM_TEST_COLLECTOR_TOKEN",
    )


def collect(config, projection, answer):
    sent: list[httpx.Request] = []

    def handler(request):
        sent.append(request)
        return httpx.Response(200, json=answer)

    collector = TableCollector(config, projection, transport=httpx.MockTransport(handler))
    return asyncio.run(collector.collect(CONTEXT)), sent


def test_sweep_collects_owners_before_what_they_own():
    assert [p.kind for p in SWEEP] == ["Deployment", "ReplicaSet", "Pod"]
    assert len({p.collector for p in SWEEP}) == 3


def test_deployments_are_projected_from_named_columns_and_the_revision_only(config):
    answer = table(
        DEPLOYMENT_COLUMNS,
        (["web", "2/3", 3, 2, "1h", "web", "nginx:1.27"], metadata("web", "d1", revision=4)),
    )
    evidence, (request,) = collect(config, DEPLOYMENT, answer)

    assert request.url.path == "/apis/apps/v1/namespaces/demo/deployments"
    assert request.url.params["includeObject"] == "Metadata"
    assert request.headers["accept"].startswith("application/json;as=Table")
    assert evidence.state is State.COMPLETE
    assert evidence.source.collector == "kubernetes-deployments"
    (deployment,) = evidence.items
    assert (deployment.id, deployment.uid, deployment.owner) == (
        "k8s:c1uster-uid:demo:deployment:web",
        "d1",
        None,
    )
    assert deployment.attributes == {"ready": "2/3", "up_to_date": 3, "available": 2, "revision": 4}
    # Labels, other annotations and the wide columns are dropped unread.
    serialized = evidence.model_dump_json()
    assert SECRET not in serialized and "nginx" not in serialized


def test_replicasets_carry_their_controller_and_ignore_other_owners(config):
    answer = table(
        REPLICA_SET_COLUMNS,
        (
            ["web-aaa", 3, 3, 2, "1h", "web", "nginx:1.27"],
            metadata(
                "web-aaa",
                "r1",
                owner=("Deployment", "web", "d1"),
                extra_owner=("ConfigMap", "not-a-controller", "c9"),
                revision=4,
            ),
        ),
        (["orphan", 1, 1, 1, "2h", "x", "y"], metadata("orphan", "r2")),
    )
    evidence, _ = collect(config, REPLICA_SET, answer)

    owned, orphan = evidence.items
    assert owned.owner == OwnerRef(kind="Deployment", name="web", uid="d1")
    assert owned.attributes == {"desired": 3, "current": 3, "ready": 2, "revision": 4}
    assert orphan.owner is None and orphan.attributes["revision"] is None
    assert SECRET not in evidence.model_dump_json()


def test_pods_carry_their_controller_beside_unchanged_attributes(config):
    answer = table(
        ["Name", "Ready", "Status", "Restarts", "Age"],
        (
            ["web-aaa-1", "1/1", "Running", "2 (5m ago)", "1h"],
            metadata("web-aaa-1", "p1", owner=("ReplicaSet", "web-aaa", "r1")),
        ),
    )
    evidence, _ = collect(config, POD, answer)

    (pod,) = evidence.items
    assert pod.owner == OwnerRef(kind="ReplicaSet", name="web-aaa", uid="r1")
    # Owner stays out of attributes, which the MCP path must match.
    assert pod.attributes == {"ready": "1/1", "status": "Running", "restarts": 2}


def test_a_malformed_owner_reference_discards_the_page(config):
    meta = metadata("web-aaa", "r1")
    meta["ownerReferences"] = [{"kind": "Deployment", "controller": True}]  # no name or uid
    evidence, _ = collect(
        config,
        REPLICA_SET,
        table(REPLICA_SET_COLUMNS, (["web-aaa", 3, 3, 2, "1h", "w", "i"], meta)),
    )

    assert evidence.state is State.MISSING and not evidence.items
    assert [error.kind for error in evidence.errors] == [ErrorKind.INVALID_OUTPUT]
