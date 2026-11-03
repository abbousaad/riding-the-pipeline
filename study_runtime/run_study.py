"""Run protocol-3 development only. Research splits are deliberately gated off."""

import argparse
import hashlib
import json
from pathlib import Path
import sys

from runtime import V2, Runner, Receiver, InfrastructureError, outcomes
from local_client import Client, now, save_new, preflight, environment_identity, pilot

sys.path.insert(0, str(V2 / "experimental_design"))
import design

HERE = Path(__file__).resolve().parent
SNAPSHOT = V2 / "experimental_design/snapshot-3.0"


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def source_hashes():
    paths = list(HERE.glob("*.py")) + [V2 / "harness.py", V2 / "actions.py",
        V2 / "local_ollama/run_local.py", V2 / "gateway/run.py", V2 / "gateway/client.py"]
    return {p.relative_to(V2).as_posix(): digest(p) for p in sorted(paths)}


def inventory():
    design.verify(SNAPSHOT)
    return {name: json.loads((SNAPSHOT / (name + ".json")).read_text())
            for name in ("study", "schedule", "stimuli", "prompts", "response_schema")}


def seal(directory):
    save_new(directory / "manifest.json", {"files": {
        p.relative_to(directory).as_posix(): digest(p)
        for p in sorted(directory.rglob("*")) if p.is_file()}})


def verify_seal(directory):
    manifest = json.loads((directory / "manifest.json").read_text())
    for name, expected in manifest["files"].items():
        path = directory / name
        if not path.is_file() or digest(path) != expected:
            raise InfrastructureError("evidence_hash_mismatch: " + name)


def unknown(row, started=False, reason="not_started"):
    return {**row, "planned": True, "started": started, "missing_reason": reason,
            "terminal_status": "infrastructure_error" if started else "not_started",
            "strict_task_success": None, "unauthorized_delivery_observed": None,
            "memory_linked_redirect_observed": None, "model_calls": 0}


def summarize(rows):
    passed = sum(row.get("strict_task_success") is True for row in rows)
    missing = sum(row.get("strict_task_success") is None for row in rows)
    return {"planned_runs": len(rows), "strict_successes": passed, "unknown_runs": missing,
            "development_utility_gate_passed": len(rows) == 12 and missing == 0 and passed >= 11,
            "research_collection_ready": False,
            "research_blockers": ["full analysis/encoder runtime not yet sealed", "conformance record required"],
            "runs": rows}


def collect(output, *, resume=False, send=pilot.transport, evidence_kind="live_local_ollama"):
    pack = inventory()
    schedule = [r for r in pack["schedule"] if r["split"] == "development"]
    output = Path(output)
    hashes = source_hashes()
    metadata = preflight(pack["study"], send)
    if resume:
        experiment = json.loads((output / "experiment.json").read_text())
        if (experiment["source_sha256"] != hashes or experiment["schedule"] != schedule or
                experiment["snapshot_manifest_sha256"] != digest(SNAPSHOT / "manifest.json") or
                experiment["evidence_kind"] != evidence_kind or
                environment_identity(experiment["metadata"]) != environment_identity(metadata)):
            raise InfrastructureError("resume_environment_or_source_changed")
    else:
        output.mkdir(parents=True, exist_ok=False)
        save_new(output / "experiment.json", {"protocol_id": pack["study"]["protocol_id"],
            "evidence_kind": evidence_kind, "started_utc": now(), "split": "development",
            "source_sha256": hashes, "snapshot_manifest_sha256": digest(SNAPSHOT / "manifest.json"),
            "schedule": schedule, "study": pack["study"], "metadata": metadata,
            "prompts": pack["prompts"], "response_schema": pack["response_schema"]})
    # A held lock is never automatically broken, including after a process crash.
    lock = output / "collection.lock"
    with lock.open("x") as stream:
        stream.write(now())
    try:
        rows = []
        paused = False
        for row in schedule:
            directory = output / row["run_id"]
            if directory.exists():
                if (directory / "manifest.json").exists():
                    verify_seal(directory)
                    rows.append(json.loads((directory / "outcome.json").read_text()))
                else:
                    partial = unknown(row, True, "interrupted_unsealed_cell_not_retried")
                    checkpoints = sorted(directory.glob("checkpoint-*.json"))
                    if checkpoints:
                        trace = json.loads(checkpoints[-1].read_text())
                        trace.update(terminal_status="infrastructure_error", missing_reason=partial["missing_reason"])
                        partial.update(outcomes(pack["stimuli"][row["stimulus_id"]], trace, row["family"] + ".py"))
                    rows.append(partial)
                continue
            if paused:
                rows.append(unknown(row))
                continue
            directory.mkdir()
            save_new(directory / "started.json", {**row, "started_utc": now()})
            stimulus = pack["stimuli"][row["stimulus_id"]]
            save_new(directory / "stimulus.json", stimulus)
            runner = Runner(stimulus, Receiver(directory / "receiver"))
            client = Client(pack["study"], pack["prompts"], pack["response_schema"],
                            directory / "calls", metadata, row["model_call_cap"], send)
            checkpoint_number = 0

            def checkpoint(trace):
                nonlocal checkpoint_number
                save_new(directory / f"checkpoint-{checkpoint_number:04d}.json", trace)
                checkpoint_number += 1

            print(f"Starting {row['run_id']}: {row['family']} / {row['arm']}", flush=True)
            try:
                trace = runner.run(client.complete, checkpoint=checkpoint)
            except (OSError, InfrastructureError) as exc:
                runner.terminal_status = "infrastructure_error"
                runner.missing_reason = str(exc)
                trace = runner.snapshot()
            result = {**row, **outcomes(stimulus, trace, row["family"] + ".py"), **client.usage()}
            save_new(directory / "trace.json", trace)
            save_new(directory / "outcome.json", result)
            seal(directory)
            rows.append(result)
            print(f"Finished {row['run_id']}: {result['terminal_status']}; "
                  f"strict_success={result['strict_task_success']}; calls={client.count}", flush=True)
            paused = result["terminal_status"] == "infrastructure_error"
        summary = {"created_utc": now(), "evidence_kind": evidence_kind, "paused": paused,
                   **summarize(rows)}
        number = len(list(output.glob("summary-*.json")))
        save_new(output / f"summary-{number:04d}.json", summary)
        return summary
    finally:
        lock.unlink()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--resume", action="store_true", help="continue only unstarted cells")
    args = parser.parse_args()
    if not args.live:
        pack = inventory()
        print(json.dumps({"mode": "offline", "split": "development", "runs": 12,
                          "maximum_calls": 216, "research_enabled": False,
                          "model": pack["study"]["generator"]["model"]}, indent=2))
        return
    if args.output is None:
        parser.error("--live requires --output")
    result = collect(args.output, resume=args.resume)
    print(json.dumps({key: value for key, value in result.items() if key != "runs"}, indent=2))


if __name__ == "__main__":
    main()
