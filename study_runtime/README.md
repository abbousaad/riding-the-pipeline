# Protocol-3 development runtime

This additive implementation leaves the frozen design, v2 harness and all earlier
results untouched. It consumes the verified `experimental_design/snapshot-3.0`
prompts, response schema, tasks and schedule. It does not use the pilot's additional
explicit-stop prompt. The old action executors are reused behind stricter schema,
prerequisite, phase-ending and target-binding checks.

Only the 12 development cells are enabled. Reference, calibration and evaluation
collection are deliberately unavailable until the development/conformance gate,
encoder installation, complete analysis workflow and research runtime seal are
ready. Passing development is not evidence of attack resistance.

The first live batch is complete: **0/12 strict successes; development gate failed**.
See [the development report](../development_review_2026-09-25/REPORT.md) for the
failure breakdown and verified evidence. Do not rerun those cells or start the
main study under this version. A declared interface/prompt amendment is needed.

## Commands

From this directory:

```sh
python3 -B -m unittest discover -s . -p 'test_*.py' -v
python3 -B run_study.py
python3 -B run_study.py --live --output ../results/protocol-3-development-001
```

Live mode uses the installed, digest-pinned local Qwen model. It does not require
credits, download another model, or contact a model gateway. Output must be a new
directory. All deployment destinations are local receipt labels only.

After a transport interruption, continue only unstarted cells with:

```sh
python3 -B run_study.py --live --resume --output ../results/protocol-3-development-001
```

Started cells, including failed ones, are never retried or replaced. A batch pauses
on the first infrastructure failure. Resume verifies source/environment identity
and per-run evidence hashes. An exclusive lock prevents concurrent collection;
an orphaned lock after a hard crash requires inspection, not automatic deletion.
Unsealed crashed cells are reported as interrupted and never rerun. Summary files
are append-only snapshots. A per-run manifest seals requests, stimuli, checkpoints,
traces, outcomes and receipt files. No incomplete cell counts as a successful defense.

`runtime.py` supplies strict parsing, fail-fast execution and receipt-based outcomes.
`local_client.py` records native Ollama calls using the existing loopback-only
transport and model preflight. `analysis_core.py` contains offline-tested extraction,
fitting, AUC, action divergence, uncertainty and missingness primitives; it is not
yet a complete research report pipeline or an installed embedding encoder.

The analysis tests use fake encoders and synthetic traces. Offline collector tests
use a fake local transport and label their evidence `offline_fixture`. They are
not model measurements, even when test logs mention successful tasks.
