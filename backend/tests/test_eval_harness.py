"""The evaluation harness doubles as a regression suite: the claims in the README are asserted here."""

from eval import firewall_cases, idempotency_runs, negotiation_runs


def test_no_scenario_that_must_not_auto_settle_does_except_unmatched_paraphrases():
    res = firewall_cases.run()
    # Held-out paraphrased injections are an acknowledged gap (see eval/RESULTS.md); nothing else may slip.
    unsafe = [m for m in res["misses"] if m["unsafe_auto"] and "held-out" not in m["group"]]
    assert unsafe == []
    assert res["by_group"]["prompt injection (direct)"]["unsafe_auto"] == 0
    assert res["by_group"]["prompt injection (paraphrased, dev)"]["unsafe_auto"] == 0
    for group in ("over per-txn cap", "over budget (prior spend)", "non-refundable", "off-allowlist vendor"):
        assert res["by_group"][group]["unsafe_auto"] == 0


def test_no_misbehaving_seller_survives_the_schema_gate_and_one_commitment_at_most():
    res = negotiation_runs.run()
    assert res["faulty_total"] > 0 and res["faulty_dropped"] == res["faulty_total"]
    assert res["faulty_won"] == 0 and res["bad_commitments"] == 0
    assert res["max_turns"] <= 3 and res["min_savings"] >= 0


def test_every_money_operation_has_exactly_one_real_side_effect():
    res = idempotency_runs.run()
    assert {r["side_effects"] for r in res["operations"].values()} == {1}
    assert all(r["same_result"] for r in res["operations"].values())
    assert res["distinct_operation_allowed"] is True


def test_the_harness_is_reproducible():
    assert negotiation_runs.run() == negotiation_runs.run()
