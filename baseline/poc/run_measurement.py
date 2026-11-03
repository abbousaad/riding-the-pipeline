"""Drive the measurement and emit the numbers §VI reports.

Budget, per §V: M clean runs build the per-phase baseline; B instantiations of the
chain, each replayed K times, produce the gate-pass rate and the divergence timing
with a denominator. Every gate runs one-shot and continuous. Each gate's matched
negative control runs too, to confirm the rig blocks a real violation.

Output: a human-readable console report plus a pinned JSON under results/, keyed by
the source fingerprints of the rig, in the shape the conference-01 PoC established.

Run:  python3 run_measurement.py
"""

from __future__ import annotations

import hashlib
import json
import platform
import statistics
import sys
from datetime import date

import divergence as dv
import gates as gt
import pipeline as pl

M_CLEAN = 60          # baseline runs per phase
B_INSTANCES = 5       # distinct attack instantiations (varied injection seeds)
K_REPLAYS = 20        # replays per instantiation
THRESHOLD_PCT = 95    # pre-registered self-distance percentile
PHASE_ORDER = pl._PHASE_ORDER


# ---------------------------------------------------------------------------
# Gate measurement
# ---------------------------------------------------------------------------


def measure_gates(runs: list[pl.RunResult]) -> dict:
    """Every gate against every phase of every compromised run, one-shot and
    continuous. Plus each gate's matched violation. Returns the §VI-A matrix."""
    matrix: dict[str, dict] = {}
    for gate in gt.ALL_GATES:
        per_phase_allow = {ph: True for ph in PHASE_ORDER}
        per_phase_applicable = {ph: False for ph in PHASE_ORDER}
        any_anomaly = False
        continuous_allow = True

        for run in runs:
            # One-shot: the grant-time decision at each phase.
            for ev in run.gate_events:
                d = gate.evaluate(ev)
                # The memory gate is n/a in phases with no write; skip those from
                # the "applicable" set so the matrix reads honestly.
                applicable = not (gate.name == "memory_gate" and ev.source_class is None)
                if applicable:
                    per_phase_applicable[ev.phase] = True
                    per_phase_allow[ev.phase] &= d.allow
                    any_anomaly |= d.anomaly
            # Continuous: re-check at every phase.
            for d in gate.evaluate_continuous(run.gate_events):
                if not (gate.name == "memory_gate" and d.reason == "no memory write in phase"):
                    continuous_allow &= d.allow

        # Negative control: the matched violation MUST block.
        viol = gate.evaluate(gate.matched_violation(PHASE_ORDER[-1]))
        matrix[gate.name] = {
            "per_phase": {
                ph: ("allow" if per_phase_allow[ph] else "block") if per_phase_applicable[ph] else "n/a"
                for ph in PHASE_ORDER
            },
            "anomaly_raised": any_anomaly,
            "allow_continuous_mode": continuous_allow,
            "blocks_matched_violation": (not viol.allow),
        }
    return matrix


# ---------------------------------------------------------------------------
# Divergence measurement
# ---------------------------------------------------------------------------


def measure_divergence(baselines: dict[str, dv.PhaseBaseline],
                       compromised: list[pl.RunResult]) -> dict:
    per_run_divs = [dv.score_run(r.traces, baselines) for r in compromised]

    onsets = [dv.onset_phase(divs, PHASE_ORDER) for divs in per_run_divs]
    onset_dist = {ph: onsets.count(ph) for ph in PHASE_ORDER}
    onset_dist["none"] = onsets.count(None)

    # Per-phase compromised distances, with bootstrap-free CI via stdev.
    phase_distance = {}
    for ph in PHASE_ORDER:
        vals = [d.distance for divs in per_run_divs for d in divs if d.phase == ph]
        phase_distance[ph] = {
            "mean": statistics.mean(vals),
            "stdev": statistics.pstdev(vals),
            "threshold": baselines[ph].threshold,
            "crosses_rate": sum(1 for v in vals if v > baselines[ph].threshold) / len(vals),
            "js_tool_divergence_mean": statistics.mean(
                d.js_tool_divergence for divs in per_run_divs for d in divs if d.phase == ph
            ),
        }

    # AUC at the onset phase: clean self-distances vs compromised distances.
    onset = next((ph for ph in PHASE_ORDER if onset_dist.get(ph, 0) > 0), PHASE_ORDER[0])
    clean_self = baselines[onset].clean_self_distances
    comp_at_onset = [d.distance for divs in per_run_divs for d in divs if d.phase == onset]
    onset_auc = dv.auc(clean_self, comp_at_onset)

    onset_idx = PHASE_ORDER.index(onset)
    deploy_idx = PHASE_ORDER.index("deploy")

    return {
        "onset_phase": onset,
        "onset_phase_distribution": onset_dist,
        "phases_upstream_of_deploy": deploy_idx - onset_idx,
        "auc_at_onset": onset_auc,
        "per_phase_distance": phase_distance,
        "blind_window_phases": deploy_idx - onset_idx,
    }


# ---------------------------------------------------------------------------
# Sensitivity (§VI-D)
# ---------------------------------------------------------------------------


