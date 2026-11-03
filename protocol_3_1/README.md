# Instruction-only protocol 3.1

Read `AMENDMENT.md` for the exact change boundary. Protocol 3.0 sources, design and
failed batch are preserved. This directory adds clarified prompts and a development
collector that reuses the original executor/client/oracle without changing them.

From this directory:

```sh
python3 -B amendment.py
python3 -B -m unittest discover -s . -p 'test_*.py' -v
python3 -B run_development.py
python3 -B run_development.py --live --output ../results/protocol-3.1-development-001
```

All model calls are to the installed local Qwen model. No credits, downloads or
external deployments. A new output directory is mandatory; research splits are
disabled. Following an infrastructure interruption only, use `--resume` on that
same new-version evidence directory to continue unstarted cells without retries.

The frozen `snapshot-3.1/` inventory includes the exact prompts and unchanged
stimuli, schema and schedule. To reproduce the snapshot for audit in a NEW directory:

```sh
python3 -B amendment.py --export snapshot-audit
```

Results belong outside this frozen source directory. Do not edit source/docs after
freezing and silently reuse this version; amendment verification checks their hashes.
