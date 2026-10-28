import base64
import json

import httpx
import pytest

from vyom.token_refresher import refresh

TOKEN = "header.payload.signature"


def client(handler):
    return httpx.Client(base_url="https://k", transport=httpx.MockTransport(handler))


def test_mints_for_the_collector_and_patches_only_the_named_secret():
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append((request.method, request.url.path, request.headers.get("content-type")))
        if request.method == "POST":
            assert json.loads(request.content)["spec"] == {"expirationSeconds": 3600}
            return httpx.Response(201, json={"status": {"token": TOKEN}})
        body = json.loads(request.content)
        assert body == {"data": {"token": base64.b64encode(TOKEN.encode()).decode()}}
        return httpx.Response(200, json={})

    refresh(client(handler), "vyom", "vyom-collector", "vyom-collector-token", 3600)

    assert seen == [
        (
            "POST",
            "/api/v1/namespaces/vyom/serviceaccounts/vyom-collector/token",
            "application/json",
        ),
        (
            "PATCH",
            "/api/v1/namespaces/vyom/secrets/vyom-collector-token",
            "application/merge-patch+json",
        ),
    ]


def test_a_refused_mint_fails_and_writes_nothing():
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.method)
        return httpx.Response(403, json={"message": "forbidden"})

    with pytest.raises(httpx.HTTPStatusError):
        refresh(client(handler), "vyom", "vyom-collector", "vyom-collector-token", 3600)
    assert calls == ["POST"]
