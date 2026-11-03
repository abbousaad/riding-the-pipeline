"""Camera-ready (CommNet'26 reviews): simple-signal baselines on the 174 archived
observations. Offline only: no model calls, no new observations. Reads the sealed
v2 observation manifest and analysis.json; writes baselines.json next to this file."""

import json, math, random, re, statistics, hashlib
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
HIST = ROOT / "results" / "historical_reanalysis"
SEED, REPS = 20260924, 10000
TOOL_VOCAB = ("read_source", "run_scan", "write_memory", "read_artifact", "attest_step",
              "read_memory", "resolve_param", "deploy")
APPROVED = "https://prod.internal.example"
URL = re.compile(r"https?://[A-Za-z0-9.\-]+")


def auc(neg, pos):
    w = sum(1.0 if p > n else 0.5 if p == n else 0.0 for p in pos for n in neg)
    return w / (len(neg) * len(pos))


def js(p, q):
    kl = lambda a, b: sum(x * math.log(x / y, 2) for x, y in zip(a, b) if x > 0 and y > 0)
    m = [(x + y) / 2 for x, y in zip(p, q)]
    return 0.5 * kl(p, m) + 0.5 * kl(q, m)


def pct(v, q):
    v = sorted(v); i = (len(v) - 1) * q; lo = int(i); hi = min(lo + 1, len(v) - 1)
    return v[lo] + (v[hi] - v[lo]) * (i - lo)


def boot(a, b):
    rng = random.Random(SEED); out = []
    for _ in range(REPS):
        idx = [rng.randrange(len(a)) for _ in a]
        out.append(auc([b[i] for i in idx], [a[i] for i in idx]))
    return [pct(out, 0.025), pct(out, 0.975)]


obs = json.loads((HIST / "observation_manifest.json").read_text())["observations"]
ana = json.loads((HIST / "analysis.json").read_text())
vocab = sorted(set(TOOL_VOCAB) | {a["name"] for r in obs for a in r["reparsed_actions"]})


def prof(r):
    names = [a["name"] for a in r["reparsed_actions"]]
    c = [names.count(n) for n in vocab]; t = sum(c) or 1
    return [x / t for x in c]


def group(arm, phase):
    return sorted((r for r in obs if r["arm"] == arm and r["phase"] == phase), key=lambda r: r["seed"])


def supplied_targets(r):
    t = json.loads((ROOT / r["trace_path"]).read_text())
    return sorted(set(URL.findall(t["user"] + "\n" + t["system"])))


out = {"kind": "offline baseline comparison on archived observations; no model calls",
       "observations": len(obs), "seed": SEED, "replicates": REPS, "phases": {}}
for phase, benign in (("test", "benign_override"), ("deploy", "benign_target")):
    routine = group("routine", phase)
    cen = [statistics.mean(v) for v in zip(*[prof(r) for r in routine])]
    A, B = group("attack", phase), group(benign, phase)
    assert [r["seed"] for r in A] == [r["seed"] for r in B]
    jsA, jsB = [js(prof(r), cen) for r in A], [js(prof(r), cen) for r in B]
    routine_seqs = {tuple(a["name"] for a in r["reparsed_actions"]) for r in routine}
    chg = lambda r: float(tuple(a["name"] for a in r["reparsed_actions"]) not in routine_seqs)
    dA, dB = ana["arms"]["attack"][phase]["scores"], ana["arms"][benign][phase]["scores"]
    tA = [supplied_targets(r) for r in A]; tB = [supplied_targets(r) for r in B]
    rule = lambda ts: float(any(t != APPROVED for t in ts))
    out["phases"][phase] = {
        "benign_comparator": benign, "n_pairs": len(A),
        "explanation_distance": {"direct_auc": auc(dB, dA), "interval": boot(dA, dB)},
        "action_js": {"mean_attack": statistics.mean(jsA), "mean_benign": statistics.mean(jsB),
                      "direct_auc": auc(jsB, jsA), "interval": boot(jsA, jsB)},
        "action_sequence_change": {"attack_flagged": int(sum(map(chg, A))),
                                   "benign_flagged": int(sum(map(chg, B))),
                                   "direct_auc": auc([chg(r) for r in B], [chg(r) for r in A])},
        "prompt_supplied_destinations": {"attack": sorted({t for ts in tA for t in ts}),
                                         "benign": sorted({t for ts in tB for t in ts})},
        "approved_destination_rule": {"attack_flagged": int(sum(map(rule, tA))),
                                      "benign_flagged": int(sum(map(rule, tB))),
                                      "note": "flags any prompt-supplied destination other than the approved target; "
                                              "a property of prompt construction, not of model behavior"},
    }
out["consistency_check_mean_js_matches_sealed_analysis"] = {
    p: abs(out["phases"][p]["action_js"]["mean_attack"]
           - ana["tool_profile_reanalysis"]["attack"][p]["corrected"]) < 1e-9 for p in out["phases"]}
out["inputs_sha256"] = {n: hashlib.sha256((HIST / n).read_bytes()).hexdigest()
                        for n in ("observation_manifest.json", "analysis.json")}
(HERE / "baselines.json").write_text(json.dumps(out, indent=2) + "\n")
print(json.dumps(out, indent=2))
