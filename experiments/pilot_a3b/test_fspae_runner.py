"""Tests for FSPAE archives, target scheduling, and Train-only guards."""
import random
from unittest.mock import patch

import pytest

from a3_bridge import ACT_ESCALATE, ACT_RETRY, ACT_VERIFY
from sbcg import CandidateRecord, fsm_fingerprint, make_shared_initial_pool
from fspae_runner import StratumParetoArchive, _target_cluster, run_fspae_evolution


SCENARIOS = [
    {
        "scenario_id": "d079|train|search|f1|D1|r0",
        "split": "train", "evaluation_role": "search",
        "task_family_id": "f1", "difficulty_stratum": "D1",
        "cluster_id": "f1|D1", "label": "R1",
    },
    {
        "scenario_id": "d079|train|search|f2|D5|r0",
        "split": "train", "evaluation_role": "search",
        "task_family_id": "f2", "difficulty_stratum": "D5",
        "cluster_id": "f2|D5", "label": "R3",
    },
]
VERDICTS = {
    SCENARIOS[0]["scenario_id"]: {"class": "R1"},
    SCENARIOS[1]["scenario_id"]: {"class": "R3"},
}


def fake_evaluate(fsm, scenarios, verdicts, scenario_families=None, use_five_objectives=True):
    action = fsm.genes_list()[0].action
    rows = []
    for scenario in scenarios:
        label = verdicts[scenario["scenario_id"]]["class"]
        success = int(action == ACT_VERIFY) if label in ("R1", "R2") else int(action == ACT_ESCALATE)
        harm = int(action == ACT_RETRY)
        rows.append({
            "scenario_id": scenario["scenario_id"], "label": label,
            "class_success": success, "avoidable_harm": harm,
            "decision_count": 1 if action != ACT_RETRY else 2,
            "policy_selected_escalation": int(action == ACT_ESCALATE),
            "duplicate": harm, "sla_violation": 0, "invariant_violation": 0,
            "compensation_failure": False,
            "decision_trace": [("TIMEOUT", 0, False, action)] if not success else [],
        })
    r12 = [row for row in rows if row["label"] in ("R1", "R2")]
    r3 = [row for row in rows if row["label"] == "R3"]
    r4 = [row for row in rows if row["label"] == "R4"]
    mean = lambda values: sum(values) / len(values) if values else 0.0
    cond = mean([row["class_success"] for row in r12])
    esc = mean([row["class_success"] for row in r3])
    contain = mean([row["class_success"] for row in r4])
    harm_mean = mean([row["avoidable_harm"] for row in rows])
    cost = mean([
        row["decision_count"] + row["policy_selected_escalation"] for row in r12
    ])
    objectives = (1 - cond, harm_mean, cost, 1 - esc, 1 - contain)
    constraints = {
        "duplicate": mean([row["duplicate"] for row in rows]),
        "sla_violation": 0.0, "invariant_violation": 0.0,
    }
    metrics = {
        "rows": rows, "cond_rec": cond, "avoid_resid": harm_mean,
        "unnec_actions_r12": cost, "corr_esc": esc, "containment": contain,
        "dup": constraints["duplicate"], "sla_viol": 0.0, "violations": 0.0,
        "objectives": objectives,
    }
    per_family = {
        scenario["task_family_id"]: float(rows[index]["class_success"])
        for index, scenario in enumerate(scenarios)
        if rows[index]["label"] in ("R1", "R2")
    }
    return CandidateRecord(
        fsm=fsm, objectives=objectives, constraints=constraints,
        per_family_condrec=per_family, fingerprint=fsm_fingerprint(fsm),
        valid_genome=True, metrics=metrics, source_split="train",
    )


def test_archive_rejects_globally_infeasible_candidate():
    archive = StratumParetoArchive("f1|D1", "R1", capacity=2)
    unsafe = fake_evaluate(
        make_shared_initial_pool(4, size=2, include_hand=False)[0],
        [SCENARIOS[0]], VERDICTS,
    )
    unsafe.constraints["duplicate"] = 0.1
    assert archive.update(unsafe, (0.0, 0.0, 0.0), random.Random(1)) is False
    assert archive.records == []


def test_archive_keeps_nondominated_candidates_and_respects_capacity():
    pool = make_shared_initial_pool(4, size=8, include_hand=False)
    archive = StratumParetoArchive("f1|D1", "R1", capacity=2)
    candidates = [
        fake_evaluate(pool[0], [SCENARIOS[0]], VERDICTS),
        fake_evaluate(pool[1], [SCENARIOS[0]], VERDICTS),
        fake_evaluate(pool[2], [SCENARIOS[0]], VERDICTS),
    ]
    for candidate, local in zip(
        candidates, [(0.0, 0.8, 3.0), (0.2, 0.2, 2.0), (0.8, 0.0, 1.0)]
    ):
        archive.update(candidate, local, random.Random(2))
    assert len(archive.records) <= 2
    assert archive.records


