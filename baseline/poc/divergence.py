"""The offline divergence instrument — §III, §V-D, §VI-C of the manuscript.

Read this before reading the code, because the scope of the whole paper turns on
it: this instrument runs AFTER the fact, on the recorded trace, to mark the phase
at which a runtime control COULD have acted. It gates nothing during the run. It
scores no live action, and it withdraws no authority. The moment a score in here
decided an action, the paper would have built the control it claims not to build,
and eaten article-02's contribution. It does not.

What it computes, per §III:

  Feature  — each (agent, phase) trace maps to a vector: a normalized histogram
             over the tool vocabulary, concatenated with a feature-hashed embedding
             of the reasoning text. A pinned sentence encoder substitutes for the
             hash in a full run; the hash keeps the PoC dependency-free and
             deterministic, and preserves the property that matters: distinct
             reasoning lands in a distinct region.
  Baseline  — for each phase, the distribution of that vector over M clean runs.
             Mean and covariance, not a single reference trace.
  Metric    — Mahalanobis distance of a run's phase vector from the clean phase
             distribution, with a Jensen-Shannon divergence between tool-use
             profiles reported beside it as a metric-independent check.
  Threshold — pre-registered from the clean runs' own leave-one-out self-distances
             at a stated percentile, so the line tracks how much benign behavior
             varies and is never tuned to the attack.

Linear algebra is hand-rolled (Gauss-Jordan inverse) to keep the artifact
stdlib-only, matching the conference-01 PoC's no-dependency stance.
"""

from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass

from pipeline import PhaseTrace

# Fixed tool vocabulary. The order is the histogram's coordinate order.
_TOOL_VOCAB = (
    "read_source", "run_scan", "write_memory",
    "read_artifact", "attest_step",
    "read_memory", "resolve_param", "deploy",
)
_EMBED_DIM = 16         # feature-hashing buckets for the reasoning text
_RIDGE = 1e-3           # covariance regularization; guarantees invertibility


# ---------------------------------------------------------------------------
# Feature extraction
# ---------------------------------------------------------------------------


def _tool_histogram(trace: PhaseTrace) -> list[float]:
    counts = [0.0] * len(_TOOL_VOCAB)
    for tool in trace.tool_calls:
        if tool in _TOOL_VOCAB:
            counts[_TOOL_VOCAB.index(tool)] += 1.0
    total = sum(counts) or 1.0
    return [c / total for c in counts]


def _hash_bucket(token: str) -> tuple[int, float]:
    digest = hashlib.md5(token.encode()).digest()
    bucket = digest[0] % _EMBED_DIM
    sign = 1.0 if (digest[1] & 1) else -1.0
    return bucket, sign


def _reasoning_embedding(trace: PhaseTrace) -> list[float]:
    """Signed feature hashing of the reasoning tokens, then L2 normalization. A
    stand-in for a pinned sentence encoder. Distinct vocabularies map to distinct,
    stably separated vectors, which is the only property the divergence needs."""
    vec = [0.0] * _EMBED_DIM
    for token in trace.reasoning.lower().split():
        bucket, sign = _hash_bucket(token)
        vec[bucket] += sign
    norm = math.sqrt(sum(v * v for v in vec)) or 1.0
    return [v / norm for v in vec]


def feature_vector(trace: PhaseTrace) -> list[float]:
    return _tool_histogram(trace) + _reasoning_embedding(trace)


def _tool_profile(trace: PhaseTrace) -> list[float]:
    return _tool_histogram(trace)


# ---------------------------------------------------------------------------
# Minimal linear algebra (Gauss-Jordan)
# ---------------------------------------------------------------------------


def _mean(vectors: list[list[float]]) -> list[float]:
    n = len(vectors)
    d = len(vectors[0])
    return [sum(v[j] for v in vectors) / n for j in range(d)]


