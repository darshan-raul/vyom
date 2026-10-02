"""Small typed boundaries usable by the future LangGraph classification node."""

from dataclasses import dataclass
from enum import Enum
from typing import Protocol


class InferenceError(RuntimeError):
    """Safe application error; never contains provider bodies or request content."""


class ConfigurationError(InferenceError):
    pass


class Domain(str, Enum):
    COST = "cost"
    INVENTORY = "inventory"
    SECURITY = "security"
    CHANGES = "changes"
    KUBERNETES = "kubernetes"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class RouteDecision:
    domain: Domain = Domain.UNKNOWN
    escalate: bool = True
    reason: str = "classifier_disabled"
    probability: float | None = None
    confidence: float | None = None


class IntentClassifier(Protocol):
    async def classify(self, request_text: str) -> RouteDecision: ...


async def route_request(
    request_text: str, classifier: IntentClassifier | None = None
) -> RouteDecision:
    """A domain is a planning hint; it cannot grant access or execute a tool.

    Disabled/unavailable classification leaves planning to the Bedrock workflow.
    Only request text crosses this interface, never graph state or tool results.
    """
    if classifier is None:
        return RouteDecision()
    try:
        return await classifier.classify(request_text)
    except InferenceError:
        return RouteDecision(reason="classifier_unavailable")
