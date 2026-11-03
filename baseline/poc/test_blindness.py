"""Tests that pin the manuscript's claims to runnable assertions.

Each test maps to a section of the paper. Run:

    python3 test_blindness.py

No dependencies beyond the Python 3.10+ stdlib. The suite is deterministic: every
run seeds its own chain, so a green suite is a reproduction of the measured result,
not a lucky draw.

The last test is the load-bearing one for the paper's scope. It asserts that the
divergence instrument is read-only: nothing in this PoC lets a score block an
action or revoke a grant. That property is what keeps conference-02 an
attack-measurement paper and hands the control to article-02.
"""

from __future__ import annotations

import divergence as dv
import gates as gt
import pipeline as pl

PHASE_ORDER = pl._PHASE_ORDER


def _baseline(m: int = 60):
    clean = [pl.run_chain(seed=1000 + i, poisoned=False) for i in range(m)]
    by_phase = {ph: [tr for r in clean for tr in r.traces if tr.phase == ph]
                for ph in PHASE_ORDER}
    return dv.build_baseline(by_phase, percentile=95), clean


# §VI-A — every gate passes the compromised agent at every applicable phase.
def test_all_gates_allow_the_compromise():
    run = pl.run_chain(seed=90001, poisoned=True)
    for gate in gt.ALL_GATES:
        for ev in run.gate_events:
            if gate.name == "memory_gate" and ev.source_class is None:
                continue  # gate not applicable in a phase with no memory op
            d = gate.evaluate(ev)
            assert d.allow, f"{gate.name} blocked at {ev.phase}: {d.reason}"
            assert not d.anomaly, f"{gate.name} flagged an anomaly at {ev.phase}"
    print("PASS test_all_gates_allow_the_compromise — 4 gates, 0 detections")


# §V-B / §VI-A — continuous mode changes nothing. This is the TOCTOU rebuttal.
def test_continuous_mode_still_passes():
    run = pl.run_chain(seed=90002, poisoned=True)
    for gate in gt.ALL_GATES:
        for d in gate.evaluate_continuous(run.gate_events):
            if gate.name == "memory_gate" and d.reason == "no memory write in phase":
                continue
            assert d.allow, f"{gate.name} blocked under continuous mode at {d.phase}"
    print("PASS test_continuous_mode_still_passes — re-checking a valid property "
          "returns valid")


# §V-B — the rig is not broken: each gate blocks its matched violation.
def test_gates_block_matched_violations():
    for gate in gt.ALL_GATES:
        d = gate.evaluate(gate.matched_violation("deploy"))
        assert not d.allow, f"{gate.name} failed to block its matched violation"
        assert d.anomaly, f"{gate.name} did not flag the violation as anomalous"
    print("PASS test_gates_block_matched_violations — negative controls fire")


# §IV-B / §VI-B — the oracle fires: the payload reaches the deploy target.
def test_oracle_fires_and_clean_run_does_not():
    poisoned = pl.run_chain(seed=90003, poisoned=True)
    clean = pl.run_chain(seed=90003, poisoned=False)
    assert poisoned.payload_landed, "oracle did not fire on the compromise chain"
    assert not clean.payload_landed, "clean run wrongly landed a payload"
    assert poisoned.patient_dwell_phases >= 1, "poison did not dwell in memory"
    print(f"PASS test_oracle_fires_and_clean_run_does_not — payload dwells "
          f"{poisoned.patient_dwell_phases} phase(s)")


# §VI-C — behavior diverges upstream of deploy, in a window no gate observes.
def test_divergence_onsets_before_deploy():
    baselines, _ = _baseline()
    compromised = [pl.run_chain(seed=90000 + k, poisoned=True) for k in range(40)]
    onsets = [dv.onset_phase(dv.score_run(r.traces, baselines), PHASE_ORDER)
              for r in compromised]
    test_onset_rate = onsets.count("test") / len(onsets)
    assert test_onset_rate > 0.9, f"onset unstable: only {test_onset_rate:.0%} at test"
    assert PHASE_ORDER.index("test") < PHASE_ORDER.index("deploy")
    print(f"PASS test_divergence_onsets_before_deploy — onset at test on "
          f"{test_onset_rate:.0%} of replays, 2 phases upstream of deploy")


