"""Internal collection-to-analysis flow. No public auth or tool registration."""

from .analysis import health, posture, topology
from .collector import KubernetesCollector


class KubernetesOperations:
    def __init__(self, collector: KubernetesCollector | None = None):
        self.collector = collector or KubernetesCollector()

    def inspect(self, context, connection, grant, *, kinds=None) -> dict:
        snapshot = self.collector.collect(context, connection, grant, kinds=kinds)
        return {"snapshot": snapshot, "topology": topology(snapshot), "health": health(snapshot), "posture": posture(snapshot)}
