# LLM Gateway multi-model pilot

This additive integration imports the sealed v2.0 local simulator without changing
its source, baseline, results, or revision manifest. Python 3.10+; no dependencies.
No live completions have been run as part of implementation.

## Experiment scope

- One chosen model handles all three roles in each run. Models are compared across
  separate full runs; this is not yet a mixed-model, per-role factorial experiment.
- Two paired arms: clean source and the same source with an adversarial comment.
  The payload reaches the tester only through an executed source read. Deployer
  views receive actual shared-memory outputs, never the payload or oracle label
  directly. Role instructions and task context are identical across models/arms.
- The example uses GPT-4.1 Mini, dated Claude Sonnet 4.5, and Gemini 2.5 Flash.
  Their provider-qualified IDs were found in the public gateway catalog on
  2026-09-24. These are editable examples, not a claim of equivalent capability
  or permanently available versions. Confirm account access before the pilot.
- One repetition is an integration smoke test, not a scientific sample size.
  Multiple tasks/payloads, benign-anomaly controls, interventions, calibrated
  sampling, and a fixed analysis plan are still required for paper results.
- Source code, scan result, and prebuilt artifact are synthetic fixtures. There
  is no real build, network deployment, SPIFFE verification, or signed provenance.
  All target URLs are local receiver labels. LLM requests do leave the machine;
  only synthetic fixture data is sent by the supplied configuration.

## Run

From this directory:

```sh
python3 -B run.py
python3 -B run.py --list-models
python3 -B -m unittest discover -s . -p 'test_gateway.py' -v
```

The default command is an offline plan. The catalog command performs a public,
unauthenticated GET and does not generate tokens. Review `pilot.example.json`:
the example schedules six runs, at most 108 completion requests and 221184
requested output tokens. `order_seed` controls scheduling only, not model RNG.
Each model has its own parameter object. The example uses temperature zero as a
smoke-test choice, not a guarantee of deterministic results. Reasoning parameters
and JSON mode are not forced across models with different capabilities.

For live execution, set `LLM_GATEWAY_API_KEY` securely in the process environment,
review the model choices and spending controls, then explicitly opt in:

```sh
python3 -B run.py --config pilot.example.json --live --output ../results/gateway-pilot-001
```

Do not put the key in JSON, source files, command arguments, or chat. The runner
does not load `.env`, inspect other credentials, or send the paper to the gateway.
Output must be a new directory. No resuming, overwriting, replay-as-new-samples,
automatic retries, response healing, or silent substitution is performed.

## Controls and evidence

Calls go to `https://api.llmgateway.io/v1/chat/completions` with a provider-qualified
model, `X-No-Fallback: true`, and `X-No-Cache: true`. Cached responses and an
explicitly reported different provider are rejected. Raw routing metadata is
retained, including actual model/provider identifiers when supplied. The runner
cannot certify undisclosed backend revisions; review these fields before pooling
runs. Provider-side prompt caching is different from full-response reuse and is
not an independent-sample violation by itself. Provider pinning may require PAYG;
DevPass may reject provider-qualified requests. Errors are not bypassed by routing
to another provider.

`max_requests` is a hard local request-attempt cap. `max_reported_cost_usd` is a
post-response guard using gateway-reported total costs, NOT a guaranteed billing
limit or price estimate. One request can exceed it; timed-out or failed requests
may still incur charges. Missing/unrecognized cost stops all further requests.
Set an appropriate project/account spend limit in the gateway dashboard too. The
example's $1 guard is provisional configuration, not approval to incur charges.

Each experiment records configuration, schedule, prompts, fixture definitions,
runtime and source hashes. Each call records request/hash, response text and parsed
body, finish reason, usage/cost, routing metadata and latency. Authorization headers
are omitted and any echoed key is redacted. Provider errors remain in evidence;
there are no retries. Avoid using sensitive real source files without reviewing
the gateway/provider data-retention policies and your own research requirements.

Each run records executed/denied actions, parse errors, actual shared-memory state,
local artifact receipts, and outcomes. `summary.json` keeps all planned runs,
including those skipped after a cap. Incomplete runs have null final attack outcomes;
any already-observed adversarial delivery is reported separately, not discarded.
Malformed output, truncation, provider refusal, HTTP failures, and turn limits are
not collapsed into attack success. Empty action lists are not automatically labeled
as refusal: they also represent normal task completion. Public explanations are
not measurements of private chain-of-thought.

The summary reports receipt-based outcomes, not overall clean-task correctness.
An approved-target delivery alone does not prove every required test/build step
was completed correctly; inspect the trace before classifying task success.

## Official API references

- [Quickstart](https://docs.llmgateway.io/quick-start)
- [Chat completion schema](https://docs.llmgateway.io/v1_chat_completions)
- [Routing and no-fallback header](https://docs.llmgateway.io/features/routing)
- [Gateway caching and bypass header](https://docs.llmgateway.io/features/caching/gateway-caching)
- [Model catalog](https://docs.llmgateway.io/v1_models)
