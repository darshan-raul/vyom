"""R2.2 acceptance: API and collector persistence, citation resolution and outage handling.

Verifies:
- Each direct pod collection is persisted through InventoryStore into Postgres.
- API citations resolve from stored runs, including old name-based item IDs.
- Persisted citations resolve after an API restart (a completely fresh app instance).
- Chat citations resolve from stored runs.
- Cross-workspace citation lookups return 404 (absent and other-workspace indistinguishable).
- Postgres outage behavior is explicit (persisted=False, 503 on citations) without breaking view.
- Unconfigured database behavior (persisted=None, 503 on citations).
"""

import asyncio
import uuid
from typing import Any

import httpx
import psycopg
import pytest
from mcp_fixture import Upstream
from mcp_fixture import config as mcp_config
from mcp_fixture import run as mcp_run
from pydantic import ValidationError

from vyom.agent.model import ModelClient, ModelConfig
from vyom.api.app import create_app
from vyom.collectors.kubernetes import KubernetesApiConfig, PodCollector
from vyom.context import TrustedContext
from vyom.inventory import DatabaseConfig
from vyom.inventory.migrate import migrate
from vyom.mcp_client.registry import OperatorConfig

JOB_ID = "k8s:c1uster-uid:demo:pod:job-7"

CONTEXT_A = TrustedContext(
    workspace_id="ws-a", connection_id="kind-vyom", cluster_uid="c-1", namespace="demo"
)
CONTEXT_B = TrustedContext(
    workspace_id="ws-b", connection_id="kind-vyom", cluster_uid="c-1", namespace="demo"
)

COLUMNS = ["Name", "Ready", "Status", "Restarts", "Age", "IP", "Node"]


def row(
    name: str,
    ready: str = "1/1",
    status: str = "Running",
    restarts: str = "0",
    uid: str | None = None,
):
    return {
        "cells": [name, ready, status, restarts, "10m", "10.0.0.1", "node-1"],
        "object": {
            "kind": "PartialObjectMetadata",
            "metadata": {"name": name, "namespace": "demo", "uid": uid or f"uid-{name}"},
        },
    }


def table(*rows):
    return {
        "kind": "Table",
        "metadata": {},
        "columnDefinitions": [{"name": name} for name in COLUMNS],
        "rows": list(rows),
    }


def fake_collector(context: TrustedContext, *rows) -> PodCollector:
    config = KubernetesApiConfig(
        connection_id=context.connection_id,
        url="https://kubernetes.test",
        credential_ref="env:VYOM_TEST_TOKEN",
    )
    transport = httpx.MockTransport(lambda _: httpx.Response(200, json=table(*rows)))
    return PodCollector(config, transport=transport)


async def migrate_db(url: str) -> None:
    async with await psycopg.AsyncConnection.connect(url, autocommit=True) as conn:
        await migrate(conn)


def request_get(app: Any, path: str) -> httpx.Response:
    async def run():
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://vyom.test"
        ) as client:
            return await client.get(path)

    return asyncio.run(run())


def request_post(app: Any, path: str, json_body: dict[str, Any]) -> httpx.Response:
    async def run():
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://vyom.test"
        ) as client:
            return await client.post(path, json=json_body)

    return asyncio.run(run())


# --- Offline tests (no database server required) --------------------------------------------


def test_database_unconfigured_behavior(monkeypatch):
    monkeypatch.setenv("VYOM_TEST_TOKEN", "dummy-token")
    operator = OperatorConfig(context=CONTEXT_A)
    pods = fake_collector(CONTEXT_A, row("web-1"))
    app = create_app(operator, pods=pods)

    # 1. Direct pod view returns 200, evidence intact, persisted is None
    res = request_get(app, "/api/kubernetes/pods")
    assert res.status_code == 200
    body = res.json()
    assert body["configured"] is True
    assert body["evidence"]["coverage"]["returned"] == 1
    assert body["persisted"] is None

    # 2. Citation route returns 503 database not configured
    cit_res = request_get(app, "/api/citations/ev_123/some-item")
    assert cit_res.status_code == 503
    assert cit_res.json()["detail"] == "database not configured"


def test_postgres_outage_does_not_break_pod_view(monkeypatch):
    monkeypatch.setenv("VYOM_TEST_TOKEN", "dummy-token")
    monkeypatch.setenv("VYOM_UNREACHABLE_DB", "postgresql://user:pass@127.0.0.1:1/nonexistent")

    db_config = DatabaseConfig(
        credential_ref="env:VYOM_UNREACHABLE_DB",
        connect_timeout_seconds=0.5,
    )
    operator = OperatorConfig(context=CONTEXT_A, database=db_config)
    pods = fake_collector(CONTEXT_A, row("web-1"))
    app = create_app(operator, pods=pods)

    # 1. Direct pod view succeeds (HTTP 200), evidence returned, but persisted is False
    res = request_get(app, "/api/kubernetes/pods")
    assert res.status_code == 200
    body = res.json()
    assert body["configured"] is True
    assert body["evidence"]["items"][0]["name"] == "web-1"
    assert body["persisted"] is False

    # 2. Citation route reports 503 database unavailable
    cit_res = request_get(app, "/api/citations/ev_123/some-item")
    assert cit_res.status_code == 503
    assert cit_res.json()["detail"] == "database unavailable"


