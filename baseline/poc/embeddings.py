"""Stdlib loader for cached semantic embeddings — the replay side of the encoder.

The real encoder (model2vec, a static sentence embedding) runs under Python 3.13 in
embed_traces.py and writes one vector per reasoning text into traces/emb/, keyed by
the sha256 of the text. This module, imported by divergence.py under the stdlib-only
runtime, only READS those cached vectors. So the measurement and a reviewer's replay
need neither the encoder, a model download, nor a key — the same record/replay stance
the chat cache takes. Miss returns None, and divergence.py falls back to its hash
embedding, which keeps the deterministic offline tests working unchanged.
"""

from __future__ import annotations

import hashlib
import json
import os

_HERE = os.path.dirname(os.path.abspath(__file__))
EMB_DIR = os.path.join(_HERE, "traces", "emb")


def text_key(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def load(text: str) -> list[float] | None:
    path = os.path.join(EMB_DIR, text_key(text) + ".json")
    if not os.path.exists(path):
        return None
    with open(path) as fh:
        return json.load(fh)["vec"]


def stats() -> dict:
    n = len([f for f in os.listdir(EMB_DIR) if f.endswith(".json")]) if os.path.isdir(EMB_DIR) else 0
    return {"cached_embeddings": n, "dir": EMB_DIR}
