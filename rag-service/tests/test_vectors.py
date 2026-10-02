"""Tenant/model isolation tests against the Qdrant SDK boundary."""

import importlib.util
import sys
import unittest
from enum import Enum
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from inference.settings import BedrockSettings, TITAN_V2
from inference.types import ConfigurationError, InferenceError


class Distance(str, Enum):
    COSINE = "Cosine"
    DOT = "Dot"


class VectorIsolationTests(unittest.TestCase):
    def setUp(self):
        self.settings = BedrockSettings(TITAN_V2, (TITAN_V2,), dimensions=256)
        self.tenant_a = "00000000-0000-0000-0000-000000000001"
        self.tenant_b = "00000000-0000-0000-0000-000000000002"
        models = SimpleNamespace(Distance=Distance)
        for name in ("VectorParams", "PointStruct", "Filter", "FieldCondition", "MatchValue"):
            setattr(models, name, SimpleNamespace)
        module_path = Path(__file__).parents[1] / "qdrant" / "client.py"
        spec = importlib.util.spec_from_file_location("vector_client_under_test", module_path)
        self.module = importlib.util.module_from_spec(spec)
        with patch.dict(sys.modules, {
            "qdrant_client": SimpleNamespace(QdrantClient=Mock()),
            "qdrant_client.models": models,
        }):
            spec.loader.exec_module(self.module)
        self.client = Mock()
        self.client.get_collection.return_value = SimpleNamespace(config=SimpleNamespace(
            params=SimpleNamespace(vectors=SimpleNamespace(size=256, distance=Distance.COSINE))
        ))
        self.client.search.return_value = []
        patcher = patch.object(self.module, "_get_client", return_value=self.client)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_each_tenant_reads_only_its_versioned_collection(self):
        for tenant in (self.tenant_a, self.tenant_b):
            self.module.search_chunks(tenant, [1] * 256, settings=self.settings)
            self.assertEqual(self.client.search.call_args.kwargs["collection_name"],
                             self.settings.collection_name(tenant))

    def test_legacy_collection_is_never_a_fallback(self):
        not_found = RuntimeError("collection not found")
        not_found.status_code = 404
        self.client.get_collection.side_effect = not_found
        with self.assertRaises(InferenceError):
            self.module.search_chunks(self.tenant_a, [1] * 256, settings=self.settings)
        self.client.search.assert_not_called()
        self.client.get_collection.assert_called_once_with(
            collection_name=self.settings.collection_name(self.tenant_a)
        )
        self.client.get_collections.assert_not_called()

    def test_incompatible_schema_prevents_read_and_write(self):
        for vectors in (SimpleNamespace(size=384, distance=Distance.COSINE),
                        SimpleNamespace(size=256, distance=Distance.DOT), {}):
            self.client.get_collection.return_value.config.params.vectors = vectors
            with self.assertRaises(InferenceError):
                self.module.search_chunks(self.tenant_a, [1] * 256, settings=self.settings)
            with self.assertRaises(InferenceError):
                self.module.upsert_chunk(self.tenant_a, "chunk", [1] * 256, {}, settings=self.settings)
        self.client.search.assert_not_called()
        self.client.upsert.assert_not_called()

    def test_wrong_dimension_or_invalid_tenant_prevents_storage_access(self):
        with self.assertRaises(InferenceError):
            self.module.search_chunks(self.tenant_a, [1] * 384, settings=self.settings)
        with self.assertRaises(InferenceError):
            self.module.upsert_chunk(self.tenant_a, "chunk", [1] * 384, {}, settings=self.settings)
        with self.assertRaises(ConfigurationError):
            self.module.search_chunks("../other-tenant", [1] * 256, settings=self.settings)
        self.client.get_collection.assert_not_called()
        self.client.upsert.assert_not_called()

    def test_new_collection_has_new_dimensions_and_metric(self):
        not_found = RuntimeError("collection not found")
        not_found.status_code = 404
        self.client.get_collection.side_effect = [not_found, self.client.get_collection.return_value]
        self.module.ensure_collection(self.tenant_a, settings=self.settings)
        request = self.client.create_collection.call_args.kwargs
        self.assertEqual(request["collection_name"], self.settings.collection_name(self.tenant_a))
        self.assertEqual(request["vectors_config"].size, 256)
        self.assertEqual(request["vectors_config"].distance, Distance.COSINE)

    def test_point_payload_records_embedding_version(self):
        self.module.upsert_chunk(self.tenant_a, "chunk", [1] * 256, {"source": "builtin"}, settings=self.settings)
        request = self.client.upsert.call_args.kwargs
        self.assertEqual(request["collection_name"], self.settings.collection_name(self.tenant_a))
        self.assertEqual(request["points"][0].payload["embedding_version"], self.settings.vector_version)


if __name__ == "__main__":
    unittest.main()
