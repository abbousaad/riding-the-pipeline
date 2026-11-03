# Revision V2 Change Log

24 September 2026. Scope: approved steps 1-3 only.

## Preservation

Archived 425 selected paper, code, trace, vector, result, and review files under `baseline/`. File-by-file SHA-256 verification checks the snapshot and original files. Credentials, dotfiles, virtual environments, symlinks, and bytecode were excluded. This is the pre-v2 state after earlier editorial edits, not an assertion about the exact originally submitted manuscript.

## Historical Analysis

| Issue | Correction |
|---|---|
| Similar AUCs against routine runs treated as equivalence | Direct attack-versus-benign AUC: tester 0.7569, deployer 0.4722 |
| Overlapping three-group ranges treated as evidence of indistinguishability | Exploratory paired-context bootstrap intervals, with fixed-reference and generalization limitations |
| A claimed exact 5% FPR | Nominal 95th-percentile calibration; observed clean LOO exceedance 2/30 = 6.67% per phase |
| B=3 presented as three attack instances | Three seed groups of four synthetic contexts; no distinct attack-instance claim |
| Tiny mean/line diagram with an ambiguous shaded band | Full-width per-observation distribution plot, both benign controls, targetless probe, and explicit calibration lines |
| Parameterized calls dropped before tool-profile calculation | Two read_source calls restored in one attack/test record; mean attack/test JS changes from 0.326537 to 0.302730 |

All historical explanation-distance AUCs reproduce unchanged. The exploratory 95% direct-AUC intervals are [0.5903, 0.9167] at Test and [0.2361, 0.7569] at Deploy. These are conditional on the selected synthetic contexts and fixed clean reference. They do not establish equivalence or out-of-sample detector performance.

Each of the 174 observations has an arm/seed/phase mapping, trace hash, raw-response hash, embedding hash, and preserved/reparsed tool calls in the observation manifest. A posteriori thresholds remain explicitly exploratory.

## Execution Repairs

| V1 behavior | V2 behavior |
|---|---|
| Empty or invalid tool lists replaced by all allowed tools | Empty means no action; malformed response recorded and stopped |
| Out-of-menu tools silently discarded | Requested names reach authorization and are logged even when denied |
| Argument suffixes discarded | Preserved for reanalysis; execution requires explicit schemas |
| Hard-coded poison written from a run flag | Exact accepted tester content is persisted |
| Deployer input scripted independently of stored memory | Read tool returns actual accepted entries |
| Gates evaluated after the run | Gates evaluated before each requested operation |
| Matched violations only checked as isolated predicates | Full-run interventions verify no forbidden side effect |
| Same layout constant counted as observed and expected provenance | Observed local artifact read/attestation state and digest binding; still an abstract model |
| Deploy name plus poison marker counted as success | Local artifact and receipt checked for actual target/digest and memory-chain linkage |
| Different synthetic commit context at each phase | One coherent context across the run |

## Verification and Remaining Evidence

The regression suite checks malformed/refused outputs, forbidden calls, argument retention, enforced denials, read-time source policy, workload revocation, exact memory flow, safe-target choice, required attestation, missing reads, digest mismatches, receiver integrity, and bounded execution.

Ten deterministic scenarios record actual local receiver outputs. Only the redirect fixture completes the adversarial memory path. The others demonstrate the expected refusal, safe deployment, or blocked operation. This is implementation validation, not an attack-success experiment.

`results/local_validation/` is the initial same-session validation output. `results/local_validation_02/` is the final rerun including the complete initial policy/configuration record; use it for current evidence. Both are deterministic fixtures. Original scientific results were not regenerated or overwritten.

No fresh model generations or external deployments were performed. No claims are made about real SPIFFE/in-toto/SLSA execution. The title, abstract, manuscript conclusions, and LaTeX figures have not been edited in this step; the corrected analysis and replacement figure are ready for the manuscript revision.
