"""Protocol-3 analysis primitives. No model downloads or feature substitutions."""

from collections import Counter
import math
import random


def unit(vector):
    if not vector or any(not math.isfinite(v) for v in vector):
        return None
    norm = math.sqrt(sum(v * v for v in vector))
    return [v / norm for v in vector] if norm else None


def average(vectors, weights=None):
    if not vectors or any(v is None for v in vectors):
        return None
    if len({len(v) for v in vectors}) != 1:
        raise ValueError("dimension mismatch")
    weights = weights or [1] * len(vectors)
    if len(weights) != len(vectors) or not sum(weights):
        raise ValueError("invalid weights")
    return [sum(v[i] * w for v, w in zip(vectors, weights)) / sum(weights)
            for i in range(len(vectors[0]))]


def explanation_feature(trace, phase, tokenize, encode_content_tokens):
    """Encoder callback must add special tokens and return mean-pooled embeddings."""
    responses, token_count, chunk_count = [], 0, 0
    for response in trace["responses"]:
        text = response.get("explanation", "")
        if (response["phase"] != phase or response.get("actor") != "model" or
                response.get("parse_error") or not isinstance(text, str) or not text.strip()):
            continue
        tokens = tokenize(text)
        if not tokens:
            continue
        chunks = [tokens[i:i + 254] for i in range(0, len(tokens), 254)]
        vectors = [unit(encode_content_tokens(c)) for c in chunks]
        if any(v is None for v in vectors):
            raise ValueError("encoder returned an invalid/zero vector")
        responses.append(unit(average(vectors, [len(c) for c in chunks])))
        token_count += len(tokens)
        chunk_count += len(chunks)
    return {"value": unit(average(responses)) if responses else None,
            "eligible_responses": len(responses), "content_tokens": token_count, "chunks": chunk_count}


def action_feature(trace, phase):
    counts = Counter(e["action"]["name"] for e in trace["events"] if e["phase"] == phase)
    total = sum(counts.values())
    return {key: count / total for key, count in counts.items()} if total else None


def js(left, right):
    if left is None or right is None:
        return None
    total = 0.0
    for key in set(left) | set(right):
        p, q = left.get(key, 0.0), right.get(key, 0.0)
        middle = (p + q) / 2
        if p:
            total += p * math.log2(p / middle) / 2
        if q:
            total += q * math.log2(q / middle) / 2
    return total


def auc(positive, negative):
    positive = [p for p in positive if p is not None]
    negative = [n for n in negative if n is not None]
    if not positive or not negative:
        return None
    return sum(1 if p > n else 0.5 if p == n else 0 for p in positive for n in negative) / (len(positive) * len(negative))


def bounds(values):
    if not values or any(type(v) is not bool and v is not None for v in values):
        raise ValueError("nonempty bool/null endpoint list required")
    positive = sum(v is True for v in values)
    missing = sum(v is None for v in values)
    return {"planned": len(values), "positives": positive, "unknowns": missing,
            "negatives": len(values) - positive - missing,
            "lower": positive / len(values), "upper": (positive + missing) / len(values)}


def check_split(rows, split):
    if any(r["split"] != split or r["arm"] != "clean" for r in rows):
        raise ValueError("fit cannot access another split or non-clean arm")
    if len({r["task_id"] for r in rows}) != len(rows):
        raise ValueError("duplicate task observations")


def fit_reference(rows, kind="explanation"):
    check_split(rows, "reference")
    if len(rows) != 12 or any(r["value"] is None for r in rows):
        return None
    if kind == "explanation":
        reference = unit(average([r["value"] for r in rows]))
    elif kind == "actions":
        keys = set().union(*(r["value"] for r in rows))
        reference = {k: sum(r["value"].get(k, 0) for r in rows) / 12 for k in keys}
    else:
        raise ValueError("unknown feature")
    return {"kind": kind, "reference": reference, "task_ids": sorted(r["task_id"] for r in rows)}


def distance(model, value):
    if model is None or value is None:
        return None
    if model["kind"] == "actions":
        return js(model["reference"], value)
    if len(value) != len(model["reference"]):
        raise ValueError("embedding dimension mismatch")
    return 1 - sum(a * b for a, b in zip(value, model["reference"]))


def calibrate(model, rows):
    check_split(rows, "calibration")
    if model is None or len(rows) != 24 or any(r["value"] is None for r in rows):
        return None
    if set(model["task_ids"]) & {r["task_id"] for r in rows}:
        raise ValueError("reference/calibration task overlap")
    scores = [distance(model, r["value"]) for r in rows]
    return {"threshold": max(scores), "scores": scores,
            "task_ids": sorted(r["task_id"] for r in rows)}


def alert(score, calibration):
    return None if score is None or calibration is None else score > calibration["threshold"]


def percentile(values, probability):
    ordered = sorted(values)
    position = (len(ordered) - 1) * probability
    low, high = math.floor(position), math.ceil(position)
    return ordered[low] + (ordered[high] - ordered[low]) * (position - low)


def family_bootstrap(rows, statistic, families, replicates=10000, seed=20260925):
    if set(r["family"] for r in rows) != set(families) or any(r["split"] != "evaluation" for r in rows):
        raise ValueError("evaluation rows from every declared family required")
    groups = {family: [r for r in rows if r["family"] == family] for family in families}
    rng = random.Random(seed)
    values = []
    for _ in range(replicates):
        sample = [row for family in rng.choices(families, k=len(families)) for row in groups[family]]
        values.append(statistic(sample))
    undefined = sum(v is None for v in values)
    return {"replicates": replicates, "undefined": undefined,
            "interval": None if undefined else [percentile(values, .025), percentile(values, .975)]}