def test_deficit_scheduler_targets_empty_stratum_before_full_archive():
    pool = make_shared_initial_pool(4, size=4, include_hand=False)
    full = StratumParetoArchive("f1|D1", "R1", capacity=4)
    empty = StratumParetoArchive("f2|D5", "R3", capacity=4)
    for index, local in enumerate(
        [(0.0, 0.0, 0.0), (0.1, 0.1, 1.0), (0.2, 0.2, 2.0), (0.3, 0.3, 3.0)]
    ):
        full.update(
            fake_evaluate(pool[index], [SCENARIOS[0]], VERDICTS),
            local, random.Random(1),
        )
    assert _target_cluster(
        {"f1|D1": full, "f2|D5": empty}, random.Random(7), "deficit"
    ) == "f2|D5"


def test_performance_deficit_uses_archive_performance_not_archive_size():
    pool = make_shared_initial_pool(44, size=12, include_hand=False)
    for index, candidate in enumerate(pool[:6]):
        candidate.genes_list()[0].action = ACT_VERIFY if index % 2 == 0 else ACT_ESCALATE
    strong_full = StratumParetoArchive("f1|D1", "R1", capacity=4)
    weak_sparse = StratumParetoArchive("f2|D5", "R3", capacity=4)
    strong_vectors = [
        (0.00, 0.50, 4.0),
        (0.10, 0.40, 3.0),
        (0.20, 0.30, 2.0),
        (0.30, 0.20, 1.0),
    ]
    for candidate, objectives in zip(pool[:4], strong_vectors):
        record = fake_evaluate(candidate, [SCENARIOS[0]], VERDICTS)
        strong_full.update(record, objectives, random.Random(1))
    weak_record = fake_evaluate(pool[5], [SCENARIOS[1]], VERDICTS)
    weak_sparse.update(weak_record, (0.90, 0.80, 2.0), random.Random(1))
    assert len(strong_full.records) == 4
    assert len(weak_sparse.records) == 1
    assert _target_cluster(
        {"f1|D1": strong_full, "f2|D5": weak_sparse},
        random.Random(7), "performance_deficit",
    ) == "f2|D5"


def test_r2_parent_pair_and_counterexample_mutation_are_target_conditioned():
    pool = make_shared_initial_pool(41, size=12, include_hand=False)
    for index, candidate in enumerate(pool[:4]):
        candidate.genes_list()[0].action = ACT_VERIFY if index % 2 == 0 else ACT_ESCALATE
    kwargs = {
        "initial_pool": pool, "scenarios": SCENARIOS, "verdicts": VERDICTS,
        "pop_size": 4, "generations": 2,
        "eval_budget": 4 * 3 * len(SCENARIOS), "seed": 17,
        "archive_capacity": 3, "target_mode": "performance_deficit",
        "parent_mode": "local_pair", "variation_mode": "target_cluster",
    }
    with patch("fspae_runner.evaluate_sbcg_candidate", side_effect=fake_evaluate):
        result = run_fspae_evolution(**kwargs)
    assert result["algorithm"] == "FSPAE-R2"
    assert result["config"]["performance_deficit"]["archive_cardinality_used"] is False
    assert result["mutation_audit"]
    for audit in result["mutation_audit"]:
        assert audit["parent_a_source"] == "target_archive"
        assert audit["parent_b_source"] == "target_archive"
        assert audit["target_cluster"] in {"f1|D1", "f2|D5"}
        if audit["selected_cluster"] is not None:
            assert audit["selected_cluster"] == audit["target_cluster"]
            assert audit["target_match"] is True
        else:
            assert audit["target_match"] is False
            assert audit["fallback"] == "standard_mutation_no_target_counterexamples"


def test_fspae_loop_is_reproducible_and_budget_accounting_is_exact():
    pool = make_shared_initial_pool(41, size=12, include_hand=False)
    kwargs = {
        "initial_pool": pool, "scenarios": SCENARIOS, "verdicts": VERDICTS,
        "pop_size": 4, "generations": 2,
        "eval_budget": 4 * 3 * len(SCENARIOS), "seed": 7,
        "archive_capacity": 3,
    }
    with patch("fspae_runner.evaluate_sbcg_candidate", side_effect=fake_evaluate):
        first = run_fspae_evolution(**kwargs)
        second = run_fspae_evolution(**kwargs)
    assert first["history"] == second["history"]
    assert first["target_selection_counts"] == second["target_selection_counts"]
    assert first["initial_pool_sha256"] == second["initial_pool_sha256"]
    assert first["unique_evaluations"] + first["cache_hits"] == first["evaluation_calls"]
    assert first["episodes"] <= first["eval_budget"]
    assert len(first["archive_stats"]) == 2
    assert {row["cluster_id"] for row in first["archive_stats"]} == {"f1|D1", "f2|D5"}


def test_fspae_refuses_diagnostic_or_test_rows_before_fitness():
    pool = make_shared_initial_pool(41, size=8, include_hand=False)
    with patch("fspae_runner.evaluate_sbcg_candidate", side_effect=AssertionError("must not evaluate")):
        with pytest.raises(ValueError, match="search-role"):
            run_fspae_evolution(
                pool, [{**SCENARIOS[0], "evaluation_role": "diagnostic"}],
                VERDICTS, pop_size=4, generations=1, eval_budget=8, seed=1,
            )
        with pytest.raises(ValueError, match="train split only"):
            run_fspae_evolution(
                pool, [{**SCENARIOS[0], "split": "test"}],
                VERDICTS, pop_size=4, generations=1, eval_budget=8, seed=1,
            )
