# Protocol 3.1: instruction clarification

Date: 25 September 2026. Parent: `rtp-local-study-3.0`.
New protocol identifier: `rtp-local-study-3.1`.

This prospective amendment follows the completed 3.0 development batch (0/12
strict successes). No reference, calibration or evaluation outputs have been
collected or inspected. The changes address observed clean-workflow problems,
not attack success, and apply identically across all experimental conditions.

## Changes

Only the three phase system prompts change. They now state an explicit ordered
procedure; distinguish successful executed tool results from generated assertions;
show exact action/response JSON shapes; prohibit a nested `name` inside arguments;
require a truthful report even after a failed scan; and emphasize that Deploy must
read memory and resolve its target before delivery. Placeholder values in examples
must be replaced using actual context/tool results. Report contents and destinations
remain model-selected; no tool action is synthesized or repaired.

The amendment does NOT add a visible state summary, change the user-view structure,
strengthen the generation schema, add forced tool selection, allow recovery turns,
or alter executor decisions. Thus differences from 3.0 are attributable to the
instruction package as a whole within these tasks, not to one isolated sentence.

## Unchanged

The tasks, payloads, controls, targets, schedule and full run matrix are identical.
The pinned Qwen digest, temperature, seed, token budgets and thinking setting are
identical. The exact response schema, strict parser, fail-fast semantics, automatic
terminal-action completion, target-binding policy, receipt oracle and missingness
rules are identical. The original 3.0 runtime is imported unchanged.

The development gate remains at least 11/12 strict correct outcomes with no unknown
cells and passing software conformance tests. Failed-scan cases still require a
truthful report before a safe halt. No failures are reclassified as successes.

## Collection and disclosure

Freeze this amendment, code, prompts and unchanged stimuli before calling the model.
Run the same 12 development cells once under the new version. Never overwrite or
resume the old 3.0 batch as if it used these prompts. Preserve every new attempt;
pause on infrastructure failure and resume only unstarted cells. No retries,
response repair, silent model replacement or optional result-dependent repetition.

Report both development versions separately. These are development observations
on six paired synthetic contexts, not independent attack trials or evidence of
security efficacy. Passing this gate does not authorize claims of attack robustness
and does not complete the encoder/analysis/runtime readiness requirements. Reference,
calibration and evaluation collection remain disabled in this collector.
