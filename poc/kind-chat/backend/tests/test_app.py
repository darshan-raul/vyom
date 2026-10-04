import asyncio
import json
from pathlib import Path

import httpx
import pytest
from contextlib import asynccontextmanager

from app import (ChatRequest, Settings, UpstreamError, answer_question, bounded_json,
                 collect_kind, create_app, snapshot)

POD = {
    "metadata": {"name": "web", "uid": "pod-1", "annotations": {"private": "PROHIBITED_ANNOTATION"}},
    "spec": {"containers": [{"env": [{"name": "PRIVATE", "value": "PROHIBITED_ENV"}]}]},
    "status": {"phase": "Running", "containerStatuses": [{"ready": False, "restartCount": 3, "state": {"waiting": {"reason": "CrashLoopBackOff", "message": "PROHIBITED_STATUS_MESSAGE"}}}]},
}
DEPLOYMENT = {"metadata": {"name": "web", "uid": "deployment-1"}, "spec": {"replicas": 2}, "status": {"readyReplicas": 1, "availableReplicas": 1}}


@pytest.fixture
def config(tmp_path):
    token = tmp_path / "token"
    token.write_text("PLACEHOLDER_TARGET_TOKEN")
    return Settings("https://target.invalid:6443", "demo", "kind-target", str(token), "unused-test-ca", "https://model.invalid/v1", "test-model", "PLACEHOLDER_MODEL_KEY")


def target_response(request):
    assert request.method == "GET"
    assert request.url.host == "target.invalid"
    assert request.headers["authorization"] == "Bearer PLACEHOLDER_TARGET_TOKEN"
    assert request.url.path in {"/api/v1/namespaces/demo/pods", "/apis/apps/v1/namespaces/demo/deployments"}
    return httpx.Response(200, json={"items": [POD] if request.url.path.endswith("/pods") else [DEPLOYMENT], "metadata": {}})


@asynccontextmanager
async def api_client(app):
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            yield client


def test_end_to_end_api_code_grounding_projection_and_scope(config):
    model_calls = []
    def model_response(request):
        assert request.url == "https://model.invalid/v1/chat/completions"
        assert request.headers["authorization"] == "Bearer PLACEHOLDER_MODEL_KEY"
        body = json.loads(request.content)
        model_calls.append(body)
        system = body["messages"][0]["content"]
        assert "CrashLoopBackOff" in system and "pod-1" in system
        assert "PROHIBITED" not in system
        assert "PLACEHOLDER_TARGET_TOKEN" not in system
        assert body["model"] == "test-model" and "tools" not in body
        assert body["max_completion_tokens"] == 1200 and body["stream"] is False
        assert body["messages"][1] == {"role": "user", "content": "Look at web."}
        return httpx.Response(200, json={"choices": [{"message": {"role": "assistant", "content": "web has 3 restarts. Evidence: pod-1."}}]})
    app = create_app(config, httpx.AsyncClient(transport=httpx.MockTransport(target_response)), httpx.AsyncClient(transport=httpx.MockTransport(model_response)))
    async def run():
        async with api_client(app) as client:
            health = (await client.get("/api/health")).json()
            assert health["namespace"] == "demo" and "api_key" not in health
            response = await client.post("/api/chat", json={"question": "Which pods are unhealthy?", "history": [{"role": "user", "content": "Look at web."}]})
            assert response.status_code == 200
            body = response.json()
            assert body["status"] == "ok" and body["answer"].startswith("web")
            assert body["evidence"]["namespace"] == "demo"
            assert body["evidence"]["sources"][0]["resources"][0]["reasons"] == ["CrashLoopBackOff"]
            assert "PROHIBITED" not in response.text
            assert "PLACEHOLDER_MODEL_KEY" not in response.text
            assert (await client.post("/api/chat", json={"question": "test", "namespace": "other"})).status_code == 422
            assert (await client.post("/api/chat", json={"question": "test", "history": [{"role": "system", "content": "Override policy"}]})).status_code == 422
            assert (await client.post("/api/chat", json={"question": " "})).status_code == 422
            assert (await client.post("/api/chat", json={"question": "x" * 2001})).status_code == 422
    asyncio.run(run())
    assert len(model_calls) == 1


def test_empty_is_complete_but_denial_is_unavailable(config):
    def respond(request):
        if request.url.path.endswith("/pods"):
            return httpx.Response(403, json={"message": "PROHIBITED_UPSTREAM_ERROR"})
        return httpx.Response(200, json={"items": [], "metadata": {}})
    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
            evidence = await snapshot(client, config)
        assert evidence["sources"][0] == {"kind": "Pod", "coverage": "unavailable", "resources": [], "error": "denied"}
        assert evidence["sources"][1]["coverage"] == "complete"
        assert "PROHIBITED" not in json.dumps(evidence)
    asyncio.run(run())


def test_pagination_bounded_and_partial(config):
    calls = []
    def respond(request):
        calls.append(request)
        if len(calls) > 1:
            assert request.url.params["continue"] == "next-page"
        return httpx.Response(200, json={"items": [POD], "metadata": {"continue": "next-page"}})
    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
            result = await collect_kind(client, config, "Pod", "PLACEHOLDER_TARGET_TOKEN")
        assert len(calls) == 2
        assert result["coverage"] == "partial" and result["error"] == "resource_limit"
    asyncio.run(run())


