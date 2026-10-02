"""Offline policy/adapter tests. No credentials, network, or optional SDK needed."""

import io
import json
import sys
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

from embed.text import chunk_text
from inference.bedrock import BedrockChat, BedrockEmbeddings, create_runtime_client
from inference.jev import CRITERIA, GATEWAY_URL, JEV_MODEL, JevClassifier, JevSettings, _post
from inference.settings import BedrockSettings, TITAN_V2
from inference.types import ConfigurationError, Domain, InferenceError, route_request


class InferenceTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.bedrock_policy = self.root / "bedrock-policy.json"
        self.bedrock_policy.write_text(json.dumps({
            "region": "ap-south-1", "data_retention_mode": "none",
            "invocation_content_logging": False,
            "approved_models": [TITAN_V2, "anthropic.test-model-v1:0"],
        }))
        self.settings = BedrockSettings(
            TITAN_V2, (TITAN_V2,), policy_file=str(self.bedrock_policy), dimensions=256
        )
        self.jev_policy = self.root / "jev-policy.json"
        self.jev_policy.write_text(json.dumps({
            "external_prompt_classification": True, "data_handling_reviewed": True,
            "gateway": "vercel", "model": JEV_MODEL, "provider": "typesafe-ai",
        }))
        self.key_file = self.root / "ai-gateway-key"
        self.key_file.write_text("test-key-not-a-real-credential\n")
        self.jev_settings = JevSettings(
            enabled=True, api_key_file=str(self.key_file), policy_file=str(self.jev_policy)
        )

    def answer(self, choice="cost", probability=0.96):
        others = (1 - probability) / (len(CRITERIA) - 1)
        return {
            "model": JEV_MODEL,
            "answers": {"intent": {
                "type": "choice", "choice": choice,
                "probabilities": {name: probability if name == choice else others for name in CRITERIA},
                "confidence": 0.9,
            }},
            "providerMetadata": {"gateway": {"routing": {
                "finalProvider": "typesafe-ai", "canonicalSlug": JEV_MODEL,
            }}},
        }

    async def test_embedding_request_matches_titan_api(self):
        client = Mock()
        body = io.BytesIO(json.dumps({"embedding": [1.0] * 256}).encode())
        client.invoke_model.return_value = {"body": body}
        vector = await BedrockEmbeddings(self.settings, client).embed_text("daily spend")
        self.assertEqual(len(vector), 256)
        request = client.invoke_model.call_args.kwargs
        self.assertEqual(request["modelId"], TITAN_V2)
        self.assertEqual(json.loads(request["body"]), {
            "inputText": "daily spend", "dimensions": 256, "normalize": True
        })
        self.assertTrue(body.closed)

    async def test_missing_or_invalid_policy_never_calls_bedrock(self):
        for content in ("{}", "null", "not-json", '{"region":"us-east-1"}'):
            with self.subTest(content=content):
                self.bedrock_policy.write_text(content)
                client = Mock()
                with self.assertRaises(ConfigurationError):
                    await BedrockEmbeddings(self.settings, client).embed_text("query")
                client.invoke_model.assert_not_called()

    async def test_policy_changes_take_effect_on_next_invocation(self):
        client = Mock()
        client.invoke_model.side_effect = lambda **kwargs: {
            "body": io.BytesIO(json.dumps({"embedding": [1] * 256}).encode())
        }
        adapter = BedrockEmbeddings(self.settings, client)
        await adapter.embed_text("first")
        self.bedrock_policy.unlink()
        with self.assertRaises(ConfigurationError):
            await adapter.embed_text("second")
        self.assertEqual(client.invoke_model.call_count, 1)

    async def test_malformed_vectors_never_reach_storage(self):
        for vector in ([1] * 384, [float("nan")] * 256, [True] * 256, [0] * 256):
            with self.subTest(vector_kind=type(vector[0]).__name__, dimension=len(vector)):
                client = Mock()
                client.invoke_model.return_value = {
                    "body": io.BytesIO(json.dumps({"embedding": vector}).encode())
                }
                with self.assertRaises(InferenceError):
                    await BedrockEmbeddings(self.settings, client).embed_text("query")

    async def test_empty_batch_and_input_limits(self):
        client = Mock()
        adapter = BedrockEmbeddings(self.settings, client)
        self.assertEqual(await adapter.embed_texts([]), [])
        for texts in ([" "], ["x"] * 129, ["x" * 50_001]):
            with self.assertRaises(InferenceError):
                await adapter.embed_texts(texts)
        client.invoke_model.assert_not_called()

    async def test_embedding_order_and_bounded_concurrency(self):
        import threading
        import time

        lock = threading.Lock()
        active = peak = 0

        def invoke(**kwargs):
            nonlocal active, peak
            value = int(json.loads(kwargs["body"])["inputText"])
            with lock:
                active += 1
                peak = max(active, peak)
            time.sleep(0.01 * (4 - value % 4))
            with lock:
                active -= 1
            return {"body": io.BytesIO(json.dumps({"embedding": [value + 1] * 256}).encode())}

        client = Mock(invoke_model=invoke)
        result = await BedrockEmbeddings(self.settings, client).embed_texts([str(i) for i in range(12)])
        self.assertEqual([vector[0] for vector in result], list(range(1, 13)))
        self.assertLessEqual(peak, 4)

    def test_wrong_region_profiles_arns_and_unapproved_models_denied(self):
        with self.assertRaises(ConfigurationError):
            replace(self.settings, region="us-east-1").validate()
        for model in (
            "us.anthropic.claude-test", "apac.amazon.nova-lite-v1:0", "global.anthropic.claude-test",
            "arn:aws:bedrock:ap-south-1:123456789012:inference-profile/test", "https://external/model",
        ):
            with self.subTest(model=model):
                with self.assertRaises(ConfigurationError):
                    replace(self.settings, model_id=model, allowed_models=(model,)).validate()
        with self.assertRaises(ConfigurationError):
            replace(self.settings, allowed_models=()).validate()

    def test_sdk_endpoint_and_retry_configuration(self):
        client_factory = Mock()
        config_factory = Mock()
        with patch.dict(sys.modules, {
            "boto3": SimpleNamespace(client=client_factory),
            "botocore.config": SimpleNamespace(Config=config_factory),
        }):
            create_runtime_client()
        self.assertEqual(client_factory.call_args.kwargs["region_name"], "ap-south-1")
        self.assertEqual(client_factory.call_args.kwargs["endpoint_url"],
                         "https://bedrock-runtime.ap-south-1.amazonaws.com")
        self.assertEqual(config_factory.call_args.kwargs["retries"]["total_max_attempts"], 3)

    async def test_converse_preserves_tool_proposals_without_executing(self):
        settings = replace(self.settings, model_id="anthropic.test-model-v1:0", allowed_models=("anthropic.test-model-v1:0",))
        proposal = {"role": "assistant", "content": [{"toolUse": {
            "toolUseId": "call1", "name": "cost_get_costs", "input": {}
        }}]}
        client = Mock()
        client.converse.return_value = {"output": {"message": proposal}, "stopReason": "tool_use"}
        messages = [{"role": "user", "content": [{"text": "What did EC2 cost?"}]}]
        tools = {"tools": [{"toolSpec": {"name": "cost_get_costs"}}]}
        result = await BedrockChat(settings, client).converse(messages, system="Read-only", tool_config=tools)
        self.assertEqual(result["message"], proposal)
        self.assertEqual(result["stop_reason"], "tool_use")
        self.assertEqual(client.converse.call_args.kwargs["messages"], messages)
        self.assertEqual(client.converse.call_args.kwargs["toolConfig"], tools)
        client.invoke_model.assert_not_called()

    async def test_provider_failures_do_not_expose_content(self):
        client = Mock()
        client.invoke_model.side_effect = RuntimeError("sensitive request and provider credential")
        with self.assertRaises(InferenceError) as caught:
            await BedrockEmbeddings(self.settings, client).embed_text("query")
        self.assertNotIn("sensitive", str(caught.exception))
        self.assertTrue(caught.exception.__suppress_context__)

    def test_collection_versions_and_tenant_scope(self):
        tenant_a = "00000000-0000-0000-0000-000000000001"
        tenant_b = "00000000-0000-0000-0000-000000000002"
        a = self.settings.collection_name(tenant_a)
        self.assertTrue(a.startswith(f"rag-{tenant_a}-v1-"))
        self.assertNotEqual(a, self.settings.collection_name(tenant_b))
        self.assertNotEqual(a, replace(self.settings, dimensions=512).collection_name(tenant_a))
        self.assertNotEqual(a, f"rag-{tenant_a}")
        for invalid in ("../tenant", "tenant-a", "", None):
            with self.assertRaises(ConfigurationError):
                self.settings.collection_name(invalid)

    async def test_jev_sends_native_evaluation_request_with_restricted_egress(self):
        post = AsyncMock(return_value=self.answer())
        decision = await JevClassifier(self.jev_settings, post).classify(
            "What did account 123456789012 spend? Contact user@example.com"
        )
        self.assertEqual(decision.domain, Domain.COST)
        self.assertFalse(decision.escalate)
        key, request = post.call_args.args
        self.assertEqual(key, "test-key-not-a-real-credential")
        self.assertEqual(request["model"], JEV_MODEL)
        self.assertEqual(request["providerOptions"]["gateway"], {
            "only": ["typesafe-ai"], "zeroDataRetention": True,
        })
        self.assertEqual(request["questions"]["intent"]["type"], "choice")
        self.assertNotIn("123456789012", request["state"])
        self.assertNotIn("user@example.com", request["state"])
        self.assertEqual(set(request), {"model", "state", "questions", "providerOptions"})

    async def test_jev_http_client_uses_gateway_key_and_no_redirects(self):
        response = Mock()
        response.json.return_value = self.answer()
        client = SimpleNamespace(post=AsyncMock(return_value=response))
        context = Mock()
        context.__aenter__ = AsyncMock(return_value=client)
        context.__aexit__ = AsyncMock(return_value=False)
        factory = Mock(return_value=context)
        with patch.dict(sys.modules, {"httpx": SimpleNamespace(AsyncClient=factory)}):
            await _post("fake-key", {"state": "cost question"})
        factory.assert_called_once_with(timeout=5, follow_redirects=False, trust_env=False)
        self.assertEqual(client.post.call_args.args, (GATEWAY_URL,))
        self.assertEqual(client.post.call_args.kwargs["headers"]["Authorization"], "Bearer fake-key")
        response.raise_for_status.assert_called_once()

    async def test_disabled_jev_does_not_require_credentials_or_network(self):
        post = AsyncMock()
        classifier = JevClassifier(JevSettings(), post)
        decision = await route_request("AWS spend", classifier)
        self.assertTrue(decision.escalate)
        self.assertEqual(decision.reason, "classifier_disabled")
        post.assert_not_called()
        self.assertTrue((await route_request("AWS spend")).escalate)

    async def test_sensitive_requests_bypass_external_classifier(self):
        post = AsyncMock()
        classifier = JevClassifier(self.jev_settings, post)
        for text in ("password=unsafe-example", "Bearer fake-token", "AKIA1234567890ABCDEF", "x" * 2001):
            with self.subTest(input_kind=text[:8]):
                decision = await classifier.classify(text)
                self.assertTrue(decision.escalate)
                self.assertEqual(decision.reason, "external_input_excluded")
        post.assert_not_called()

    async def test_jev_missing_approval_or_key_escalates_without_network(self):
        post = AsyncMock()
        self.jev_policy.unlink()
        decision = await route_request("AWS spend", JevClassifier(self.jev_settings, post))
        self.assertEqual(decision.reason, "classifier_unavailable")
        post.assert_not_called()

    async def test_jev_outage_rate_limit_and_timeout_escalate(self):
        for error in (TimeoutError(), RuntimeError("429 provider secret"), RuntimeError("529 overloaded")):
            post = AsyncMock(side_effect=error)
            decision = await route_request("AWS spend", JevClassifier(self.jev_settings, post))
            self.assertTrue(decision.escalate)
            self.assertEqual(decision.reason, "classifier_unavailable")
            self.assertEqual(post.await_count, 1)

    async def test_uncertain_unknown_and_low_confidence_are_not_routes(self):
        cases = [self.answer(probability=0.6), self.answer("unknown")]
        low_confidence = self.answer()
        low_confidence["answers"]["intent"]["confidence"] = 0.2
        cases.append(low_confidence)
        for response in cases:
            post = AsyncMock(return_value=response)
            result = await JevClassifier(self.jev_settings, post).classify("AWS question")
            self.assertTrue(result.escalate)
            self.assertEqual(result.domain, Domain.UNKNOWN)

    async def test_missing_confidence_is_not_manufactured(self):
        response = self.answer()
        del response["answers"]["intent"]["confidence"]
        result = await JevClassifier(self.jev_settings, AsyncMock(return_value=response)).classify("AWS spend")
        self.assertFalse(result.escalate)
        self.assertIsNone(result.confidence)
        self.assertEqual(result.probability, 0.96)

    async def test_kubernetes_route_is_a_planning_hint(self):
        post = AsyncMock(return_value=self.answer("kubernetes"))
        result = await route_request(
            "Why are pods pending in my GKE cluster?", JevClassifier(self.jev_settings, post)
        )
        self.assertEqual(result.domain, Domain.KUBERNETES)
        self.assertFalse(result.escalate)
        self.assertIn("kubernetes", post.call_args.args[1]["questions"]["intent"]["criteria"])

    async def test_invalid_or_unexpected_gateway_answers_escalate(self):
        cases = [None, {}, {"model": "other-model"}]
        for field, value in (("choice", "delete_resource"), ("probabilities", {}),
                             ("confidence", float("nan")), ("type", "score")):
            response = self.answer()
            response["answers"]["intent"][field] = value
            cases.append(response)
        wrong_provider = self.answer()
        wrong_provider["providerMetadata"]["gateway"]["routing"]["finalProvider"] = "other"
        cases.append(wrong_provider)
        wrong_sum = self.answer()
        wrong_sum["answers"]["intent"]["probabilities"]["cost"] = 0.7
        cases.append(wrong_sum)
        for response in cases:
            result = await JevClassifier(self.jev_settings, AsyncMock(return_value=response)).classify("AWS spend")
            self.assertTrue(result.escalate)
            self.assertEqual(result.reason, "invalid_classifier_response")

    def test_chunking_terminates_and_preserves_tail(self):
        self.assertEqual(chunk_text(""), [])
        self.assertEqual(chunk_text("abc", 3, 1), ["abc"])
        self.assertEqual(chunk_text("abcdefg", 4, 1), ["abcd", "defg"])
        for size, overlap in ((0, 0), (4, 4), (4, -1)):
            with self.assertRaises(ValueError):
                chunk_text("text", size, overlap)


if __name__ == "__main__":
    unittest.main()
