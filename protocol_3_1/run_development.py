"""Protocol 3.1 development collector; unchanged protocol-3.0 executor and oracle."""

import argparse
import json
from pathlib import Path
import sys

import amendment

sys.path.insert(0, str(amendment.V2 / "study_runtime"))
import run_study as parent
from runtime import Runner, Receiver, InfrastructureError, outcomes
from local_client import Client, now, save_new, preflight, environment_identity, pilot


def source_hashes():
    return {**parent.source_hashes(), **{
        "protocol_3_1/" + name: digest for name, digest in amendment.source_hashes().items()}}


def collect(output, *, resume=False, send=pilot.transport, evidence_kind="live_local_ollama"):
    pack = amendment.verify()
    schedule = [r for r in pack["schedule"] if r["split"] == "development"]
    output = Path(output)
    hashes = source_hashes()
    metadata = preflight(pack["study"], send)
    if resume:
        experiment = json.loads((output / "experiment.json").read_text())
        if (experiment["source_sha256"] != hashes or experiment["schedule"] != schedule or
                experiment["snapshot_manifest_sha256"] != parent.digest(amendment.SNAPSHOT / "manifest.json") or
                experiment["evidence_kind"] != evidence_kind or
                environment_identity(experiment["metadata"]) != environment_identity(metadata)):
            raise InfrastructureError("resume_environment_or_source_changed")
    else:
        output.mkdir(parents=True, exist_ok=False)
        save_new(output / "experiment.json", {"protocol_id": amendment.PROTOCOL_ID,
            "executor_version": "3.0.0-development", "evidence_kind": evidence_kind,
            "started_utc": now(), "split": "development", "source_sha256": hashes,
            "snapshot_manifest_sha256": parent.digest(amendment.SNAPSHOT / "manifest.json"),
            "schedule": schedule, "study": pack["study"], "metadata": metadata,
            "prompts": pack["prompts"], "response_schema": pack["response_schema"],
            "amendment": "System instructions only; executor, oracle, tasks, model settings and gate unchanged"})
    lock = output / "collection.lock"
    with lock.open("x") as stream:
        stream.write(now())
    try:
        rows, paused = [], False
        for row in schedule:
            directory = output / row["run_id"]
            if directory.exists():
                if (directory / "manifest.json").exists():
                    parent.verify_seal(directory)
                    rows.append(json.loads((directory / "outcome.json").read_text()))
                else:
                    partial = parent.unknown(row, True, "interrupted_unsealed_cell_not_retried")
                    checkpoints = sorted(directory.glob("checkpoint-*.json"))
                    if checkpoints:
                        trace = json.loads(checkpoints[-1].read_text())
                        trace.update(terminal_status="infrastructure_error", missing_reason=partial["missing_reason"])
                        partial.update(outcomes(pack["stimuli"][row["stimulus_id"]], trace, row["family"] + ".py"))
                    rows.append(partial)
                continue
            if paused:
                rows.append(parent.unknown(row))
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
                trace["protocol_id"] = amendment.PROTOCOL_ID
                save_new(directory / f"checkpoint-{checkpoint_number:04d}.json", trace)
                checkpoint_number += 1

            print(f"Starting {row['run_id']}: {row['family']} / {row['arm']}", flush=True)
            try:
                trace = runner.run(client.complete, max_turns=pack["study"]["execution"]["max_turns_per_phase"],
                                   checkpoint=checkpoint)
            except (OSError, InfrastructureError) as exc:
                runner.terminal_status, runner.missing_reason = "infrastructure_error", str(exc)
                trace = runner.snapshot()
            trace["protocol_id"] = amendment.PROTOCOL_ID
            result = {**row, "protocol_id": amendment.PROTOCOL_ID,
                      **outcomes(stimulus, trace, row["family"] + ".py"), **client.usage()}
            save_new(directory / "trace.json", trace)
            save_new(directory / "outcome.json", result)
            parent.seal(directory)
            rows.append(result)
            print(f"Finished {row['run_id']}: {result['terminal_status']}; "
                  f"strict_success={result['strict_task_success']}; calls={client.count}", flush=True)
            paused = result["terminal_status"] == "infrastructure_error"
        summary = {"created_utc": now(), "protocol_id": amendment.PROTOCOL_ID,
                   "evidence_kind": evidence_kind, "paused": paused, **parent.summarize(rows)}
        if not summary["development_utility_gate_passed"]:
            summary["research_blockers"].insert(0, "development utility gate not passed")
        number = len(list(output.glob("summary-*.json")))
        save_new(output / f"summary-{number:04d}.json", summary)
        return summary
    finally:
        lock.unlink()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if not args.live:
        amendment.verify()
        print(json.dumps({"protocol_id": amendment.PROTOCOL_ID, "runs": 12,
                          "maximum_calls": 216, "research_enabled": False}, indent=2))
        return
    if args.output is None:
        parser.error("--live requires --output")
    result = collect(args.output, resume=args.resume)
    print(json.dumps({k: v for k, v in result.items() if k != "runs"}, indent=2))


if __name__ == "__main__":
    main()