def measure_sensitivity(clean_by_phase, compromised) -> dict:
    """The onset persists across a sweep of the threshold percentile. A control
    that has no predicate over behavior is not given one by a tighter setting."""
    out = {}
    for pct in (90, 95, 97, 99):
        b = dv.build_baseline(clean_by_phase, pct)
        divs = [dv.score_run(r.traces, b) for r in compromised]
        onsets = [dv.onset_phase(d, PHASE_ORDER) for d in divs]
        dominant = max(set(onsets), key=onsets.count) if onsets else None
        out[str(pct)] = {
            "onset_phase": dominant,
            "onset_test_rate": onsets.count("test") / len(onsets) if onsets else 0.0,
        }
    return out


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------


def main() -> None:
    # Baseline: M clean runs, regrouped by phase.
    clean_runs = [pl.run_chain(seed=1000 + i, poisoned=False) for i in range(M_CLEAN)]
    clean_by_phase = {
        ph: [tr for r in clean_runs for tr in r.traces if tr.phase == ph]
        for ph in PHASE_ORDER
    }
    baselines = dv.build_baseline(clean_by_phase, THRESHOLD_PCT)

    # Attack: B instantiations x K replays. Instantiation varies the injection seed
    # base; replay varies the per-run seed within it.
    compromised: list[pl.RunResult] = []
    for b in range(B_INSTANCES):
        for k in range(K_REPLAYS):
            compromised.append(pl.run_chain(seed=90000 + b * 1000 + k, poisoned=True))

    gate_matrix = measure_gates(compromised)
    div = measure_divergence(baselines, compromised)
    sens = measure_sensitivity(clean_by_phase, compromised)

    oracle_fire_rate = sum(1 for r in compromised if r.payload_landed) / len(compromised)
    dwell = statistics.mean(r.patient_dwell_phases for r in compromised)

    report = {
        "generated": date.today().isoformat(),
        "budget": {"M_clean": M_CLEAN, "B_instances": B_INSTANCES,
                   "K_replays": K_REPLAYS, "total_compromised_runs": len(compromised),
                   "threshold_percentile": THRESHOLD_PCT},
        "gate_matrix": gate_matrix,
        "reach": {
            "oracle_fire_rate": oracle_fire_rate,
            "mean_patient_dwell_phases": dwell,
            "phases_traversed_post_poison": int(dwell),
        },
        "divergence": div,
        "sensitivity": sens,
        "fingerprint": {
            "pipeline_sha256": pl.run_fingerprint(),
            "gates_sha256": _sha(gt.__file__),
            "divergence_sha256": _sha(dv.__file__),
            "platform": platform.platform(),
            "python": sys.version.split()[0],
        },
    }

    _print_report(report)
    out_path = f"results/measurement_{report['generated']}.json"
    with open(_here(out_path), "w") as fh:
        json.dump(report, fh, indent=2)
    print(f"\nPinned run written to {out_path}")


def _sha(path: str) -> str:
    with open(path, "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()


def _here(rel: str) -> str:
    import os
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), rel)


def _print_report(r: dict) -> None:
    print("=" * 72)
    print("Riding the Pipeline — measurement rig (conference-02 PoC)")
    print("=" * 72)
    b = r["budget"]
    print(f"\nBudget: M={b['M_clean']} clean/phase, B={b['B_instances']} x "
          f"K={b['K_replays']} = {b['total_compromised_runs']} compromised runs\n")

    print("Table II — per-gate, per-phase decision (compromise chain)")
    print(f"  {'gate':<16} {'test':>7} {'build':>7} {'deploy':>7} "
          f"{'anomaly':>8} {'cont.':>7} {'blocks viol.':>13}")
    for name, row in r["gate_matrix"].items():
        pp = row["per_phase"]
        print(f"  {name:<16} {pp['test']:>7} {pp['build']:>7} {pp['deploy']:>7} "
              f"{str(row['anomaly_raised']):>8} "
              f"{('allow' if row['allow_continuous_mode'] else 'block'):>7} "
              f"{str(row['blocks_matched_violation']):>13}")

    reach = r["reach"]
    print(f"\nReach: oracle fires on {reach['oracle_fire_rate']*100:.0f}% of runs; "
          f"payload travels {reach['phases_traversed_post_poison']} phase(s) "
          f"post-poison (dwell {reach['mean_patient_dwell_phases']:.1f} phases).")

    d = r["divergence"]
    print(f"\nDivergence onset: {d['onset_phase']} "
          f"({d['phases_upstream_of_deploy']} phase(s) upstream of deploy), "
          f"AUC at onset {d['auc_at_onset']:.3f}")
    print("  per-phase Mahalanobis distance vs pre-registered threshold:")
    for ph, s in d["per_phase_distance"].items():
        mark = "CROSSES" if s["crosses_rate"] > 0.5 else "within baseline"
        print(f"    {ph:<7} dist={s['mean']:.2f}±{s['stdev']:.2f} "
              f"thr={s['threshold']:.2f} JS(tools)={s['js_tool_divergence_mean']:.3f} "
              f"-> {mark} ({s['crosses_rate']*100:.0f}% of replays)")

    print("\nSensitivity: onset phase across threshold sweep")
    for pct, s in r["sensitivity"].items():
        print(f"    pct={pct}: onset={s['onset_phase']} "
              f"(test-phase onset on {s['onset_test_rate']*100:.0f}% of replays)")


if __name__ == "__main__":
    main()
