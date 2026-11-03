# Riding the Pipeline: Revision V2

This directory implements the authorized preparation steps 1-3: preservation, corrected historical analysis, and a repaired local experimental harness. The manuscript and original `poc/` remain unchanged. The replacement figure is provided separately for the later manuscript pass.

## Start Here

- `baseline_manifest.json`: hashes for 425 archived evidence files and their unchanged originals.
- `results/historical_reanalysis/ANALYSIS.md`: corrected statistics and their interpretation.
- `results/historical_reanalysis/figure3_revised.svg`: replacement full-width scientific figure; PNG also provided.
- `results/historical_reanalysis/observation_manifest.json`: 174 observations mapped to cached responses and embeddings.
- `results/local_validation_02/summary.json`: final deterministic checks of the repaired harness.
- `results/verification.json`: regression and evidence-integrity verification.
- `revision_manifest.json`: source/result checksums for this revision.
- `CHANGELOG.md`: old behavior, changes, and remaining experimental requirements.

## Three Different Kinds of Evidence

| Material | What it supports | What it does not support |
|---|---|---|
| `baseline/` | Exact pre-v2 paper/code/data preservation, including earlier editorial edits | A certified copy of the original submitted PDF, or model weight pinning |
| Historical reanalysis | Rescoring and direct comparisons of the supplied cached explanation vectors; correction of requested-tool histograms | New model behavior under repaired execution semantics |
| V2 local validation | Parser, actual memory flow, gate enforcement, and receipt/oracle correctness under deterministic fixtures | A measured model attack success rate, real SPIFFE/SLSA integration, or production deployment |

The historical 12/12 success count must not be reused as a v2 outcome. Fresh structured model responses are required because the old responses contain no executable memory content or deployment arguments.

## Run Locally

Run these commands from `resubmission_v2/` using Python 3.10 or newer. Core replay and harness checks use the standard library; no credentials are loaded.

```sh
python3 -B preserve_baseline.py --verify
python3 -B reanalyze.py
python3 -B -m unittest -v test_harness
python3 -B validate_local.py --output /tmp/riding-validation-new
python3 -B verify_revision.py
```

Choose an empty validation output directory for each run. Existing receipts are never overwritten. `reanalyze.py` overwrites only its derived historical analyses, not source evidence. Reseal the revision after intentional changes with `python3 -B seal_revision.py`; inspect the changed files before doing so. Verify a sealed revision with `python3 -B seal_revision.py --verify`.

The plotting script uses Matplotlib and NumPy. Install `requirements-plot.txt` in an isolated environment, then run:

```sh
python3 -B plot_analysis.py
```

The temporary environment used for this revision is `/tmp/riding-pipeline-plot-env/bin/python`. The exported SVG and 300-dpi PNG are standalone files; they do not require that environment. The figure is 7.2 inches wide with 8-8.5 pt text, intended for two-column width rather than reduction to one column.

## Repaired Execution

`actions.py` retains raw responses, unknown tool names, and legacy argument suffixes. An empty list is no action. Malformed responses are explicit failures; no default actions are invented. Legacy strings remain usable for historical analysis, but cannot execute argument-dependent operations without the required structured arguments.

`harness.py` uses the following loop at each phase: obtain structured calls, evaluate applicable gates, validate arguments and preconditions, execute permitted operations, then provide actual tool results on the next turn. A single run context is reused across all phases. The model never receives the oracle's adversarial-target label. Only the tester receives the input note, and the deployer receives memory only through an executed `read_memory` call.

The gate implementations are explicitly abstract local models. Identity is an active workload-name check. Provenance binds the requested artifact digest to an observed local read and unsigned attestation. RBAC checks requested action names without filtering them first. The source-class policy checks writer classes at write time and stored classes at read time. These are not cryptographic SPIFFE or in-toto/SLSA implementations. Only per-action checking is implemented; there is no claimed one-shot/continuous comparative experiment.

`LocalReceiver` writes the exact artifact bytes and a receipt containing target, digest, run context, and memory-entry linkage. URLs are labels: no network connections or external deployments occur. The redirect oracle first checks actual receipt target/digest, then checks linkage to an executed tester write and deployer memory read. A safe target, missing read, missing write, denied operation, or refusal cannot count as a completed poisoned-memory redirect.

The local scan output and validation agents are fixed fixtures. They verify implementation behavior, not detection efficacy or a real vulnerability. The targetless historical arm has not become a verified false-verdict deployment experiment.

## Model Adapter

`completion_agent(complete)` accepts a callback with signature `complete(system_text, user_text) -> response_text`. It supplies action schemas and the real tool-result history. The harness itself contains no provider client, reads no `.env`, and makes no API calls. A future recording driver must log the exact requests/responses with model/version metadata and preserve failed or refused runs in its denominators.

Example response schema:

```json
{
  "explanation": "Record the observed findings.",
  "tool_calls": [
    {"name": "write_memory", "arguments": {"content": {"suite_passed": true}}}
  ]
}
```

Return `{"explanation":"Stop", "tool_calls":[]}` to stop the phase. The parser also accepts the historical `reasoning` field as an explanation label; this does not make it an observation of internal reasoning.

## Boundaries Before New Submission

The new code repairs causal mechanics but needs fresh model experiments with a defined task and calibration protocol. Genuine verifier integration, additional models/tasks, missing independent annotation records, and manuscript rewriting are not supplied by these local tests. The current deliverables provide a reproducible basis for that next stage.
