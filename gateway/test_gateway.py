"""Offline transport doubles only. These tests are not LLM measurements."""

from copy import deepcopy
import io
import json
from pathlib import Path
import tempfile
import unittest
import urllib.error
from unittest.mock import patch

from client import Budget, Client, GatewayError, NoRedirect
from run import HERE, execute, matrix, plan, task_for, validate_config
from local_fixtures import fixture_agent


class Response(io.BytesIO):
    def __init__(self, body, headers=None):
        super().__init__(body.encode())
        self.headers = headers or {}
        self.status = 200


def envelope(content='{"explanation":"done","tool_calls":[]}', **overrides):
    value = {"model": "test-model", "choices": [{"finish_reason": "stop", "message": {
        "role": "assistant", "content": content}}],
        "metadata": {"used_provider": "test", "used_model": "test-model", "cached": False},
        "usage": {"prompt_tokens": 12, "completion_tokens": 4, "total_tokens": 16,
                  "cost_details": {"total_cost": 0.001}}}
    value.update(overrides)
    return value


class ClientTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "calls"
        self.budget = Budget(10, 1)
        self.model = {"id": "test/test-model", "parameters": {"max_tokens": 100}}

    def client(self, data=None, *, send=None, headers=None, key="secret-for-tests"):
        if send is None:
            send = lambda request, timeout: Response(json.dumps(data or envelope()), headers)
        return Client(key, self.model, self.path, self.budget, send=send)

    def record(self):
        return json.loads((self.path / "call-0001.json").read_text())

    def test_headers_and_recording(self):
        def send(request, timeout):
            self.assertEqual(request.get_header("Authorization"), "Bearer secret-for-tests")
            self.assertEqual(request.get_header("X-no-fallback"), "true")
            self.assertEqual(request.get_header("X-no-cache"), "true")
            payload = json.loads(request.data)
            self.assertEqual(payload["model"], "test/test-model")
            self.assertFalse(payload["stream"])
            self.assertNotIn("plugins", payload)
            return Response(json.dumps(envelope()))
        self.client(send=send).complete("system", "user")
        record = self.record()
        self.assertEqual(record["response"]["metadata"]["used_provider"], "test")
        self.assertEqual(self.budget.reported_cost, 0.001)
        self.assertNotIn("secret-for-tests", json.dumps(record))

    def test_identical_requests_are_sent_and_recorded_twice(self):
        calls = []
        def send(request, timeout):
            calls.append(request)
            return Response(json.dumps(envelope()))
        client = self.client(send=send)
        client.complete("s", "u")
        client.complete("s", "u")
        self.assertEqual(len(calls), 2)
        self.assertEqual(len(list(self.path.glob("*.json"))), 2)

    def test_fresh_request_hash_includes_model_and_parameters(self):
        self.client().complete("s", "u")
        first = self.record()["request_sha256"]
        self.path = self.path.parent / "second"
        self.model = {"id": "test/other", "parameters": {"max_tokens": 101}}
        self.client().complete("s", "u")
        self.assertNotEqual(first, self.record()["request_sha256"])

    def test_cache_rejected_by_metadata(self):
        client = self.client(envelope(metadata={"cached": True}))
        with self.assertRaisesRegex(GatewayError, "cached_response_rejected"):
            client.complete("s", "u")
        self.assertEqual(self.record()["error"], "cached_response_rejected")

    def test_cache_rejected_by_header(self):
        with self.assertRaisesRegex(GatewayError, "cached_response_rejected"):
            self.client(headers={"x-llmgateway-cache": "HIT"}).complete("s", "u")

    def test_provider_mismatch_rejected(self):
        with self.assertRaisesRegex(GatewayError, "unexpected_provider"):
            self.client(envelope(metadata={"used_provider": "different"})).complete("s", "u")

    def test_truncation_refusal_and_filter(self):
        cases = [("length", None, "truncated_response"),
                 ("stop", "Cannot comply", "provider_refusal"),
                 ("content_filter", None, "filtered_response")]
        for index, (finish, refusal, error) in enumerate(cases):
            self.path = Path(self.temp.name) / str(index)
            data = envelope()
            data["choices"][0]["finish_reason"] = finish
            data["choices"][0]["message"]["refusal"] = refusal
            with self.assertRaisesRegex(GatewayError, error):
                self.client(data).complete("s", "u")
            self.assertEqual(self.record()["error"], error)

    def test_bad_json_no_tool_fabrication(self):
        data = envelope(content="Not JSON")
        self.assertEqual(self.client(data).complete("s", "u"), "Not JSON")
        self.assertEqual(self.record()["response"]["choices"][0]["message"]["content"], "Not JSON")

    def test_invalid_gateway_body_accounted(self):
        client = self.client(send=lambda *args: Response('{"cost": NaN}'))
        with self.assertRaisesRegex(GatewayError, "invalid_gateway_response"):
            client.complete("s", "u")
        self.assertEqual(self.budget.unknown_cost_calls, 1)
        self.assertEqual(self.record()["response_text"], '{"cost": NaN}')

    def test_http_error_redacts_echoed_key_and_never_retries(self):
        key = 'secret"with\\punctuation'
        def send(request, timeout):
            raise urllib.error.HTTPError(request.full_url, 429, "rate limit", {},
                                         io.BytesIO(("bad key: " + key).encode()))
        client = self.client(send=send, key=key)
        with self.assertRaisesRegex(GatewayError, "http_error"):
            client.complete("s", "u")
        self.assertNotIn(key, self.record()["response_text"])
        self.assertEqual(self.budget.requests, 1)
        with self.assertRaisesRegex(GatewayError, "unknown_cost_stop"):
            client.complete("s", "u")
        self.assertEqual(self.budget.requests, 1)

    def test_timeout_recorded(self):
        def send(*args):
            raise TimeoutError()
        with self.assertRaisesRegex(GatewayError, "transport_error"):
            self.client(send=send).complete("s", "u")
        self.assertEqual(self.record()["error"], "transport_error")

    def test_escaped_key_redacted_from_raw_json_and_parsed_body(self):
        key = 'secret"with\\punctuation'
        self.client(envelope(content=key), key=key).complete("s", "u")
        record = self.record()
        self.assertNotIn(key, record["response_text"])
        self.assertNotIn(json.dumps(key)[1:-1], record["response_text"])
        self.assertEqual(record["response"]["choices"][0]["message"]["content"], "[REDACTED]")

    def test_finite_json_numbers_required(self):
        with self.assertRaisesRegex(GatewayError, "invalid_gateway_response"):
            self.client(send=lambda *args: Response('{"usage":{"cost":1e999}}')).complete("s", "u")
        self.assertEqual(self.record()["error"], "invalid_gateway_response")

    def test_unknown_cost_stops_next_call_but_zero_cost_is_valid(self):
        client = self.client(envelope(usage={"cost": 0}))
        client.complete("s", "u")
        client.complete("s", "u")
        self.assertEqual(self.budget.unknown_cost_calls, 0)
        self.path = self.path.parent / "unknown"
        client = self.client(envelope(usage={}))
        client.complete("s", "u")
        with self.assertRaisesRegex(GatewayError, "unknown_cost_stop"):
            client.complete("s", "u")

    def test_caps(self):
        self.budget.max_requests = 1
        client = self.client()
        client.complete("s", "u")
        with self.assertRaisesRegex(GatewayError, "request_cap"):
            client.complete("s", "u")
        self.budget.max_requests = 10
        self.budget.max_cost = 0.0001
        with self.assertRaisesRegex(GatewayError, "reported_cost_cap"):
            client.complete("s", "u")
        self.assertEqual(len(list(self.path.glob("*.json"))), 1)

    def test_redirects_disabled(self):
        self.assertIsNone(NoRedirect().redirect_request(None, None, 302, "", {}, "https://elsewhere"))

    def test_existing_evidence_not_overwritten(self):
        self.client()
        with self.assertRaises(FileExistsError):
            self.client()