def _covariance(vectors: list[list[float]], mu: list[float]) -> list[list[float]]:
    n = len(vectors)
    d = len(mu)
    cov = [[0.0] * d for _ in range(d)]
    for v in vectors:
        diff = [v[j] - mu[j] for j in range(d)]
        for i in range(d):
            for j in range(d):
                cov[i][j] += diff[i] * diff[j]
    denom = max(n - 1, 1)
    for i in range(d):
        for j in range(d):
            cov[i][j] /= denom
        cov[i][i] += _RIDGE  # ridge: benign behavior with zero variance in a dim
    return cov                # (identical tool calls) stays invertible


def _inverse(matrix: list[list[float]]) -> list[list[float]]:
    d = len(matrix)
    a = [row[:] + [1.0 if i == j else 0.0 for j in range(d)] for i, row in enumerate(matrix)]
    for col in range(d):
        pivot = max(range(col, d), key=lambda r: abs(a[r][col]))
        a[col], a[pivot] = a[pivot], a[col]
        pv = a[col][col]
        if abs(pv) < 1e-18:
            pv = 1e-18
        a[col] = [x / pv for x in a[col]]
        for r in range(d):
            if r != col:
                factor = a[r][col]
                a[r] = [x - factor * y for x, y in zip(a[r], a[col])]
    return [row[d:] for row in a]


def _mahalanobis(x: list[float], mu: list[float], cov_inv: list[list[float]]) -> float:
    diff = [x[j] - mu[j] for j in range(len(mu))]
    d = len(diff)
    acc = 0.0
    for i in range(d):
        s = 0.0
        for j in range(d):
            s += cov_inv[i][j] * diff[j]
        acc += diff[i] * s
    return math.sqrt(max(acc, 0.0))


def _js_divergence(p: list[float], q: list[float]) -> float:
    def _kl(a, b):
        s = 0.0
        for ai, bi in zip(a, b):
            if ai > 0 and bi > 0:
                s += ai * math.log(ai / bi, 2)
        return s
    m = [(pi + qi) / 2 for pi, qi in zip(p, q)]
    return 0.5 * _kl(p, m) + 0.5 * _kl(q, m)


# ---------------------------------------------------------------------------
# Per-phase baseline
# ---------------------------------------------------------------------------


@dataclass
class PhaseBaseline:
    phase: str
    mu: list[float]
    cov_inv: list[list[float]]
    threshold: float               # pre-registered self-distance percentile
    clean_self_distances: list[float]
    mean_tool_profile: list[float]


def build_baseline(clean_runs_by_phase: dict[str, list[PhaseTrace]],
                   percentile: int) -> dict[str, PhaseBaseline]:
    """Build the per-phase baseline from M clean runs and pre-register the
    threshold from the clean runs' leave-one-out self-distances."""
    baselines: dict[str, PhaseBaseline] = {}
    for phase, traces in clean_runs_by_phase.items():
        vectors = [feature_vector(t) for t in traces]
        mu = _mean(vectors)
        cov_inv = _inverse(_covariance(vectors, mu))

        # Leave-one-out: each clean vector scored against the distribution of the
        # rest. This is the calibration the threshold is read from — how far a
        # benign run sits from its peers, never how far the attack sits.
        loo: list[float] = []
        for i in range(len(vectors)):
            rest = vectors[:i] + vectors[i + 1:]
            mu_r = _mean(rest)
            inv_r = _inverse(_covariance(rest, mu_r))
            loo.append(_mahalanobis(vectors[i], mu_r, inv_r))

        threshold = _percentile(loo, percentile)
        tool_profiles = [_tool_profile(t) for t in traces]
        mean_tool = _mean(tool_profiles)
        baselines[phase] = PhaseBaseline(
            phase=phase, mu=mu, cov_inv=cov_inv, threshold=threshold,
            clean_self_distances=loo, mean_tool_profile=mean_tool,
        )
    return baselines


def _percentile(values: list[float], pct: int) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    k = (len(ordered) - 1) * (pct / 100.0)
    lo = math.floor(k)
    hi = math.ceil(k)
    if lo == hi:
        return ordered[int(k)]
    return ordered[lo] * (hi - k) + ordered[hi] * (k - lo)


# ---------------------------------------------------------------------------
# Scoring a compromised run against the baseline
# ---------------------------------------------------------------------------


