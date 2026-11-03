# Corrected Analysis of the Historical Cached Observations

These are reanalyses of the archived v1 prompts and outputs, not executions of the repaired v2 harness.

## Direct Attack-versus-Benign Comparisons

Higher distance is ranked as more attack-like. Each comparison uses the same 12 paired synthetic contexts.

| Phase | Direct AUC | Exploratory 95% paired-bootstrap interval | Paired mean difference |
|---|---:|---:|---:|
| test | 0.7569 | [0.5903, 0.9167] | 0.0697 |
| deploy | 0.4722 | [0.2361, 0.7569] | -0.0011 |

Intervals use 10,000 paired resamples (seed 20260924) with the clean reference held fixed. They describe variability within the selected synthetic contexts; they are not evidence of equivalence, independent attack-instance coverage, or generalization to new workflows. No threshold selected on these samples has held-out validation.

The tester retains some descriptive ranking information. At the deployer, these two selected arms have little separation under this scalar score. Similar AUCs against a third, routine group alone cannot establish indistinguishability.

## Calibration and Historical Arm Results

The reference is a 95th-percentile calibration threshold, not an exactly 5% measured false-positive rate. In each phase 2/30 leave-one-out routine scores exceed it (6.67%). Fresh test FPR has not been measured. Routine scores use 29-item reference centroids, whereas non-routine scores use the full 30-item centroid. That asymmetry is preserved for historical comparability and should be replaced by a separate calibration/test design in new experiments.

| Arm | Phase | AUC vs routine | Mean distance | Threshold crossings |
|---|---|---:|---:|---:|
| attack | test | 1.0000 | 0.3869 | 12/12 |
| attack | build | 0.5444 | 0.1064 | 0/12 |
| attack | deploy | 0.8694 | 0.1865 | 6/12 |
| benign_override | test | 0.9667 | 0.3172 | 10/12 |
| benign_target | deploy | 0.8444 | 0.1876 | 6/12 |
| targetless | test | 0.9944 | 0.3163 | 11/12 |
| targetless | deploy | 0.6694 | 0.1522 | 3/12 |

## Experimental Unit

The legacy B=3, K=4 arrangement partitions 12 synthetic contexts into three seed groups. It does not establish three distinct attack instances. Context variation is limited to prompt metadata; no real repository changes are established by those labels. Consequently the original per-group ranges are not used as uncertainty estimates here.

## Tool-profile Correction

Legacy calls are reparsed without dropping unknown names or parameter suffixes and without synthesizing actions from empty lists. One of the 174 records restores two parameterized read_source calls. The explanation text and cached vector for every observation are unchanged. Historical tool histograms remain requested-action profiles, not verified execution traces.

| Arm | Phase | Original mean JS | Corrected mean JS |
|---|---|---:|---:|
| attack | test | 0.326537 | 0.302730 |
| attack | build | 0.000000 | 0.000000 |
| attack | deploy | 0.056395 | 0.056395 |
| benign_override | test | 0.287958 | 0.287958 |
| benign_target | deploy | 0.074674 | 0.074674 |
| targetless | test | 0.214404 | 0.214404 |
| targetless | deploy | 0.038115 | 0.038115 |

## Figure

`figure3_revised.svg` and `figure3_revised.png` plot all observations at Test, Build, and Deploy, with per-phase routine-calibration thresholds. Routine dots are leave-one-out scores; other dots use the full routine centroid. The verdict-probe points represent targetless prompts, not verified second-payload deployments. Direct AUCs appear only in the relevant two comparison panels. There is no shaded confidence band or line connecting phase means.

## Evidence

`observation_manifest.json` links each arm/seed/phase to its trace and vector with file hashes and preserved/reparsed actions. `analysis.json` contains all per-observation distances. No API calls, new model observations, or external deployments were made. The historical 12/12 oracle count is retained only as an archived simulation output, not a validated success rate.
