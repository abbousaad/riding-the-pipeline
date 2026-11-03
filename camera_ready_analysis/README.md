# Camera-ready analyses (CommNet'26 reviews)

Added 3 November 2026. Offline only: no model calls, no new observations, no external deployments.
The sealed revision (`seal_revision.py --verify`) is untouched; these scripts only read it.

| Script | Answers | Output |
|---|---|---|
| `baselines.py` | R1 "compare against meaningful baselines": explanation distance vs. action-profile JS, sequence change, and an approved-destination rule on the same 12 matched pairs | `baselines.json` |
| `mitigation.py` | R1 "evaluate the proposed mitigation directly", R2 "approval-bound capabilities": 12 deterministic scenarios under the current policy and destination binding | `mitigation.json` |

Run from the parent directory:

```sh
python3 -B camera_ready_analysis/baselines.py
python3 -B camera_ready_analysis/mitigation.py
```

`baselines.py` checks that its mean JS values reproduce the sealed `analysis.json` exactly.
Binding uses the same predicate as `study_runtime`'s `target_bound` policy.
