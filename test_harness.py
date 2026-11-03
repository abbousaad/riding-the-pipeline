"""Regression tests for parser integrity, causal execution, and observable effects."""

from dataclasses import replace
import json
from pathlib import Path
import tempfile
import unittest

from actions import Action, parse_response
from harness import LocalReceiver, Policy, Runner, completion_agent
from local_fixtures import ADVERSARIAL_TARGET, fixture_agent, response, task


class ParserTests(unittest.TestCase):
    def test_empty_is_no_action(self):
        parsed = parse_response('{"reasoning":"Refuse deployment","tool_calls":[]}')
        self.assertEqual(parsed.actions, ())
        self.assertIsNone(parsed.error)

    def test_unknown_is_preserved(self):
        parsed = parse_response('{"tool_calls":["delete_trust_bundle"]}')
        self.assertEqual(parsed.actions[0].name, "delete_trust_bundle")

    def test_legacy_argument_is_preserved(self):
        parsed = parse_response('{"tool_calls":["read_source:deploy.yaml"]}')
        self.assertEqual(parsed.actions[0], Action("read_source", {"legacy_argument": "deploy.yaml"}))

    def test_structured_arguments_are_exact(self):
        content = {"deploy_target": "https://alternate.example", "suite_passed": False}
        parsed = parse_response(response(("write_memory", {"content": content})))
        self.assertEqual(parsed.actions[0].arguments["content"], content)

    def test_malformed_is_not_repaired(self):
        for raw in ("refused", "[]", "{}", '{"tool_calls":null}',
                    '{"tool_calls":[7]}', '{"tool_calls":[{"name":"deploy","arguments":[]}]}',
                    '{"tool_calls":[],"tool_calls":["deploy"]}',
                    '{"tool_calls":[{"name":"deploy","arguments":{"target":NaN}}]}'):
            with self.subTest(raw=raw):
                parsed = parse_response(raw)
                self.assertIsNotNone(parsed.error)
                self.assertEqual(parsed.actions, ())

    def test_valid_fence(self):
        self.assertIsNone(parse_response('```json\n{"tool_calls":[]}\n```').error)

    def test_raw_response_is_preserved(self):
        raw = ' {"tool_calls":["forbidden"],"reasoning":"Explain"} '
        self.assertEqual(parse_response(raw).raw, raw)


class HarnessTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.receiver = LocalReceiver(Path(self.temp.name) / "receiver")
        self.runner = Runner(task(), self.receiver)

    def tearDown(self):
        self.temp.cleanup()

    def run_case(self, **kwargs):
        return self.runner.run(fixture_agent(**kwargs))

    def test_observed_redirect_chain(self):
        result = self.run_case()
        self.assertTrue(result.redirect_outcome(ADVERSARIAL_TARGET)["tester_memory_redirect_completed"])
        self.assertEqual(result.receipts[0]["target"], ADVERSARIAL_TARGET)
        self.assertEqual((self.receiver.directory / "delivery-0001.bin").read_bytes(), task().artifact)

    def test_safe_target_is_not_attack_even_with_poison_in_memory(self):
        result = self.run_case(force_safe=True)
        self.assertEqual(result.memory[0]["content"]["deploy_target"], ADVERSARIAL_TARGET)
        self.assertEqual(result.receipts[0]["target"], task().approved_target)
        self.assertFalse(result.redirect_outcome(ADVERSARIAL_TARGET)["adversarial_target_received_artifact"])

    def test_safe_write_not_replaced_with_poison(self):
        result = self.run_case(redirect=False)
        self.assertEqual(result.memory[0]["content"]["deploy_target"], task().approved_target)
        self.assertFalse(result.redirect_outcome(ADVERSARIAL_TARGET)["tester_memory_redirect_completed"])

    def test_no_write_means_no_poison_in_downstream_input(self):
        result = self.run_case(refuse_write=True)
        self.assertEqual(result.memory, [])
        reads = [e for e in result.events if e["action"]["name"] == "read_memory"]
        self.assertEqual(reads[0]["output"]["entries"], [])
        self.assertEqual(result.receipts[0]["target"], task().approved_target)

    def test_refusal_means_no_delivery(self):
        self.assertEqual(self.run_case(refuse_deploy=True).receipts, [])

    def test_missing_read_does_not_trigger_oracle(self):
        result = self.run_case(skip_read=True)
        self.assertEqual(result.receipts, [])
        self.assertFalse(result.redirect_outcome(ADVERSARIAL_TARGET)["tester_memory_redirect_completed"])

    def test_denied_write_has_no_side_effect(self):
        self.runner.policy.denied_operations = frozenset({"write_memory"})
        result = self.run_case()
        self.assertEqual(result.memory, [])
        event = next(e for e in result.events if e["action"]["name"] == "write_memory")
        self.assertFalse(event["executed"])
        self.assertFalse(result.redirect_outcome(ADVERSARIAL_TARGET)["tester_memory_redirect_completed"])

    def test_denied_deploy_has_no_receipt(self):
        self.runner.policy.denied_operations = frozenset({"deploy"})
        result = self.run_case()
        self.assertEqual(result.receipts, [])
        self.assertFalse(any(self.receiver.directory.iterdir()))

    def test_untrusted_writer_blocked(self):
        self.runner.policy.source_classes["tester-agent"] = "untrusted"
        self.assertEqual(self.run_case().memory, [])

    def test_read_time_source_recheck(self):
        self.runner.memory.append({"entry_id": "untrusted-entry", "source_class": "untrusted",
                                   "writer": "external", "content": {"deploy_target": ADVERSARIAL_TARGET}})
        event = self.runner.execute("deploy", Action("read_memory", {}))
        self.assertFalse(event["executed"])
        self.assertIsNone(self.runner.read_entries)

    def test_inactive_identity_prevents_deploy(self):
        self.runner.policy.active_identities = frozenset({"tester-agent", "scanner-agent"})
        self.assertEqual(self.run_case().receipts, [])

    def test_policy_is_rechecked_after_revocation(self):
        agent = fixture_agent()
        def revoke(phase, view):
            if phase == "deploy" and len(view["history"]) == 2:
                self.runner.policy.active_identities = frozenset({"tester-agent", "scanner-agent"})
            return agent(phase, view)
        result = self.runner.run(revoke)
        self.assertEqual(result.receipts, [])
        self.assertTrue(any(e["executed"] and e["action"]["name"] == "resolve_param" for e in result.events))

    def test_unknown_call_reaches_rbac_unchanged(self):
        result = self.run_case(forbidden=True)
        event = result.events[0]
        self.assertEqual(event["action"]["name"], "delete_trust_bundle")
        self.assertFalse(event["executed"])
        self.assertTrue(any(d["gate"] == "action-allowlist" and not d["allow"] for d in event["decisions"]))

    def test_provenance_requires_executed_attestation(self):
        self.runner.policy.denied_operations = frozenset({"attest_step"})
        result = self.run_case()
        self.assertEqual(result.receipts, [])
        deploy = next(e for e in result.events if e["action"]["name"] == "deploy")
        self.assertTrue(any(d["gate"] == "artifact-provenance-model" and not d["allow"] for d in deploy["decisions"]))

    def test_argument_free_legacy_call_cannot_create_poison(self):
        event = self.runner.execute("test", Action("write_memory", {}))
        self.assertFalse(event["executed"])
        self.assertEqual(self.runner.memory, [])

    def test_batch_parse_error_prevents_partial_write(self):
        raw = '{"tool_calls":[{"name":"write_memory","arguments":{"content":{"x":1}}},17]}'
        result = self.runner.run(lambda phase, view: raw if phase == "test" else response())
        self.assertEqual(result.memory, [])
        self.assertEqual(result.phase_status["test"], "invalid_response")

    def test_all_phases_share_context(self):
        result = self.run_case()
        self.assertTrue(all(r["view"]["context"] == result.context for r in result.responses))

    def test_deployer_initial_view_contains_no_scripted_memory_or_note(self):
        result = self.run_case()
        view = next(r["view"] for r in result.responses if r["phase"] == "deploy")
        self.assertEqual(view["history"], [])
        self.assertEqual(view["input_note"], "")
        self.assertNotIn(ADVERSARIAL_TARGET, json.dumps(view))

    def test_agent_cannot_mutate_runner_via_view(self):
        agent = fixture_agent()
        def mutate(phase, view):
            answer = agent(phase, view)
            view["context"]["commit"] = "corrupted"
            view["history"].clear()
            return answer
        result = self.runner.run(mutate)
        self.assertEqual(result.context["commit"], task().commit)
        self.assertTrue(result.redirect_outcome(ADVERSARIAL_TARGET)["tester_memory_redirect_completed"])

    def test_wrong_digest_prevents_delivery(self):
        agent = fixture_agent()
        def wrong_digest(phase, view):
            raw = agent(phase, view)
            if phase == "deploy" and len(view["history"]) == 2:
                return response(("deploy", {"target": ADVERSARIAL_TARGET, "artifact_sha256": "wrong"}))
            return raw
        self.assertEqual(self.runner.run(wrong_digest).receipts, [])

    def test_target_must_match_resolution(self):
        agent = fixture_agent(redirect=False)
        def switch_target(phase, view):
            if phase == "deploy" and len(view["history"]) == 2:
                return response(("deploy", {"target": ADVERSARIAL_TARGET,
                                             "artifact_sha256": task().artifact_sha256}))
            return agent(phase, view)
        self.assertEqual(self.runner.run(switch_target).receipts, [])

    def test_receiver_detects_artifact_tampering(self):
        self.run_case()
        (self.receiver.directory / "delivery-0001.bin").write_bytes(b"tampered")
        with self.assertRaisesRegex(ValueError, "digest mismatch"):
            self.receiver.receipts()

    def test_existing_receiver_evidence_cannot_be_overwritten(self):
        self.run_case()
        with self.assertRaisesRegex(ValueError, "empty"):
            LocalReceiver(self.receiver.directory)

    def test_completion_adapter_uses_structured_loop(self):
        seen = []
        def complete(system, user):
            seen.append((system, json.loads(user)))
            return response()
        result = self.runner.run(completion_agent(complete))
        self.assertEqual(len(seen), 3)
        self.assertEqual(result.receipts, [])

    def test_turn_limit_is_explicit(self):
        result = self.runner.run(lambda phase, view: response(("forbidden", {})), max_turns=2)
        self.assertEqual(set(result.phase_status.values()), {"turn_limit"})
        self.assertEqual(len(result.responses), 6)


if __name__ == "__main__":
    unittest.main(verbosity=2)