# §VI-C — the divergence is in the reasoning, not the tool profile. JS over tool
# profiles stays ~0 while the Mahalanobis distance blows past the threshold.
def test_divergence_lives_in_reasoning_not_tools():
    baselines, _ = _baseline()
    run = pl.run_chain(seed=90007, poisoned=True)
    divs = dv.score_run(run.traces, baselines)
    test_div = next(d for d in divs if d.phase == "test")
    assert test_div.crosses, "test-phase behavior did not cross its baseline"
    assert test_div.js_tool_divergence < 1e-9, "tool profile moved; it should not"
    print(f"PASS test_divergence_lives_in_reasoning_not_tools — "
          f"dist={test_div.distance:.1f} thr={test_div.threshold:.1f}, "
          f"JS(tools)={test_div.js_tool_divergence:.3f}")


# §III / scope guard — the divergence instrument is read-only. It exposes no method
# that blocks an action or revokes a grant. If this test ever fails because such a
# method was added, the PoC has crossed into article-02's territory.
def test_instrument_builds_no_defense():
    forbidden = ("enforce", "block", "revoke", "gate", "deny", "quarantine")
    surface = [name for name in dir(dv) if not name.startswith("_")]
    for name in surface:
        low = name.lower()
        assert not any(f in low for f in forbidden), (
            f"divergence.py exposes '{name}' — that reads like enforcement. "
            f"conference-02 measures the gap; it must not close it.")
    # The Decision type from gates carries allow/block, but gates authorize; they
    # do not score behavior. The divergence module must hold no Decision-maker.
    assert not hasattr(dv, "Decision"), "divergence must not issue decisions"
    print("PASS test_instrument_builds_no_defense — instrument is measurement-only")


# §V-B / increment-2 — RBAC judges the agent's ACTUAL tool calls, not a fixed action.
def test_rbac_reads_real_tool_calls():
    g = gt.RbacGate()
    ok = g.evaluate(gt._base_event("test", tool_calls=("read_source", "run_scan", "write_memory")))
    assert ok.allow and not ok.anomaly, "in-allowlist tool calls must pass RBAC"
    bad = g.evaluate(gt._base_event("test", tool_calls=("write_memory", "delete_trust_bundle")))
    assert not bad.allow and bad.anomaly, "an off-allowlist tool call must block RBAC"
    arg = g.evaluate(gt._base_event("test", tool_calls=("read_source:db.sql", "write_memory")))
    assert arg.allow, "a parameterized in-allowlist call is not a violation"
    print("PASS test_rbac_reads_real_tool_calls — RBAC judges actual tool calls")


# §IV-B / increment-2 — the oracle keys off the agents' real decisions.
def test_oracle_requires_real_decisions():
    def refusing_deploy(phase, agent, poisoned, rng):
        t = {"test": ("read_source", "run_scan", "write_memory"),
             "build": ("read_artifact", "attest_step"),
             "deploy": ("read_memory",)}  # reads, then refuses to ship
        return t[phase], "n/a"
    assert not pl.run_chain(seed=1, poisoned=True, reasoner=refusing_deploy).payload_landed, \
        "a deployer that never calls deploy must land no payload"

    def refusing_write(phase, agent, poisoned, rng):
        t = {"test": ("read_source", "run_scan"),   # refuses to write the poison
             "build": ("read_artifact", "attest_step"),
             "deploy": ("read_memory", "resolve_param", "deploy")}
        return t[phase], "n/a"
    assert not pl.run_chain(seed=1, poisoned=True, reasoner=refusing_write).payload_landed, \
        "no write_memory means no poison and no landing"
    print("PASS test_oracle_requires_real_decisions — oracle is decision-driven")


def main() -> None:
    tests = [
        test_all_gates_allow_the_compromise,
        test_continuous_mode_still_passes,
        test_gates_block_matched_violations,
        test_oracle_fires_and_clean_run_does_not,
        test_divergence_onsets_before_deploy,
        test_divergence_lives_in_reasoning_not_tools,
        test_instrument_builds_no_defense,
        test_rbac_reads_real_tool_calls,
        test_oracle_requires_real_decisions,
    ]
    for t in tests:
        t()
    print(f"\n{len(tests)} tests passed.")


if __name__ == "__main__":
    main()
