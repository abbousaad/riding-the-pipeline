# Protocol 3.1 development validation

Date: 25 September 2026. Protocol: `rtp-local-study-3.1`.

## Result

The completed local `qwen3.5:9b` batch passed 12/12 strict development checks:
six truthful failed-scan reports followed by safe halts, and six approved local
deliveries with verified receipts. The unchanged acceptance threshold was 11/12,
with no unknown outcomes and passing software conformance tests.

The batch contains 66 model calls, 67,272 prompt tokens, 3,308 generated tokens,
and 386.66 seconds of summed call latency. There were no infrastructure errors,
no action errors, and no unauthorized deliveries. The maximum prompt was 1,345
tokens. The model digest is
`6488c96fa5faab64bb65cbd30d4289e20e6130ef535a93ef9a49f42eda893ea7`;
the recorded Ollama version is 0.33.3.

These are six paired synthetic contexts under clean and clean-bound conditions,
not 12 independent attack trials. No attack-success rate, detector effectiveness,
production-control bypass, or cross-model generalization follows from this batch.

## Amendment and retained evidence

Protocol 3.0 failed the same gate with 0/12 strict successes. That failed batch is
retained separately. Protocol 3.1 clarified the three phase instructions, including
JSON nesting, truthful failed-scan reporting, and deployment prerequisites. It did
not change the model, tasks, schedule, response schema, executor, oracle, or
acceptance threshold. This is development iteration, not held-out evaluation.

Evidence is in `../results/protocol-3.1-development-001/`; the original failure is
in `../results/protocol-3-development-001/`. `verification-001.json` records the
first completed audit; `verification-002.json` repeats that audit after the
manuscript and legacy-code corrections, with all checks passing. The verifier
recomputes outcomes and checks actual requests,
16 source hashes, 204 new evidence files, the prior development evidence, 425
baseline files, 66 sealed v2 files, and earlier pilot evidence. It also runs 142
offline software tests. These test counts are not experimental sample sizes.

## Manuscript and legacy code correction

The paper now separates archived Kimi prompt observations, ten deterministic
executor scenarios, and these fresh Qwen development checks. The unsupported
75% historical attack-success claim was removed. The earlier count of 56 refers
to 32 harness and 24 gateway unit tests, not 56 full-run experiments.

The editable legacy `poc` path now reports requested-action outcomes as unknown
and no success percentage. It no longer fabricates memory effects for custom or
model reasoners. The synthetic fixture's denied-deployment state is initialized,
and regression tests cover denial, safe-target requests, reversed action order,
missing resolution, and the distinction between unknown and zero success.
These maintenance changes do not modify any frozen protocol or recorded model run.

## Next boundary

Research collection has not started. Passing development validation does not
complete the frozen encoder, analysis, or research-runtime readiness requirements.
Reference, calibration, and evaluation collection remain disabled in this
development collector. Prepare and verify those components before collecting
research outcomes, without pooling development observations into evaluation.
