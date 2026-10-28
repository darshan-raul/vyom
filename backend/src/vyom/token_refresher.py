"""Keeps the collector's token fresh (K8S02): ``python -m vyom.token_refresher``.

The API pod runs as ``vyom-api``, which has no Kubernetes access, but its pods view must read
the Kubernetes API as ``vyom-collector``. A CronJob runs this module as its own ServiceAccount,
which may mint tokens for ``vyom-collector`` only and patch one named Secret only. It asks
the API server for a short-lived token and writes it to that Secret. The API mounts the Secret
as a file and reads it on every request, so a new token is picked up without a restart.

Nothing here prints or logs the token.
"""

import base64  # Secret values travel base64-encoded
import os
import ssl
import sys
from pathlib import Path

import httpx

# Where Kubernetes mounts this pod's own ServiceAccount token, CA and namespace.
_SA_DIR = Path("/var/run/secrets/kubernetes.io/serviceaccount")
_API_URL = "https://kubernetes.default.svc"


def refresh(http: httpx.Client, namespace: str, account: str, secret: str, seconds: int) -> None:
    """Mint a token for ``account`` and store it under key ``token`` in ``secret``."""
    # TokenRequest: the API server signs a new token that expires after ``seconds``.
    minted = http.post(
        f"/api/v1/namespaces/{namespace}/serviceaccounts/{account}/token",
        json={
            "apiVersion": "authentication.k8s.io/v1",
            "kind": "TokenRequest",
            "spec": {"expirationSeconds": seconds},
        },
    )
    minted.raise_for_status()
    token = minted.json()["status"]["token"]
    # A merge patch changes only the ``token`` key and needs only the "patch" verb.
    stored = http.patch(
        f"/api/v1/namespaces/{namespace}/secrets/{secret}",
        headers={"Content-Type": "application/merge-patch+json"},
        json={"data": {"token": base64.b64encode(token.encode()).decode()}},
    )
    stored.raise_for_status()


def main() -> int:
    account = os.environ.get("COLLECTOR_ACCOUNT", "vyom-collector")
    secret = os.environ["COLLECTOR_TOKEN_SECRET"]
    seconds = int(os.environ.get("TOKEN_SECONDS", "3600"))
    namespace = (_SA_DIR / "namespace").read_text().strip()
    with httpx.Client(
        base_url=_API_URL,
        headers={"Authorization": f"Bearer {(_SA_DIR / 'token').read_text().strip()}"},
        verify=ssl.create_default_context(cafile=str(_SA_DIR / "ca.crt")),
        timeout=httpx.Timeout(15, connect=5),
        trust_env=False,
    ) as http:
        try:
            refresh(http, namespace, account, secret, seconds)
        except (httpx.HTTPError, KeyError, ValueError) as error:
            # The type and status only: a response body or URL could name a secret.
            status = getattr(getattr(error, "response", None), "status_code", "-")
            print(f"token refresh failed: {type(error).__name__} status={status}", file=sys.stderr)
            return 1
    print("collector token refreshed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
