"""Audit the amended batch and all retained earlier evidence without model calls."""

import argparse
from collections import Counter
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import sys

HERE = Path(__file__).resolve().parent
V2 = HERE.parent
sys.path.insert(0, str(V2 / "protocol_3_1"))
import amendment
import run_development
from runtime import outcomes
sys.path.insert(0, str(V2 / "development_review_2026-09-25"))
import audit as old_audit


def verify(directory):
    if (directory / "collection.lock").exists():
        raise ValueError("collection must finish before audit")
    pack = amendment.verify()
    experiment = json.loads((directory / "experiment.json").read_text())
    if (experiment["protocol_id"] != amendment.PROTOCOL_ID or experiment["study"] != pack["study"] or
            experiment["snapshot_manifest_sha256"] != run_development.parent.digest(amendment.SNAPSHOT / "manifest.json")):
        raise ValueError("experiment identity or frozen settings mismatch")
    if experiment["source_sha256"] != run_development.source_hashes():
        raise ValueError("runtime source mismatch")
    if experiment["prompts"] != pack["prompts"] or experiment["response_schema"] != pack["response_schema"]:
        raise ValueError("experiment prompt/schema mismatch")
    rows, calls, diagnoses, verified_files = [], [], [], 0
    expected_rows = [r for r in pack["schedule"] if r["split"] == "development"]
    if experiment["schedule"] != expected_rows:
        raise ValueError("schedule mismatch")
    for row in expected_rows:
        root = directory / row["run_id"]
        run_development.parent.verify_seal(root)
        verified_files += len(json.loads((root / "manifest.json").read_text())["files"])
        trace = json.loads((root / "trace.json").read_text())
        result = json.loads((root / "outcome.json").read_text())
        stimulus = pack["stimuli"][row["stimulus_id"]]
        if json.loads((root / "stimulus.json").read_text()) != stimulus:
            raise ValueError("stimulus mismatch")
        computed = outcomes(stimulus, trace, row["family"] + ".py")
        if any(result[k] != v for k, v in {**row, **computed}.items()):
            raise ValueError("outcome recomputation mismatch")
        for path in sorted((root / "calls").glob("call-*.json")):
            call = json.loads(path.read_text())
            generator = pack["study"]["generator"]
            if (call["request"]["messages"][0]["content"] != pack["prompts"][call["phase"]] or
                    call["request"]["format"] != pack["response_schema"] or
                    call["request"]["model"] != generator["model"] or
                    call["expected_digest"] != generator["digest"] or
                    call["endpoint"] != generator["endpoint"] or
                    call["request"]["think"] != generator["think"] or
                    call["request"]["options"] != {k: generator[k] for k in ("temperature", "seed", "num_ctx", "num_predict")}):
                raise ValueError("actual call differs from frozen prompt/schema")
            calls.append(call)
        rows.append(result)
        diagnoses.append({"run_id": row["run_id"], "family": row["family"], "arm": row["arm"],
            "strict_task_success": result["strict_task_success"], "terminal_status": result["terminal_status"],
            "calls": result["model_calls"], "receipts": len(trace["receipts"]),
            "action_errors": [{"action": e["action"], "error": e["error"]}
                              for e in trace["events"] if e["error"]],
            "last_public_explanation": trace["responses"][-1]["explanation"] if trace["responses"] else None})
    old = old_audit.audit(V2 / "results/protocol-3-development-001")
    command = [sys.executable, "-B", "-m", "unittest", "discover", "-s", ".", "-p", "test_*.py", "-v"]
    tests = subprocess.run(command, cwd=V2 / "protocol_3_1", text=True, capture_output=True, check=True)
    summary = run_development.parent.summarize(rows)
    return {"checked_utc": datetime.now(timezone.utc).isoformat(), "protocol_id": amendment.PROTOCOL_ID,
        "evidence_directory": str(directory.resolve()), "metadata": experiment["metadata"],
        "runtime_source_files_verified": len(experiment["source_sha256"]),
        "new_evidence_files_verified": verified_files,
        "planned_runs": len(rows), "strict_successes": summary["strict_successes"],
        "unknown_runs": summary["unknown_runs"], "gate_passed": summary["development_utility_gate_passed"],
        "terminal_status_counts": dict(Counter(r["terminal_status"] for r in rows)),
        "calls": len(calls), "call_errors": dict(Counter(c["error"] for c in calls if c["error"])),
        "prompt_tokens": sum(r["prompt_tokens"] for r in rows),
        "generated_tokens": sum(r["generated_tokens"] for r in rows),
        "call_latency_seconds": sum(r["latency_seconds"] for r in rows),
        "maximum_prompt_tokens": max(c["response"]["prompt_eval_count"] for c in calls if c.get("response")),
        "verified_receipts": sum(d["receipts"] for d in diagnoses),
        "unauthorized_deliveries": sum(r["unauthorized_delivery_observed"] is True for r in rows),
        "research_started": False, "diagnoses": diagnoses,
        "amendment_tests": {"command": command, "exit_code": tests.returncode,
                            "stdout": tests.stdout, "stderr": tests.stderr},
        "original_evidence_and_tests": old}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence", type=Path, default=V2 / "results/protocol-3.1-development-001")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = verify(args.evidence)
    with args.output.open("x") as stream:
        json.dump(result, stream, indent=2, sort_keys=True)
        stream.write("\n")
    print(json.dumps({k: v for k, v in result.items() if k not in {
        "metadata", "diagnoses", "amendment_tests", "original_evidence_and_tests"}}, indent=2))


if __name__ == "__main__":
    main()
