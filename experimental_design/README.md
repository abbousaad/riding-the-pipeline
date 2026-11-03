# Experimental design, protocol 3.0

Start with [PROTOCOL.md](PROTOCOL.md). It fixes the threat model, execution rules,
controls, sample size, outcomes, monitoring analysis and reporting boundaries.
[READINESS.md](READINESS.md) separates this completed design from the engineering
and validation required before collecting new research data.

The design uses one local Qwen generator, 66 synthetic contexts across four disjoint
splits, and 336 scheduled runs including 288 evaluation runs. There are three source
payloads, three matched benign controls, an authorized migration control, and a
separate assumed-compromised tester with a target-binding intervention. No second
generative model or API credit is required. The semantic monitoring instrument is
a pinned local MiniLM encoder; it is not downloaded by these tools.

The source/benign pairs differ only in the destination in their comment. Executor
binding is also tested on clean and authorized-migration tasks, not just attacks.
Repeated calls and template variants are not described as independent attacks.

## Offline commands

Run from this directory:

```sh
python3 -B design.py
python3 -B -m unittest discover -s . -p 'test_design.py' -v
python3 -B design.py --verify snapshot-3.0
```

The included `snapshot-3.0/` contains exact prompts/schema, 66 task definitions,
336 materialized stimuli, deterministic run order and SHA-256 hashes. Rebuilding
for audit must use a NEW output directory:

```sh
python3 -B design.py --export snapshot-audit
```

The exporter refuses to overwrite existing directories and makes no network/model
calls. `--verify` checks hashes and regenerates inventory contents in memory to
check reproducibility. It does not validate a live experiment or implement the
new runner. Do not feed the study config to the old pilot CLI.

No old evidence or manuscript files are changed by this design package. The main
experiment is intentionally not launched as part of experimental-design work.