def test_database_config_validates_credential_ref():
    with pytest.raises(ValidationError):
        DatabaseConfig(credential_ref="postgresql://plain-url-forbidden")
    with pytest.raises(ValidationError):
        DatabaseConfig(credential_ref="invalid_ref")

    cfg = DatabaseConfig(credential_ref="env:DB_URL")
    assert cfg.credential_ref == "env:DB_URL"


# --- Real Postgres acceptance tests --------------------------------------------------------


@pytest.mark.postgres
def test_direct_pod_collection_persists_and_citation_resolves(database_url, monkeypatch):
    env_key = f"DB_URL_{uuid.uuid4().hex[:8].upper()}"
    monkeypatch.setenv(env_key, database_url)
    monkeypatch.setenv("VYOM_TEST_TOKEN", "dummy-token")
    asyncio.run(migrate_db(database_url))

    db_config = DatabaseConfig(credential_ref=f"env:{env_key}")
    operator = OperatorConfig(context=CONTEXT_A, database=db_config)
    pods = fake_collector(
        CONTEXT_A,
        row("web-1", "1/1", "Running", "0", uid="u1"),
        row("web-2", "0/1", "CrashLoopBackOff", "4", uid="u2"),
    )
    app = create_app(operator, pods=pods)

    # 1. Call GET /api/kubernetes/pods
    res = request_get(app, "/api/kubernetes/pods")
    assert res.status_code == 200
    body = res.json()
    assert body["configured"] is True
    assert body["persisted"] is True
    evidence_id = body["evidence"]["id"]
    item_id_1 = body["evidence"]["items"][0]["id"]
    item_id_2 = body["evidence"]["items"][1]["id"]

    # 2. Resolve citation for web-2 via GET /api/citations/{evidence_id}/{item_id}
    cit_res = request_get(app, f"/api/citations/{evidence_id}/{item_id_2}")
    assert cit_res.status_code == 200
    cit_body = cit_res.json()
    assert cit_body["run_id"] == evidence_id
    assert cit_body["item_id"] == item_id_2
    assert cit_body["name"] == "web-2"
    assert cit_body["native_uid"] == "u2"
    assert cit_body["attributes"]["status"] == "CrashLoopBackOff"
    assert cit_body["resource_id"] is not None
    assert cit_body["resource_removed_at"] is None

    # 3. Resolve citation for web-1
    cit_res_1 = request_get(app, f"/api/citations/{evidence_id}/{item_id_1}")
    assert cit_res_1.status_code == 200
    assert cit_res_1.json()["name"] == "web-1"
    assert cit_res_1.json()["native_uid"] == "u1"


@pytest.mark.postgres
def test_citation_resolves_after_api_restart(database_url, monkeypatch):
    """Proves persistence across API restart: citation is read by a brand new app instance."""
    env_key = f"DB_URL_{uuid.uuid4().hex[:8].upper()}"
    monkeypatch.setenv(env_key, database_url)
    monkeypatch.setenv("VYOM_TEST_TOKEN", "dummy-token")
    asyncio.run(migrate_db(database_url))

    db_config = DatabaseConfig(credential_ref=f"env:{env_key}")
    operator = OperatorConfig(context=CONTEXT_A, database=db_config)
    pods = fake_collector(CONTEXT_A, row("web-1", "1/1", "Running", "0", uid="u1"))

    # Instance 1 records the collection
    app_1 = create_app(operator, pods=pods)
    res = request_get(app_1, "/api/kubernetes/pods")
    assert res.status_code == 200 and res.json()["persisted"] is True
    evidence_id = res.json()["evidence"]["id"]
    item_id = res.json()["evidence"]["items"][0]["id"]

    # Instance 1 is destroyed; Instance 2 starts fresh with the same database
    del app_1
    app_2 = create_app(operator, pods=None)  # no collector needed to resolve stored citations

    cit_res = request_get(app_2, f"/api/citations/{evidence_id}/{item_id}")
    assert cit_res.status_code == 200
    cit_body = cit_res.json()
    assert cit_body["name"] == "web-1"
    assert cit_body["native_uid"] == "u1"
    assert cit_body["run_id"] == evidence_id


