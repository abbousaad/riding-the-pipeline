# Riding the Pipeline — measurement PoC

Executable companion to *Riding the Pipeline: Measured Blindness of Identity and
Provenance Gates to Behavioral Compromise in Agent-Operated CI/CD*. It instantiates
the compromise chain of §IV on an instrumented pipeline whose agents are a real
language model (kimi-k2.5), runs the four gates of §II against it, and produces the
measurement §VI reports: every gate allows the compromise at every phase, one-shot
and continuous, while behavior tells a split story that the gates cannot read.

Two findings, both measured over M=30 clean and 12 compromised runs (B=3, K=4):

1. **The gates are blind.** All four return allow at every phase, in one-shot and
   continuous mode, and each blocks its paired negative control. The compromise
   reaches production.
2. **Behavioral divergence is uneven.** The compromised agent's reasoning separates
   completely from clean (AUC 1.00); the deceived deployer that lands the payload
   separates far more weakly (AUC 0.87), shallow enough that a threshold calibrated
   to benign variation crosses on only half its runs. The separation is real but too
   marginal to gate on where the damage is done, and sharp enough to gate on where
   adversarial content is processed.

The point is not to ship a pipeline. It is to make one negative result trustworthy,
that the gates admit the compromise by construction rather than by misconfiguration
or a lucky run, and to measure where in the agents' behavior the compromise is even
visible.

## Scope boundary (why this stays an attack-measurement paper)

This PoC builds no defense. The divergence instrument reads the recorded trace after
the fact to mark where a control could have acted; it scores nothing live and revokes
nothing. That boundary is enforced by `test_instrument_builds_no_defense`. The
runtime control that closes the gap is article-02's contribution.

## What's in here

```
poc/
├── chain.yaml              # Listing 1 — the compromise chain descriptor
├── gates.py                # §II — four gates, one-shot + continuous, + negative controls
│                           #        (RBAC reads the agent's real tool calls)
├── pipeline.py             # §IV, §V-A — chain runner, agents, memory, delegation,
│                           #        pluggable reasoner, decision-driven oracle
├── agent_llm.py            # LLM reasoner (kimi-k2.5) with content-addressed record/replay
├── divergence.py           # §III, §V-D, §VI-C — the OFFLINE divergence instrument
├── embeddings.py           # stdlib loader for cached semantic embeddings (replay side)
├── embed_traces.py         # record-time encoder (model2vec, run under the 3.13 venv)
├── run_measurement.py      # deterministic/synthetic baseline driver (stdlib, offline)
├── run_llm_measurement.py  # §VI — real-agent driver, emits the pinned JSON
├── test_blindness.py       # nine tests pinning the paper's claims
├── traces/                 # committed record/replay cache (chat responses + emb/ vectors)
├── results/
│   ├── measurement_*.json           # deterministic baseline run
│   └── llm_measurement_*.json       # real-agent run cited from §VI
├── .env                    # MOONSHOT_API_KEY (git-ignored, never committed)
├── .venv/                  # 3.13 venv with model2vec (git-ignored)
└── README.md               # this file
```

## Two ways to run

**Deterministic path (stdlib, offline, no key).** Synthetic trace generators drive
the chain. Fast, reproducible, and the default for the test suite.

```
python3 test_blindness.py      # nine assertions pinning the claims
python3 run_measurement.py     # deterministic baseline + its pinned JSON
```

**Real-agent path (kimi-k2.5, record then replay).** Determinism comes from the
caches, not temperature: kimi-k2.5 forces temperature=1, so each recorded run is
pinned by its content-addressed trace and its cached embedding.

```
# 1. record chat traces (needs MOONSHOT_API_KEY; uses stdlib urllib)
set -a && . ./.env && set +a
LLM_MODE=auto python3 run_llm_measurement.py

# 2. embed the reasoning with the real encoder (needs model2vec, Python 3.13)
.venv/bin/python embed_traces.py

# 3. score, offline and key-free, from the committed caches
LLM_MODE=replay python3 run_llm_measurement.py
```

Steps 1 and 2 are one-time. With `traces/` committed, step 3 (and every §VI number)
replays with no key, no network, and stdlib only, the same record/replay stance the
conference-01 PoC took.

## The four gates (§II)

Each gate reads one property and answers one question. A compromised agent holds
every one of those properties, which is why none of the four can flag it. `gates.py`
makes that executable: every gate exposes `evaluate` (grant-time),
`evaluate_continuous` (re-check every phase), and `matched_violation` (a paired input
the gate MUST block, so a clean pass is a measurement and not a broken rig).

| Gate | Reads | Passes the compromise because |
|---|---|---|
| `SpiffeGate` | SVID against trust bundle | the SVID was issued to the workload, and the workload still runs |
| `ProvenanceGate` | artifact steps vs declared layout | the artifact did pass the declared steps; intent is outside the frame |
| `RbacGate` | the agent's **actual tool calls** vs the role's per-phase allowlist | the compromised agent picks only permitted tools (argument suffixes stripped before the check) |
| `MemoryGate` (AADS D2) | source class of the write | the tester is a trusted class, so its poison is admitted with authority |