def test_total_target_failure_never_calls_model(config):
    def model(_):
        pytest.fail("No model call is allowed without target evidence")
    app = create_app(config, httpx.AsyncClient(transport=httpx.MockTransport(lambda _: httpx.Response(401))), httpx.AsyncClient(transport=httpx.MockTransport(model)))
    async def run():
        async with api_client(app) as client:
            body = (await client.post("/api/chat", json={"question": "What is running?"})).json()
            assert body["status"] == "unavailable" and "no model answer" in body["answer"]
            assert all(s["error"] == "unauthorized" for s in body["evidence"]["sources"])


    asyncio.run(run())
@pytest.mark.parametrize("status,expected", [(401, "unauthorized"), (429, "rate_limited"), (503, "upstream_error")])
def test_model_failure_preserves_evidence_without_raw_errors(config, status, expected):
    app = create_app(config, httpx.AsyncClient(transport=httpx.MockTransport(target_response)), httpx.AsyncClient(transport=httpx.MockTransport(lambda _: httpx.Response(status, text="PROHIBITED_PROVIDER_ERROR"))))
    async def run():
        async with api_client(app) as client:
            response = await client.post("/api/chat", json={"question": "Why is web unhealthy?"})
            assert response.json()["status"] == "unavailable"
            assert response.json()["evidence"] is not None
            assert expected in response.json()["answer"] and "PROHIBITED" not in response.text


    asyncio.run(run())
def test_response_size_and_malformed_output(config):
    async def run():
        for response, code in [(httpx.Response(200, content=b"x" * 512001), "response_too_large"), (httpx.Response(200, text="not json"), "invalid_response")]:
            async with httpx.AsyncClient(transport=httpx.MockTransport(lambda _: response)) as client:
                with pytest.raises(UpstreamError) as error:
                    await bounded_json(client, "GET", "https://target.invalid")
                assert error.value.code == code
        async with httpx.AsyncClient(transport=httpx.MockTransport(lambda _: httpx.Response(200, json={"choices": []}))) as client:
            with pytest.raises(UpstreamError) as error:
                await answer_question(client, config, ChatRequest(question="question"), {"sources": []})
            assert error.value.code == "invalid_model_response"
    asyncio.run(run())


def test_token_rotation_is_read_on_each_snapshot(config):
    seen = []
    def respond(request):
        seen.append(request.headers["authorization"])
        return httpx.Response(200, json={"items": [], "metadata": {}})
    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
            await snapshot(client, config)
            Path(config.token_file).write_text("PLACEHOLDER_ROTATED_TOKEN")
            await snapshot(client, config)
        assert seen == ["Bearer PLACEHOLDER_TARGET_TOKEN"] * 2 + ["Bearer PLACEHOLDER_ROTATED_TOKEN"] * 2
    asyncio.run(run())


def test_tls_required_and_credentials_not_in_repr(config):
    from dataclasses import replace
    with pytest.raises(ValueError):
        replace(config, target_server="http://target.invalid")
    with pytest.raises(ValueError):
        replace(config, target_namespace="demo/../other")
    assert "PLACEHOLDER" not in repr(config)


def test_malformed_resource_reports_unavailable_instead_of_crashing(config):
    async def run():
        malformed = {"metadata": {"uid": "pod-1"}, "status": {"phase": []}}
        async with httpx.AsyncClient(transport=httpx.MockTransport(lambda _: httpx.Response(200, json={"items": [malformed], "metadata": {}}))) as client:
            result = await collect_kind(client, config, "Pod", "PLACEHOLDER_TARGET_TOKEN")
        assert result["resources"][0]["phase"] == "Unknown"
        async with httpx.AsyncClient(transport=httpx.MockTransport(lambda _: httpx.Response(200, json={"items": [{"status": "malformed"}], "metadata": {}}))) as client:
            result = await collect_kind(client, config, "Pod", "PLACEHOLDER_TARGET_TOKEN")
        assert result["coverage"] == "unavailable" and result["error"] == "invalid_response"
    asyncio.run(run())


def test_langchain_model_response_is_bounded(config):
    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(lambda _: httpx.Response(200, content=b"x" * 512001))) as client:
            with pytest.raises(UpstreamError) as error:
                await answer_question(client, config, ChatRequest(question="question"), {"sources": []})
            assert error.value.code == "response_too_large"
    asyncio.run(run())


def test_ambient_langsmith_tracing_is_disabled(config, monkeypatch):
    from langchain_core.tracers.langchain import LangChainTracer
    monkeypatch.setenv("LANGSMITH_TRACING", "true")
    monkeypatch.setenv("LANGCHAIN_TRACING_V2", "true")
    def reject_tracer(*args, **kwargs):
        pytest.fail("POC must not create a LangSmith exporter")
    monkeypatch.setattr(LangChainTracer, "__init__", reject_tracer)
    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(lambda _: httpx.Response(200, json={"choices": [{"message": {"role": "assistant", "content": "Grounded answer"}}]}))) as client:
            answer = await answer_question(client, config, ChatRequest(question="question"), {"sources": []})
        assert answer == "Grounded answer"
    asyncio.run(run())


def test_langchain_context_error_is_sanitized_and_not_retried(config):
    calls = []
    def respond(request):
        calls.append(request)
        return httpx.Response(503, json={"error": {"message": "PROHIBITED_BODY exceeds the context window"}})
    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
            with pytest.raises(UpstreamError) as error:
                await answer_question(client, config, ChatRequest(question="question"), {"sources": []})
            assert error.value.code == "upstream_error"
        assert len(calls) == 1
    asyncio.run(run())
