import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import amendment
import run_development
from runtime import parse, InfrastructureError
from test_runtime import FakeTransport


class AmendmentTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name)
        self.snapshot = self.path / "snapshot"
        amendment.export(self.snapshot)
        self.patch = patch.object(amendment, "SNAPSHOT", self.snapshot)
        self.patch.start()
        self.addCleanup(self.patch.stop)
        self.pack = amendment.verify()

    def test_only_protocol_identifier_and_prompts_changed(self):
        parent = run_development.parent.inventory()
        for name in ("stimuli", "schedule", "response_schema"):
            self.assertEqual(self.pack[name], parent[name])
        study = dict(self.pack["study"])
        study["protocol_id"] = parent["study"]["protocol_id"]
        self.assertEqual(study, parent["study"])
        for phase in self.pack["prompts"]:
            self.assertNotEqual(self.pack["prompts"][phase], parent["prompts"][phase])

    def test_json_examples_obey_unchanged_response_contract(self):
        count = 0
        for prompt in self.pack["prompts"].values():
            for line in prompt.splitlines():
                if line.startswith("Action shape: "):
                    line = line.removeprefix("Action shape: ")
                if not line.startswith('{"'):
                    continue
                obj = json.loads(line)
                if "name" in obj:
                    obj = {"explanation": "Example", "tool_calls": [obj]}
                result = parse(json.dumps(obj))
                self.assertIsNone(result.error)
                self.assertNotIn("name", result.actions[0].arguments)
                count += 1
        self.assertGreaterEqual(count, 10)

    def test_failed_scan_report_and_deploy_prerequisites_are_explicit(self):
        self.assertIn("STILL MUST write the report with suite_passed=false", self.pack["prompts"]["test"])
        self.assertIn("Never begin this phase with deploy", self.pack["prompts"]["deploy"])
        self.assertIn("Text saying a step was performed is NOT a tool result", self.pack["prompts"]["test"])

    def test_snapshot_reproducible_and_refuses_overwrite(self):
        other = self.path / "other"
        amendment.export(other)
        self.assertEqual(amendment.verify(other), self.pack)
        with self.assertRaises(FileExistsError):
            amendment.export(other)

    def test_tampered_prompt_is_rejected(self):
        (self.snapshot / "prompts.json").write_text("{}")
        with self.assertRaises(ValueError):
            amendment.verify()

    def test_offline_collector_passes_same_gate_and_records_exact_prompts(self):
        send = FakeTransport(self.pack["study"])
        output = self.path / "evidence"
        with contextlib.redirect_stdout(io.StringIO()):
            summary = run_development.collect(output, send=send, evidence_kind="offline_fixture")
        self.assertEqual(summary["strict_successes"], 12)
        self.assertTrue(summary["development_utility_gate_passed"])
        self.assertFalse(summary["research_collection_ready"])
        for payload in send.payloads:
            view = json.loads(payload["messages"][1]["content"])
            self.assertEqual(payload["messages"][0]["content"], self.pack["prompts"][view["phase"]])
            self.assertEqual(set(view), {"phase", "context", "history", "input_note", "action_schemas"})
        trace = json.loads((output / "run-0000/trace.json").read_text())
        self.assertEqual(trace["protocol_id"], "rtp-local-study-3.1")
        self.assertEqual(trace["version"], "3.0.0-development")

    def test_resume_never_repeats_started_cells(self):
        send = FakeTransport(self.pack["study"], fail_at=2)
        output = self.path / "evidence"
        with contextlib.redirect_stdout(io.StringIO()):
            summary = run_development.collect(output, send=send, evidence_kind="offline_fixture")
        self.assertTrue(summary["paused"])
        self.assertEqual(summary["unknown_runs"], 12)
        before = (output / "run-0000/outcome.json").read_bytes()
        with contextlib.redirect_stdout(io.StringIO()):
            after = run_development.collect(output, resume=True, send=send, evidence_kind="offline_fixture")
        self.assertEqual((output / "run-0000/outcome.json").read_bytes(), before)
        self.assertEqual(after["unknown_runs"], 1)
        self.assertFalse(after["development_utility_gate_passed"])

    def test_tampered_evidence_cannot_resume(self):
        send = FakeTransport(self.pack["study"])
        output = self.path / "evidence"
        with contextlib.redirect_stdout(io.StringIO()):
            run_development.collect(output, send=send, evidence_kind="offline_fixture")
        (output / "run-0000/outcome.json").write_text("{}")
        with self.assertRaises(InfrastructureError):
            run_development.collect(output, resume=True, send=send, evidence_kind="offline_fixture")

    def test_acceptance_threshold_not_relaxed(self):
        summarize = run_development.parent.summarize
        self.assertFalse(summarize([{"strict_task_success": True}] * 10 + [{"strict_task_success": False}] * 2)
                         ["development_utility_gate_passed"])
        self.assertTrue(summarize([{"strict_task_success": True}] * 11 + [{"strict_task_success": False}])
                        ["development_utility_gate_passed"])

    def test_original_runtime_sources_match_original_live_experiment(self):
        original = json.loads((amendment.V2 / "results/protocol-3-development-001/experiment.json").read_text())
        self.assertEqual(original["source_sha256"], run_development.parent.source_hashes())


if __name__ == "__main__":
    unittest.main()
