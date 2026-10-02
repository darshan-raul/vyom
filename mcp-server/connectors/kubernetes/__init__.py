"""Read-only Kubernetes collection independent of cloud billing connectors.

Use KubernetesOperations only with context/grants resolved by the backend. This
package is deliberately not registered in the legacy unauthenticated MCP server.
"""

from .models import ClusterConnection, ClusterGrant, RequestContext
from .operations import KubernetesOperations

__all__ = ["ClusterConnection", "ClusterGrant", "RequestContext", "KubernetesOperations"]
