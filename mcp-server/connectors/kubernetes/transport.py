"""Bounded GET-only API transport using enrolled endpoint and rendered files."""

import json
import socket
import ssl
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlsplit
from urllib.request import HTTPRedirectHandler, HTTPSHandler, ProxyHandler, Request, build_opener

from .models import AccessDenied, ClusterConnection, CollectionError


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class KubernetesHTTP:
    """Only build after context/grant checks. Does not evaluate kubeconfig hooks.

    approved_host is operator-controlled enrollment data, not an SSRF defense by
    itself. Enrollment/network policy must validate permitted network destinations
    (B11.2). This transport cannot follow redirects or environment proxies.
    """

    MAX_BYTES = 4 * 1024 * 1024

    def __init__(self, connection: ClusterConnection):
        parsed = urlsplit(connection.endpoint)
        if (parsed.scheme != "https" or not parsed.hostname
                or parsed.hostname != connection.approved_host
                or parsed.username is not None or parsed.password is not None
                or parsed.path not in ("", "/") or parsed.query or parsed.fragment):
            raise CollectionError("denied")
        # Credentials must be a backend-rendered tenant/cluster file, never a
        # caller-supplied filename. CA and token share the same credential scope.
        expected = Path("/etc/secrets/tenants") / str(connection.tenant_id) / "clusters" / str(connection.cluster_id)
        for filename in (connection.token_file, connection.ca_file):
            if Path(filename).parent != expected:
                raise CollectionError("denied")
        self.connection = connection
        try:
            tls = ssl.create_default_context(cafile=connection.ca_file)
            self.opener = build_opener(ProxyHandler({}), NoRedirect(), HTTPSHandler(context=tls))
        except (OSError, ValueError):
            raise CollectionError("unavailable") from None

    def get(self, path: str, params: dict) -> dict:
        # Only the closed resource registry's list paths can reach this boundary.
        from .models import RESOURCES

        parts = path.split("/")
        allowed = False
        for resource in RESOURCES:
            try:
                namespace = parts[parts.index("namespaces") + 1] if resource.namespaced else None
                allowed = allowed or path == resource.path(namespace)
            except (AccessDenied, ValueError, IndexError):
                continue
        if not allowed or set(params) - {"limit", "continue"}:
            raise CollectionError("denied")
        try:
            token = Path(self.connection.token_file).read_text().strip()
            if not token or any(char.isspace() for char in token):
                raise CollectionError("denied")
            request = Request(
                self.connection.endpoint.rstrip("/") + path + "?" + urlencode(params),
                headers={"Authorization": "Bearer " + token, "Accept": "application/json"},
                method="GET",
            )
            with self.opener.open(request, timeout=10) as response:
                raw = response.read(self.MAX_BYTES + 1)
            if len(raw) > self.MAX_BYTES:
                raise CollectionError("limit_exceeded")
            data = json.loads(raw)
            if not isinstance(data, dict):
                raise CollectionError("invalid_response")
            return data
        except HTTPError as exc:
            code = "denied" if exc.code in (401, 403) else "unsupported" if exc.code == 404 else "unavailable"
            exc.close()
            raise CollectionError(code) from None
        except (URLError, OSError, socket.timeout):
            raise CollectionError("unavailable") from None
        except (ValueError, TypeError):
            raise CollectionError("invalid_response") from None
