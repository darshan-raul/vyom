"""Operator configuration: the trusted context, the MCP endpoints Vyom may connect to, the
reasoning endpoint and the direct collector's Kubernetes API.

Loaded once from a file the operator mounts. Nothing in a request or a model reply can add
an endpoint, change a URL or pick a credential: callers name a tool ID and the registry
decides where it goes and what is presented there.
"""

import json
import re
from pathlib import Path
from urllib.parse import urlsplit  # splits a URL into scheme, host, path and so on

# field_validator checks one field; model_validator checks the object as a whole.
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from vyom.agent.model import ModelConfig
from vyom.collectors.kubernetes import KubernetesApiConfig
from vyom.context import TrustedContext
from vyom.credentials import check_reference, read_credential

SERVER_ID = r"^[a-z][a-z0-9]{0,30}$"  # no underscore: "__" separates server from tool
_TOOL_NAME = re.compile(r"^[A-Za-z0-9_.-]{1,64}$")


# Example: tool_id("kubernetes", "pods_list") -> "kubernetes__pods_list".
def tool_id(server_id: str, tool_name: str) -> str:
    """Server-qualified tool identity, safe as a model-facing function name."""
    return f"{server_id}__{tool_name}"


# Safety limits for one server. ``gt``/``le`` mean greater-than / less-or-equal; values
# outside the range are rejected when the config loads.
class Limits(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    connect_timeout_seconds: float = Field(default=5, gt=0, le=30)
    call_timeout_seconds: float = Field(default=15, gt=0, le=120)
    max_response_bytes: int = Field(default=262_144, gt=0, le=4_194_304)


# Settings for one upstream MCP server, read from the operator's config file.
class ServerConfig(BaseModel):
    # Validation errors must not echo a mistakenly pasted credential.
    model_config = ConfigDict(frozen=True, extra="forbid", hide_input_in_errors=True)

    id: str = Field(pattern=SERVER_ID)
    connection_id: str  # the authorized connection this endpoint serves
    url: str
    # Cleartext is an explicit operator choice (an in-cluster Service without TLS).
    allow_cleartext: bool = False
    ca_file: str | None = None
    # Send ``Host: localhost`` whatever the URL says. Some upstreams (the Go MCP SDK) refuse a
    # non-localhost Host on a connection that arrives over loopback, which is how a sidecar
    # proxy delivers it. TLS is still verified against the URL's host name.
    loopback_host_header: bool = False
    # Where the host reads its bearer credential at connect time: "file:/path" or
    # "env:NAME". The value itself never appears in configuration.
    credential_ref: str
    enabled_tools: frozenset[str] = frozenset()  # upstream tool names
    limits: Limits = Limits()

    # A validator runs automatically when the object is created. ``@field_validator("url")``
    # attaches this check to the ``url`` field; @classmethod is required by pydantic.
    # Returning the value accepts it; raising ValueError rejects it.
    @field_validator("url")
    @classmethod
    def _plain_endpoint(cls, url: str) -> str:
        parts = urlsplit(url)
        if parts.scheme not in ("http", "https") or not parts.hostname:
            raise ValueError("url must be an http(s) endpoint")
        if parts.username or parts.password or parts.query or parts.fragment:
            raise ValueError("url must not carry credentials, a query or a fragment")
        return url

    @field_validator("credential_ref")
    @classmethod
    def _reference_only(cls, ref: str) -> str:
        return check_reference(ref)

    @field_validator("enabled_tools")
    @classmethod
    def _tool_names(cls, names: frozenset[str]) -> frozenset[str]:
        if not all(_TOOL_NAME.fullmatch(name) for name in names):
            raise ValueError("enabled_tools must be upstream tool names")
        return names

    # Runs after all fields are valid, for rules that involve more than one field.
    @model_validator(mode="after")
    def _transport_security(self) -> "ServerConfig":
        if urlsplit(self.url).scheme == "http" and not self.allow_cleartext:
            raise ValueError("an http url requires allow_cleartext: true")
        return self

    def read_credential(self) -> str:
        """Resolve the reference now, so a rotated token is picked up on the next connect."""
        return read_credential(self.credential_ref)


# The whole config file: one trusted context plus the servers, model and collector settings.
class OperatorConfig(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", hide_input_in_errors=True)

    context: TrustedContext
    mcp_servers: tuple[ServerConfig, ...] = ()
    model: ModelConfig | None = None  # absent: chat is unavailable, never a silent fallback
    # The direct collector's API server and identity; absent: no deterministic resource view.
    kubernetes: KubernetesApiConfig | None = None

    @model_validator(mode="after")
    def _unique_server_ids(self) -> "OperatorConfig":
        ids = [server.id for server in self.mcp_servers]
        # A set drops duplicates, so a shorter set means some ID appeared twice.
        if len(ids) != len(set(ids)):
            raise ValueError("mcp server ids must be unique")
        return self

    def server(self, server_id: str) -> ServerConfig | None:
        # next(generator, default) returns the first match, or None if there is none.
        return next((server for server in self.mcp_servers if server.id == server_id), None)


def load_operator_config(path: str | Path) -> OperatorConfig:
    # Read the JSON file, parse it to Python data, then validate it into a typed object.
    return OperatorConfig.model_validate(json.loads(Path(path).read_text()))
