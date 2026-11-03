"""Record-time encoder: embed every cached reasoning trace with a real model.

Runs under Python 3.13 with model2vec (a static, CPU, distilled sentence embedding
— genuinely semantic, no torch). Reads the chat traces the pipeline recorded, parses
out each agent's reasoning text, and writes one vector per text into traces/emb/,
keyed by sha256(text). Those vectors are committed and read back by embeddings.py
under the stdlib runtime, so the divergence measurement never needs this dependency.

    .venv/bin/python embed_traces.py        # embed all reasoning in traces/

This is the encoder the paper's §V-D calls a "pinned sentence encoder." Pinning it
here means caching its output, so the vector is reproducible without re-running the
model.
"""

from __future__ import annotations

import hashlib
import json
import os

from model2vec import StaticModel

_HERE = os.path.dirname(os.path.abspath(__file__))
_TRACES = os.path.join(_HERE, "traces")
_EMB = os.path.join(_TRACES, "emb")
_MODEL = "minishlab/potion-base-8M"


def _reasoning_of(content: str) -> str | None:
    """Pull the reasoning field out of a recorded chat response, tolerating fences."""
    text = content.strip()
    if text.startswith("```"):
        text = text.split("```", 2)[1] if text.count("```") >= 2 else text.strip("`")
        text = text.lstrip("json").strip()
    try:
        return str(json.loads(text).get("reasoning", "")).strip() or None
    except (json.JSONDecodeError, AttributeError):
        return None


def main() -> None:
    os.makedirs(_EMB, exist_ok=True)
    model = StaticModel.from_pretrained(_MODEL)

    texts: set[str] = set()
    for fn in os.listdir(_TRACES):
        if not fn.endswith(".json"):
            continue
        with open(os.path.join(_TRACES, fn)) as fh:
            rec = json.load(fh)
        if "content" not in rec:
            continue
        r = _reasoning_of(rec["content"])
        if r:
            texts.add(r)

    new = 0
    for t in sorted(texts):
        key = hashlib.sha256(t.encode()).hexdigest()
        out = os.path.join(_EMB, key + ".json")
        if os.path.exists(out):
            continue
        vec = model.encode([t])[0].tolist()
        with open(out, "w") as fh:
            json.dump({"vec": vec, "model": _MODEL, "dim": len(vec)}, fh)
        new += 1

    print(f"embedded {len(texts)} unique reasoning texts ({new} new) -> {_EMB}")


if __name__ == "__main__":
    main()
