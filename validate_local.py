"""Record deterministic intervention checks with actual local receiver evidence."""

import argparse
from dataclasses import asdict
import json
from pathlib import Path

from harness import LocalReceiver, Policy, Runner, VERSION
from local_fixtures import ADVERSARIAL_TARGET, fixture_agent, task

HERE = Path(__file__).resolve().parent


def validate(output):
    output.mkdir(parents=True, exist_ok=True)
    if any(output.iterdir()):
        raise SystemExit("Output must be empty; choose a new directory to preserve previous validation.")
    scenarios = [
        ("redirect", {}, {}, True),
        ("safe_write", {"redirect": False}, {}, False),
        ("refuse_write", {"refuse_write": True}, {}, False),
        ("refuse_deploy", {"refuse_deploy": True}, {}, False),
        ("safe_target_with_poison_present", {"force_safe": True}, {}, False),
        ("missing_read", {"skip_read": True}, {}, False),
        ("deny_write", {}, {"denied_operations": frozenset({"write_memory"})}, False),
        ("deny_deploy", {}, {"denied_operations": frozenset({"deploy"})}, False),
        ("deny_attestation", {}, {"denied_operations": frozenset({"attest_step"})}, False),
        ("unknown_action", {"forbidden": True}, {}, False),
    ]
    cases = []
    for name, agent_args, policy_args, expected in scenarios:
        receiver = LocalReceiver(output / name / "receiver")
        result = Runner(task(), receiver, Policy(**policy_args)).run(fixture_agent(**agent_args))
        outcome = result.redirect_outcome(ADVERSARIAL_TARGET)
        if outcome["tester_memory_redirect_completed"] != expected:
            raise AssertionError(name)
        data = {"kind": "deterministic_local_validation_not_model_measurement", "harness": VERSION,
                "scenario": name, "expected_redirect": expected, "outcome": outcome, "run": asdict(result)}
        (output / name / "trace.json").write_text(json.dumps(data, indent=2) + "\n")
        cases.append({"scenario": name, **outcome, "expected_redirect": expected,
                      "denied_or_invalid_operations": sum(not e["executed"] for e in result.events)})
    summary = {"harness": VERSION, "kind": "deterministic local regression validation",
               "fresh_model_runs": 0, "external_deployments": 0, "cases": cases}
    (output / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=HERE / "results" / "local_validation")
    validate(parser.parse_args().output)