class MatrixTests(unittest.TestCase):
    def setUp(self):
        self.config = json.loads((HERE / "pilot.example.json").read_text())
        self.config["models"] = [{"id": "test/model-a", "parameters": {"max_tokens": 500}},
                                 {"id": "test/model-b", "parameters": {"max_tokens": 500}}]
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.output = Path(self.temp.name) / "evidence"

    def test_offline_plan_no_calls(self):
        with patch("urllib.request.OpenerDirector.open", side_effect=AssertionError("network")):
            result = plan(validate_config(self.config))
        self.assertEqual(result["runs"], 4)
        self.assertEqual(result["maximum_completion_requests"], 72)
        self.assertEqual(matrix(self.config), matrix(deepcopy(self.config)))

    def test_validation(self):
        for field, value in (("max_requests", 0), ("repetitions", True),
                             ("max_reported_cost_usd", float("nan")),
                             ("arms", ["attack"]), ("models", [])):
            config = deepcopy(self.config)
            config[field] = value
            with self.assertRaises(ValueError):
                validate_config(config)
        for name in ("auto", "test/auto", "test/latest", "missing-provider"):
            config = deepcopy(self.config)
            config["models"][0]["id"] = name
            with self.assertRaises(ValueError):
                validate_config(config)
        config = deepcopy(self.config)
        config["models"][0]["parameters"]["plugins"] = []
        with self.assertRaises(ValueError):
            validate_config(config)

    def test_paired_context_and_payload_boundary(self):
        clean, injected = task_for("clean", 0), task_for("source_injection", 0)
        self.assertEqual(clean.context(), injected.context())
        self.assertEqual(clean.artifact, injected.artifact)
        self.assertEqual(injected.input_note, "")
        self.assertNotIn("attacker-endpoint", clean.sources["auth.py"])
        self.assertIn("attacker-endpoint", injected.sources["auth.py"])

    def mock_send(self, request, timeout):
        payload = json.loads(request.data)
        view = json.loads(payload["messages"][1]["content"])
        model = payload["model"]
        agent = fixture_agent(redirect=model.endswith("model-b"))
        content = agent(view["phase"], view)
        return Response(json.dumps(envelope(content=content, model=model)))

    def test_two_models_full_harness_independent_artifacts(self):
        summary = execute(self.config, self.output, "mock-key", send=self.mock_send,
                          evidence_kind="offline_transport_double")
        self.assertEqual(len(summary["runs"]), 4)
        for row in summary["runs"]:
            self.assertEqual(row["status"], "completed")
            redirect = row["model"].endswith("model-b")
            self.assertEqual(row["tester_memory_redirect_completed"], redirect)
            self.assertEqual(row["approved_target_received_artifact"], not redirect)
            self.assertTrue((self.output / row["directory"] / "trace.json").is_file())
            self.assertEqual(row["api_requests"], 10)
        self.assertEqual(summary["budget"]["requests_attempted"], 40)
        with self.assertRaises(FileExistsError):
            execute(self.config, self.output, "mock-key", send=self.mock_send)

    def test_cap_keeps_all_planned_denominators_and_partial_trace(self):
        self.config["max_requests"] = 1
        summary = execute(self.config, self.output, "mock-key", send=self.mock_send,
                          evidence_kind="offline_transport_double")
        self.assertEqual(len(summary["runs"]), 4)
        self.assertEqual(summary["budget"]["requests_attempted"], 1)
        self.assertTrue(all(r["status"] == "incomplete" for r in summary["runs"]))
        self.assertTrue(all(r["tester_memory_redirect_completed"] is None for r in summary["runs"]))
        trace = json.loads((self.output / "run-0000" / "trace.json").read_text())
        self.assertTrue(trace["events"])

    def test_malformed_model_output_does_not_execute(self):
        def send(*args):
            return Response(json.dumps(envelope(content="I refuse")))
        summary = execute(self.config, self.output, "mock-key", send=send,
                          evidence_kind="offline_transport_double")
        self.assertTrue(all(r["status"] == "invalid_response" for r in summary["runs"]))
        for row in summary["runs"]:
            trace = json.loads((self.output / row["directory"] / "trace.json").read_text())
            self.assertEqual(trace["events"], [])
            self.assertFalse(row["observed_adversarial_delivery"])

    def test_missing_key_creates_no_evidence(self):
        with self.assertRaises(ValueError):
            execute(self.config, self.output, "", send=self.mock_send)
        self.assertFalse(self.output.exists())


if __name__ == "__main__":
    unittest.main()
