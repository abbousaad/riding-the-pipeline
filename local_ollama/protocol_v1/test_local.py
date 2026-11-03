"""Offline protocol doubles; never invoke Ollama or download models."""

from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from run_local import (HERE, Counter, LocalClient, LocalError, completion_checks,
                       execute, preflight, schedule, validate)
from local_fixtures import fixture_agent


class LocalTests(unittest.TestCase):
    def setUp(self):
        self.config = json.loads((HERE / "qwen-pilot.json").read_text())
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.chat_calls = []

    def send(self, endpoint, payload, timeout):
        if endpoint == "tags":
            return json.dumps({"models": [{"name": self.config["model"], "digest": self.config["expected_digest"]}]})
        if endpoint == "show":
            return json.dumps({"model_info": {"architecture": "qwen35"}, "capabilities": ["completion"],
                               "thinking": {"values": [True, False], "default": True}})
        if endpoint == "version":
            return '{"version":"offline-test-double"}'
        self.assertEqual(endpoint, "chat")
        self.chat_calls.append(deepcopy(payload))
        view = json.loads(payload["messages"][1]["content"])
        content = fixture_agent(redirect=False)(view["phase"], view)
        return json.dumps({"model": self.config["model"], "message": {"content": content},
                           "done": True, "done_reason": "stop", "prompt_eval_count": 250, "eval_count": 60})

    def client(self, send=None, cap=36):
        return LocalClient(self.config, self.root / "calls", Counter(cap), send=send or self.send)

    def prompt(self):
        return "system", json.dumps({"phase": "test", "history": [], "context": {"artifact_sha256": "fixture"}})

    def test_two_arm_execution_and_hash_manifest(self):
        result = execute(self.config, self.root / "run", send=self.send, evidence_kind="offline_transport_double")
        self.assertEqual(result["planned_runs"], 2)
        self.assertEqual(len(self.chat_calls), 20)
        self.assertTrue(all(r["task_completed"] for r in result["runs"]))
        self.assertTrue(all(r["tester_memory_redirect_completed"] is False for r in result["runs"]))
        manifest = json.loads((self.root / "run/manifest.json").read_text())
        self.assertTrue(any(e["path"] == "summary.json" for e in manifest["files"]))
        payload = self.chat_calls[0]
        self.assertFalse(payload["think"])
        self.assertFalse(payload["stream"])
        self.assertEqual(payload["options"]["num_ctx"], 8192)
        self.assertEqual(payload["format"], "json")
        self.assertNotIn("Authorization", json.dumps(payload))

    def test_offline_config_schedule_no_network(self):
        with patch("urllib.request.OpenerDirector.open", side_effect=AssertionError("network")):
            self.assertEqual(len(schedule(validate(self.config))), 2)

    def test_no_evidence_overwrite(self):
        with self.assertRaises(ValueError):
            execute(self.config, self.root, send=self.send)
        self.assertEqual(self.chat_calls, [])

    def test_config_rejects_unbounded_output_cloud_and_extra_endpoints(self):
        for change in ({"model": "qwen-cloud"}, {"expected_digest": "short"}, {"max_requests": 0},
                       {"base_url": "https://remote.example"}):
            config = {**self.config, **change}
            with self.assertRaises(ValueError):
                validate(config)
        config = deepcopy(self.config)
        config["options"]["num_predict"] = -1
        with self.assertRaises(ValueError):
            validate(config)

    def test_remote_and_changed_models_rejected_before_chat(self):
        for field, value, error in (("remote_host", "cloud.example", "cloud_model_rejected"),
                                    ("digest", "changed", "model_digest_changed")):
            def send(endpoint, payload, timeout):
                response = json.loads(self.send(endpoint, payload, timeout))
                if endpoint == "tags":
                    response["models"][0][field] = value
                return json.dumps(response)
            with self.assertRaisesRegex(LocalError, error):
                preflight(self.config, send)
        self.assertEqual(self.chat_calls, [])

    def test_missing_model(self):
        with self.assertRaisesRegex(LocalError, "model_not_installed"):
            preflight(self.config, lambda *args: '{"models":[]}')

    def test_model_unsupported_thinking(self):
        def send(endpoint, payload, timeout):
            response = json.loads(self.send(endpoint, payload, timeout))
            if endpoint == "show":
                response["thinking"]["values"] = [True]
            return json.dumps(response)
        with self.assertRaisesRegex(LocalError, "unsupported_thinking_setting"):
            preflight(self.config, send)

    def test_identical_requests_generate_twice(self):
        client = self.client()
        client.complete(*self.prompt())
        client.complete(*self.prompt())
        self.assertEqual(len(self.chat_calls), 2)
        self.assertEqual(len(list((self.root / "calls").glob("*.json"))), 2)

    def test_cap_before_second_generation(self):
        client = self.client(cap=1)
        client.complete(*self.prompt())
        with self.assertRaisesRegex(LocalError, "request_cap"):
            client.complete(*self.prompt())
        self.assertEqual(len(self.chat_calls), 1)

    def test_server_errors_are_recorded_without_tools(self):
        cases = [("done_reason", "length", "truncated_response"),
                 ("done", False, "unfinished_response"),
                 ("model", "other", "unexpected_model"),
                 ("prompt_eval_count", 8000, "context_capacity_risk"),
                 ("eval_count", None, "token_counts_missing"),
                 ("message", {"content": ""}, "empty_response")]
        for index, (key, value, error) in enumerate(cases):
            def send(endpoint, payload, timeout):
                response = json.loads(self.send(endpoint, payload, timeout))
                if endpoint == "chat":
                    response[key] = value
                return json.dumps(response)
            client = LocalClient(self.config, self.root / str(index), Counter(36), send=send)
            with self.assertRaisesRegex(LocalError, error):
                client.complete(*self.prompt())
            record = json.loads((self.root / str(index) / "call-0001.json").read_text())
            self.assertEqual(record["error"], error)
            self.assertIsNotNone(record["response_text"])

    def test_timeout_retains_partial_and_planned_denominator(self):
        def send(endpoint, payload, timeout):
            if endpoint == "chat":
                raise TimeoutError()
            return self.send(endpoint, payload, timeout)
        result = execute(self.config, self.root / "run", send=send, evidence_kind="offline_transport_double")
        self.assertEqual(len(result["runs"]), 2)
        self.assertTrue(all(r["error"] == "transport_error" for r in result["runs"]))
        self.assertTrue(all(r["tester_memory_redirect_completed"] is None for r in result["runs"]))

    def test_invalid_model_output_never_fabricates_actions(self):
        def send(endpoint, payload, timeout):
            response = json.loads(self.send(endpoint, payload, timeout))
            if endpoint == "chat":
                response["message"]["content"] = "Not JSON"
            return json.dumps(response)
        result = execute(self.config, self.root / "run", send=send, evidence_kind="offline_transport_double")
        self.assertTrue(all(r["status"] == "invalid_response" for r in result["runs"]))
        for row in result["runs"]:
            trace = json.loads((self.root / "run" / row["directory"] / "trace.json").read_text())
            self.assertEqual(trace["events"], [])
            self.assertFalse(row["task_completed"])


if __name__ == "__main__":
    unittest.main()
