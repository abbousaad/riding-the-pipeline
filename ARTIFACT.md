# Riding the Pipeline — research artifact

Artifact for: S. Abbou, A. Z. Faroukhi, and Y. Gahi, "Riding the Pipeline: Memory-Mediated Redirection and
Explanation Drift in a CI/CD Agent Simulator," in *Proc. 9th Int. Conf. Adv. Commun. Technol. Netw. (CommNet)*, 2026.

Everything runs locally. Targets are receiver labels; nothing contacts external systems. No credentials are included;
the historical recorder (`baseline/poc/agent_llm.py`) needs your own `MOONSHOT_API_KEY` only to record new traces.

| Paper element | Where |
|---|---|
| Repaired executor and receipts | `harness.py`, `actions.py`, `local_fixtures.py`, `validate_local.py` |
| Historical reanalysis (174 responses, Tables III–IV, Fig. 2) | `reanalyze.py`, `results/historical_reanalysis/` |
| Baseline signals (Table IV) | `camera_ready_analysis/baselines.py` |
| Destination binding vs. current policy (Table V) | `camera_ready_analysis/mitigation.py` |
| Fresh development batch (protocol 3.1) | `study_runtime/`, `protocol_3_1/`, `results/protocol-3.1-development-001/` |
| Archived evidence with hashes | `baseline/`, `baseline_manifest.json`, `revision_manifest.json` |

Quick check (Python 3.10+, standard library only):

```sh
python3 -B seal_revision.py --verify                    # published sources and results match their hashes
python3 -B camera_ready_analysis/reanalyze_release.py   # regenerates Tables III-IV and Fig. 2
python3 -B -m unittest -v test_harness
python3 -B camera_ready_analysis/baselines.py
python3 -B camera_ready_analysis/mitigation.py
```

`preserve_baseline.py --verify` additionally compares the snapshot with the original pre-revision directory,
which is not part of this release; the snapshot hashes themselves are in `baseline_manifest.json`.
`reanalyze_release.py` overwrites `results/historical_reanalysis/`. On a platform other than the one used
(macOS, Python 3) some floating-point values in `analysis.json` may differ in the last one or two digits (~1e-15),
so the seal check can then report that file as changed; every reported value and `ANALYSIS.md` are unaffected.

Three snapshot files listed in `baseline_manifest.json` are withheld because they contain confidential peer-review
material: `reviews.md`, `SUBMISSION_PREP.md`, and `review_2026-09-24/DEEP_REVIEW.md`.
See `README.md` for the full revision notes.