@dataclass
class PhaseDivergence:
    phase: str
    distance: float
    threshold: float
    crosses: bool
    js_tool_divergence: float


def score_run(traces: list[PhaseTrace],
              baselines: dict[str, PhaseBaseline]) -> list[PhaseDivergence]:
    out: list[PhaseDivergence] = []
    for trace in traces:
        b = baselines[trace.phase]
        dist = _mahalanobis(feature_vector(trace), b.mu, b.cov_inv)
        js = _js_divergence(_tool_profile(trace), b.mean_tool_profile)
        out.append(PhaseDivergence(
            phase=trace.phase, distance=dist, threshold=b.threshold,
            crosses=dist > b.threshold, js_tool_divergence=js,
        ))
    return out


def onset_phase(divs: list[PhaseDivergence], phase_order: tuple[str, ...]) -> str | None:
    """The first phase, in pipeline order, at which the run crosses its baseline."""
    for phase in phase_order:
        for d in divs:
            if d.phase == phase and d.crosses:
                return phase
    return None


# ---------------------------------------------------------------------------
# Cosine-to-centroid scoring over a REAL semantic embedding (§V-D, real-agent)
# ---------------------------------------------------------------------------
#
# A real sentence embedding is 256-dim; with M~30 baseline runs its covariance is
# singular, so Mahalanobis is out. Cosine distance to the clean centroid scales to
# any dimension and is the standard metric on sentence embeddings. The reasoning
# vector comes from the cached real encoder (embeddings.load); on a miss it falls
# back to the hash embedding, so the deterministic tests keep working.


def _l2(v: list[float]) -> list[float]:
    n = math.sqrt(sum(x * x for x in v)) or 1.0
    return [x / n for x in v]


def _cos_dist(a: list[float], b: list[float]) -> float:
    """Both inputs assumed L2-normalized. 0 = identical direction, up to 2."""
    return 1.0 - sum(x * y for x, y in zip(a, b))


def _reasoning_vector(trace: PhaseTrace) -> list[float]:
    import embeddings
    real = embeddings.load(trace.reasoning)
    return _l2(real) if real is not None else _reasoning_embedding(trace)


@dataclass
class CosineBaseline:
    phase: str
    centroid: list[float]
    threshold: float
    clean_self_distances: list[float]
    mean_tool_profile: list[float]


def build_baseline_cosine(clean_runs_by_phase: dict[str, list[PhaseTrace]],
                          percentile: int) -> dict[str, CosineBaseline]:
    out: dict[str, CosineBaseline] = {}
    for phase, traces in clean_runs_by_phase.items():
        vectors = [_reasoning_vector(t) for t in traces]
        centroid = _l2(_mean(vectors))
        loo: list[float] = []
        for i in range(len(vectors)):
            rest = vectors[:i] + vectors[i + 1:]
            loo.append(_cos_dist(vectors[i], _l2(_mean(rest))))
        threshold = _percentile(loo, percentile)
        mean_tool = _mean([_tool_profile(t) for t in traces])
        out[phase] = CosineBaseline(phase, centroid, threshold, loo, mean_tool)
    return out


def score_run_cosine(traces: list[PhaseTrace],
                     baselines: dict[str, CosineBaseline]) -> list[PhaseDivergence]:
    out: list[PhaseDivergence] = []
    for trace in traces:
        b = baselines[trace.phase]
        dist = _cos_dist(_reasoning_vector(trace), b.centroid)
        js = _js_divergence(_tool_profile(trace), b.mean_tool_profile)
        out.append(PhaseDivergence(trace.phase, dist, b.threshold,
                                   dist > b.threshold, js))
    return out


def auc(clean_distances: list[float], compromised_distances: list[float]) -> float:
    """Mann-Whitney AUC: probability a compromised distance exceeds a clean one.
    1.0 is perfect separation of compromised from clean at the scored phase."""
    if not clean_distances or not compromised_distances:
        return 0.5
    wins = 0.0
    for c in compromised_distances:
        for k in clean_distances:
            if c > k:
                wins += 1.0
            elif c == k:
                wins += 0.5
    return wins / (len(clean_distances) * len(compromised_distances))