## The compromise chain and its two roles (§IV)

`pipeline.py` drives `Test × Memory → Deploy × Delegation` with a pluggable reasoner
(synthetic by default, kimi-k2.5 via `make_llm_reasoner`). The threat model has two
distinct roles:

- **Compromised insider** (tester). An authorized agent under adversarial control.
  It applies the injected override and writes the poison to shared memory under its
  trusted source class. Its reasoning diverges from a clean tester's; its tool calls
  stay inside the allowlist.
- **Deceived victim** (deployer). Not compromised. It reads the poisoned entry as
  authoritative upstream state, resolves it, and ships it. It behaves like a clean
  deployer, which is why its divergence stays too shallow to gate on without stalling
  clean deploys.

A live modeling note the model itself forced: handed the raw injection, kimi-k2.5
recognizes and refuses it, flagging a supply-chain attack. So we posit the compromise
has succeeded and model the tester as already subverted, while the deployer is merely
misled. Refusal is recorded, but the object of study is what a *successful* compromise
looks like to the gates.

**The oracle is decision-driven.** A payload lands only if the tester actually calls
`write_memory` and the deployer actually calls `deploy`. A tester that declines to
write or a deployer that declines to ship yields no landing. On the real runs the
tester wrote in 12/12 and the deployer shipped in 12/12, so the compromise lands
100% of the time, earned from real decisions rather than a scripted flag (clean runs
show 28/30 deployers shipping, the variance that proves the oracle is not hardcoded).

## The divergence instrument (§III, §V-D) — read this part carefully

`divergence.py` is where the scope of the whole paper is decided. Its contract is
narrow and stated in the module docstring: it runs **after** the run, on the
**recorded** trace, and it gates **nothing**.

It maps each phase's reasoning text to a vector with a real static sentence encoder
(`potion-base-8M`, cached by `embed_traces.py` and read back through `embeddings.py`),
keeps the tool-call profile as a secondary channel, and builds a per-phase baseline
as the L2-normalized centroid over M clean runs. Divergence at a phase is the cosine
distance of a run's reasoning embedding from that centroid. The threshold is a
**deterministic function of the clean baseline alone** (`build_baseline_cosine`), the
95th percentile of the clean runs' own leave-one-out cosine distances, computed with
no access to any compromised run and recomputable from the committed clean traces, so
the line tracks how much benign behavior varies and cannot have been tuned to
the attack. A Jensen-Shannon divergence over the tool profiles rides alongside as a
metric-independent check.

The encoder runs only on the record path (Python 3.13 + model2vec); its vectors are
cached and committed, so the replay path and the deterministic tests stay stdlib-only.
When a reasoning text has no cached embedding (the synthetic path), the instrument
falls back to a feature-hash embedding, which keeps the offline tests deterministic.

## What the pinned run shows (§VI)

From `results/llm_measurement_2026-07-12.json`, over M=30 clean and 12 compromised
runs (B=3, K=4):

| Result | Value | Maps to |
|---|---|---|
| Every gate allows at every phase, one-shot | 4 gates, 0 detections | Table II, §VI-A |
| Every gate allows under continuous mode | detection count stays 0 | §VI-A, TOCTOU rebuttal |
| Each gate blocks its matched violation | 4/4 | §V-B negative controls |
| Oracle fires (payload lands), decision-driven | 100% of runs | §VI-B |
| Divergence onset | test phase, 12/12 runs, 2 phases upstream of deploy | §VI-C |
| Separation at the compromised tester (AUC) | 1.00, crosses 100% | §VI-C, finding 1 |
| Separation at the deceived deployer (AUC) | 0.87, crosses 50% (marginal) | §VI-C, finding 2 |
| Separation at the uninvolved build phase (AUC) | 0.54 (chance) | §VI-C control |
| JS over tool profiles | 0.33 at test, 0.06 at deploy | §VI-D mechanism |

The tester shifts both its reasoning and its tool profile (JS 0.33): a compromised
agent short-circuits toward its objective, though every tool it calls stays inside the
allowlist, so RBAC is satisfied. The deployer barely moves on either channel (JS 0.06,
cosine at the threshold): a deceived agent doing ordinary work on trusted data.

## What this PoC does *not* do

- No defense. No scoring of live actions, no revocation, no sidecar. The divergence
  instrument is read-only and a test enforces that. Article-02 owns the control.
- No breadth across the taxonomy. One conf-00 cell, run many times with varying CI
  context. The injected directive, payload, and framework are held fixed. The N ≥ 8
  benchmark across cells and frameworks is article-01's job.
- No claim about KMS compromise, SVID forgery, or broken provenance crypto. The attack
  lives entirely inside authorized behavior, and the result is sharper for excluding
  them.

The PoC proves the blind spot is real and repeatable across variants of one cell,
robust to enforcing and continuous gate modes, and shows where the behavioral signal
lives. It stops at the edge of the control that would close the gap.