@pytest.mark.postgres
def test_cross_workspace_citation_lookup_returns_404(database_url, monkeypatch):
    """Workspace B cannot resolve citations recorded by Workspace A."""
    env_key = f"DB_URL_{uuid.uuid4().hex[:8].upper()}"
    monkeypatch.setenv(env_key, database_url)
    monkeypatch.setenv("VYOM_TEST_TOKEN", "dummy-token")
    asyncio.run(migrate_db(database_url))

    db_config = DatabaseConfig(credential_ref=f"env:{env_key}")
    operator_a = OperatorConfig(context=CONTEXT_A, database=db_config)
    pods_a = fake_collector(CONTEXT_A, row("web-1", uid="u1"))
    app_a = create_app(operator_a, pods=pods_a)

    # Persist in Workspace A
    res_a = request_get(app_a, "/api/kubernetes/pods")
    assert res_a.status_code == 200 and res_a.json()["persisted"] is True
    evidence_id = res_a.json()["evidence"]["id"]
    item_id = res_a.json()["evidence"]["items"][0]["id"]

    # Query same citation from Workspace B
    operator_b = OperatorConfig(context=CONTEXT_B, database=db_config)
    app_b = create_app(operator_b, pods=None)
    res_b = request_get(app_b, f"/api/citations/{evidence_id}/{item_id}")
    assert res_b.status_code == 404
    assert res_b.json()["detail"] == "citation not found"


@pytest.mark.postgres
def test_unknown_citation_returns_404(database_url, monkeypatch):
    env_key = f"DB_URL_{uuid.uuid4().hex[:8].upper()}"
    monkeypatch.setenv(env_key, database_url)
    asyncio.run(migrate_db(database_url))

    db_config = DatabaseConfig(credential_ref=f"env:{env_key}")
    operator = OperatorConfig(context=CONTEXT_A, database=db_config)
    app = create_app(operator, pods=None)

    res = request_get(app, "/api/citations/ev_no_such_run/no_such_item")
    assert res.status_code == 404
    assert res.json()["detail"] == "citation not found"


@pytest.mark.postgres
def test_chat_citations_resolve_from_stored_runs(database_url, tmp_path, monkeypatch):
    """Chat question gathers evidence via tool, persists it, and the answer's citations resolve."""
    env_key = f"DB_URL_{uuid.uuid4().hex[:8].upper()}"
    monkeypatch.setenv(env_key, database_url)
    monkeypatch.setenv("VYOM_TEST_MODEL_KEY", "dummy-key")
    asyncio.run(migrate_db(database_url))

    upstream = Upstream()

    class ScriptedModel:
        def __init__(self):
            self.turn = 0

        async def __call__(self, request: httpx.Request) -> httpx.Response:
            self.turn += 1
            if self.turn == 1:
                # Propose tool call
                return httpx.Response(
                    200,
                    json={
                        "id": "gen-1",
                        "choices": [
                            {
                                "message": {
                                    "role": "assistant",
                                    "content": None,
                                    "tool_calls": [
                                        {
                                            "id": "call-1",
                                            "type": "function",
                                            "function": {
                                                "name": "kubernetes__pods_list",
                                                "arguments": '{"namespace":"demo"}',
                                            },
                                        }
                                    ],
                                },
                                "finish_reason": "tool_calls",
                            }
                        ],
                        "usage": {"prompt_tokens": 10, "completion_tokens": 10},
                    },
                )
            # Turn 2: answer citing pod [2]
            return httpx.Response(
                200,
                json={
                    "id": "gen-2",
                    "choices": [
                        {
                            "message": {
                                "role": "assistant",
                                "content": "The pod [2] has failed.",
                            },
                            "finish_reason": "stop",
                        }
                    ],
                    "usage": {"prompt_tokens": 20, "completion_tokens": 10},
                },
            )

    db_config = DatabaseConfig(credential_ref=f"env:{env_key}")
    model_cfg = ModelConfig(
        provider="openrouter",
        model="test/model",
        base_url="https://openrouter.ai/api/v1",
        credential_ref="env:VYOM_TEST_MODEL_KEY",
    )
    operator = mcp_config(tmp_path).model_copy(update={"model": model_cfg, "database": db_config})
    client = ModelClient(model_cfg, transport=httpx.MockTransport(ScriptedModel()))

    async def send(host):
        app = create_app(operator, host=host, model=client)
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://vyom.test") as cl:
            # 1. Ask question in chat
            chat_res = await cl.post("/api/chat", json={"question": "which pods are failing?"})
            assert chat_res.status_code == 200
            chat_body = chat_res.json()
            assert chat_body["outcome"] == "answered"
            assert len(chat_body["citations"]) == 1
            cited = chat_body["citations"][0]
            assert cited["ref"] == 2
            assert cited["item_id"] == JOB_ID

            # 2. Resolve citation via GET /api/citations/{evidence_id}/{item_id}
            cit_res = await cl.get(f"/api/citations/{cited['evidence_id']}/{cited['item_id']}")
            assert cit_res.status_code == 200
            cit_body = cit_res.json()
            assert cit_body["name"] == "job-7"
            assert cit_body["attributes"]["phase"] == "Failed"
            assert cit_body["run_id"] == cited["evidence_id"]
            assert cit_body["item_id"] == cited["item_id"]

    mcp_run(upstream, operator, send)
