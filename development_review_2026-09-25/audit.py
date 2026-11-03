"""Verify development evidence without rerunning the model or altering its data."""

import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import sys

HERE = Path(__file__).resolve().parent
V2 = HERE.parent
sys.path.insert(0, str(V2 / "study_runtime"))
import run_study
from runtime import outcomes


def verify_files(root, manifest, files_key="files"):
    files = manifest[files_key]
    entries = files.items() if isinstance(files, dict) else ((e["path"], e["sha256"]) for e in files)
    count = 0
    for name, expected in entries:
        actual = hashlib.sha256((root / name).read_bytes()).hexdigest()
        if actual != expected:
            raise ValueError("hash mismatch: " + str(root / name))
        count += 1
    return count


def audit(directory):
    experiment = json.loads((directory / "experiment.json").read_text())
    if (directory / "collection.lock").exists():
        raise ValueError("collection still running or orphaned lock requires inspection")
    if experiment["source_sha256"] != run_study.source_hashes():
        raise ValueError("runtime source changed after development collection")
    pack = run_study.inventory()
    rows, calls, files_checked, diagnoses = [], [], 0, []
    for row in experiment["schedule"]:
        root = directory / row["run_id"]
        run_study.verify_seal(root)
        manifest = json.loads((root / "manifest.json").read_text())
        files_checked += len(manifest["files"])
        trace = json.loads((root / "trace.json").read_text())
        result = json.loads((root / "outcome.json").read_text())
        recomputed = outcomes(pack["stimuli"][row["stimulus_id"]], trace, row["family"] + ".py")
        if any(result[k] != v for k, v in recomputed.items()):
            raise ValueError("outcome recomputation mismatch: " + row["run_id"])
        if any(result[k] != v for k, v in row.items()):
            raise ValueError("schedule identity mismatch")
        rows.append(result)
        calls += [json.loads(p.read_text()) for p in sorted((root / "calls").glob("call-*.json"))]
        diagnoses.append({"run_id": row["run_id"], "family": row["family"], "arm": row["arm"],
            "strict_task_success": result["strict_task_success"], "terminal_status": result["terminal_status"],
            "model_calls": result["model_calls"],
            "action_errors": [{"phase": e["phase"], "action": e["action"], "error": e["error"]}
                              for e in trace["events"] if e["error"]],
            "last_public_explanation": trace["responses"][-1]["explanation"] if trace["responses"] else None,
            "verified_receipts": len(trace["receipts"])})
    archive = verify_files(V2 / "baseline", json.loads((V2 / "baseline_manifest.json").read_text()))
    sealed = verify_files(V2, json.loads((V2 / "revision_manifest.json").read_text()))
    old_pilots = {}
    for name in ("ollama-qwen-pilot-001", "ollama-qwen-pilot-002"):
        root = V2 / "results" / name
        old_pilots[name] = verify_files(root, json.loads((root / "manifest.json").read_text()))
    suites = []
    for folder, pattern in ((V2, "test_harness.py"), (V2 / "gateway", "test_gateway.py"),
                            (V2 / "local_ollama", "test_local.py"),
                            (V2 / "experimental_design", "test_design.py"),
                            (V2 / "study_runtime", "test_*.py")):
        command = [sys.executable, "-B", "-m", "unittest", "discover", "-s", ".", "-p", pattern]
        completed = subprocess.run(command, cwd=folder, text=True, capture_output=True, check=True)
        suites.append({"directory": str(folder), "command": command, "exit_code": completed.returncode,
                       "stdout": completed.stdout, "stderr": completed.stderr})
    summary = run_study.summarize(rows)
    return {"checked_utc": datetime.now(timezone.utc).isoformat(),
        "evidence_directory": str(directory.resolve()), "evidence_kind": experiment["evidence_kind"],
        "protocol_id": experiment["protocol_id"], "metadata": experiment["metadata"],
        "audit_source_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "source_hashes_verified": len(experiment["source_sha256"]),
        "evidence_files_verified": files_checked, "baseline_files_verified": archive,
        "sealed_v2_files_verified": sealed, "old_pilot_files_verified": old_pilots,
        "planned_runs": len(rows), "strict_successes": summary["strict_successes"],
        "unknown_runs": summary["unknown_runs"],
        "development_utility_gate_passed": summary["development_utility_gate_passed"],
        "terminal_status_counts": dict(Counter(r["terminal_status"] for r in rows)),
        "calls": len(calls), "chat_requests_sent": sum(c["chat_sent"] for c in calls),
        "call_errors": dict(Counter(c["error"] for c in calls if c["error"])),
        "prompt_tokens": sum(r["prompt_tokens"] for r in rows),
        "generated_tokens": sum(r["generated_tokens"] for r in rows),
        "call_latency_seconds": sum(r["latency_seconds"] for r in rows),
        "maximum_prompt_tokens": max(c["response"]["prompt_eval_count"] for c in calls if c.get("response")),
        "verified_receipts": sum(d["verified_receipts"] for d in diagnoses),
        "research_collection_started": False, "tests": suites, "diagnoses": diagnoses}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence", type=Path, default=V2 / "results/protocol-3-development-001")
    parser.add_argument("--output", type=Path, required=True, help="new audit result JSON")
    args = parser.parse_args()
    result = audit(args.evidence)
    with args.output.open("x") as stream:
        json.dump(result, stream, indent=2, sort_keys=True)
        stream.write("\n")
    print(json.dumps({k: v for k, v in result.items() if k not in {"metadata", "tests", "diagnoses"}}, indent=2))


if __name__ == "__main__":
    main()
