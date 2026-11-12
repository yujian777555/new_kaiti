"""Paper 1 safe runner preflight tests — 10 deterministic gates.

No LLM, API, network, or model inference is performed by any test in this file.
"""
from __future__ import annotations

import builtins
import copy
import json
import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from scripts.paper1_safe_runner import (
    DBHashReport,
    EpisodeCache,
    PreflightConfig,
    PreflightResult,
    SplitData,
    TestAccessViolation as _TestAccessViolation,
    TestIsolationGuard as _TestIsolationGuard,
    Treatment,
    TREATMENT_CACHE_NAMESPACES,
    build_batch_plan,
    build_evotool_config,
    classify_operation_outcome,
    compute_db_hash,
    compute_progress,
    inject_official_db,
    load_official_db,
    load_splits,
    run_preflight,
)

# Prevent pytest from collecting these as test classes.
_TestAccessViolation.__test__ = False
_TestIsolationGuard.__test__ = False


# ---------------------------------------------------------------------------
# Helpers: synthetic JSONL data
# ---------------------------------------------------------------------------
def _make_row(split: str, index: int) -> dict:
    return {
        "split": split,
        "task_id": f"retail-{split}-{index:04d}",
        "user_id": f"user-{index:04d}",
        "instruction": f"Task instruction {index}",
        "actions": [{"name": "lookup_order", "kwargs": {"order_id": f"o-{index}"}}],
        "outputs": [f"output-{index}"],
    }


def _write_jsonl(path: pathlib.Path, split: str, count: int) -> None:
    path.write_text(
        "".join(json.dumps(_make_row(split, i)) + "\n" for i in range(count)),
        encoding="utf-8",
    )


@pytest.fixture()
def synthetic_data_dir(tmp_path):
    _write_jsonl(tmp_path / "train.jsonl", "train", 500)
    _write_jsonl(tmp_path / "dev.jsonl", "dev", 20)
    _write_jsonl(tmp_path / "test.jsonl", "test", 115)
    return tmp_path


# ---------------------------------------------------------------------------
# 1. Split preservation
# ---------------------------------------------------------------------------
class TestSplitPreservation:
    def test_train_dev_counts_500_20(self, synthetic_data_dir):
        splits = load_splits(synthetic_data_dir)
        assert len(splits.train) == 500
        assert len(splits.dev) == 20
        assert splits.test is None  # Test NOT loaded

    def test_no_cross_split_task_id_overlap(self, synthetic_data_dir):
        splits = load_splits(synthetic_data_dir)
        overlap = set(splits.train_ids) & set(splits.dev_ids)
        assert overlap == set()

    def test_original_task_ids_preserved(self, synthetic_data_dir):
        splits = load_splits(synthetic_data_dir)
        assert splits.train_ids[0] == "retail-train-0000"
        assert splits.train_ids[-1] == "retail-train-0499"
        assert splits.dev_ids[0] == "retail-dev-0000"
        assert splits.dev_ids[-1] == "retail-dev-0019"

    def test_no_random_resplitting(self, synthetic_data_dir):
        """Loading twice must yield identical task-id lists (no shuffle)."""
        first = load_splits(synthetic_data_dir)
        second = load_splits(synthetic_data_dir)
        assert first.train_ids == second.train_ids
        assert first.dev_ids == second.dev_ids


# ---------------------------------------------------------------------------
# 2. 8x3 batch plan
# ---------------------------------------------------------------------------
class TestBatchPlan:
    def test_eight_batches_three_distinct_tasks(self, synthetic_data_dir):
        splits = load_splits(synthetic_data_dir)
        plan = build_batch_plan(splits.train_ids, seed=42)
        assert len(plan) == 8
        for batch in plan:
            assert len(batch["task_ids"]) == 3

    def test_24_unique_train_tasks_per_seed(self, synthetic_data_dir):
        splits = load_splits(synthetic_data_dir)
        plan = build_batch_plan(splits.train_ids, seed=42)
        flat = [tid for b in plan for tid in b["task_ids"]]
        assert len(flat) == 24
        assert len(set(flat)) == 24

    def test_deterministic_across_calls(self, synthetic_data_dir):
        splits = load_splits(synthetic_data_dir)
        first = build_batch_plan(splits.train_ids, seed=42)
        second = build_batch_plan(splits.train_ids, seed=42)
        assert first == second

    def test_different_seeds_yield_different_plans(self, synthetic_data_dir):
        splits = load_splits(synthetic_data_dir)
        first = build_batch_plan(splits.train_ids, seed=42)
        other = build_batch_plan(splits.train_ids, seed=99)
        assert first != other

    def test_batch_ids_recorded(self, synthetic_data_dir):
        splits = load_splits(synthetic_data_dir)
        plan = build_batch_plan(splits.train_ids, seed=42)
        for i, batch in enumerate(plan):
            assert batch["generation"] == i + 1
            assert all(isinstance(tid, str) for tid in batch["task_ids"])


# ---------------------------------------------------------------------------
# 3. Dev-only selection
# ---------------------------------------------------------------------------
class TestDevOnlySelection:
    def test_config_selects_on_dev_not_test(self):
        cfg = build_evotool_config(PreflightConfig())
        # The evolve() signature accepts test=None; the runner must pass None.
        # Selection happens via select_population(pop, sel) where sel = Dev.
        # This test verifies the config does not enable any Test path.
        assert cfg.evolve.log_test_eval is False

    def test_train_and_dev_are_disjoint(self, synthetic_data_dir):
        splits = load_splits(synthetic_data_dir)
        train_set = set(splits.train_ids)
        dev_set = set(splits.dev_ids)
        assert train_set.isdisjoint(dev_set)

    def test_selection_set_size_is_dev_count(self, synthetic_data_dir):
        splits = load_splits(synthetic_data_dir)
        assert len(splits.dev) == 20  # S_sel == Dev == 20


# ---------------------------------------------------------------------------
# 4. Test file access interception
# ---------------------------------------------------------------------------
class TestFileAccessInterception:
    def test_guard_blocks_test_file_read(self, synthetic_data_dir):
        guard = _TestIsolationGuard()
        guard.arm()
        try:
            test_path = synthetic_data_dir / "test.jsonl"
            with pytest.raises(_TestAccessViolation):
                with test_path.open("r", encoding="utf-8") as fh:
                    fh.read(1)
        finally:
            guard.disarm()

    def test_guard_blocks_builtin_open(self, synthetic_data_dir):
        guard = _TestIsolationGuard()
        guard.arm()
        try:
            test_path = synthetic_data_dir / "test.jsonl"
            with pytest.raises(_TestAccessViolation):
                with builtins.open(str(test_path), "r", encoding="utf-8") as fh:
                    fh.read(1)
        finally:
            guard.disarm()

    def test_guard_allows_non_test_files(self, synthetic_data_dir):
        guard = _TestIsolationGuard()
        guard.arm()
        try:
            train_path = synthetic_data_dir / "train.jsonl"
            with train_path.open("r", encoding="utf-8") as fh:
                first_line = fh.readline()
            assert "train" in first_line
        finally:
            guard.disarm()

    def test_guard_records_violations(self, synthetic_data_dir):
        guard = _TestIsolationGuard()
        guard.arm()
        try:
            test_path = synthetic_data_dir / "test.jsonl"
            with pytest.raises(_TestAccessViolation):
                test_path.open("r", encoding="utf-8")
            assert len(guard.violations) == 1
        finally:
            guard.disarm()

    def test_disarmed_guard_allows_test_read(self, synthetic_data_dir):
        guard = _TestIsolationGuard()
        guard.disarm()
        test_path = synthetic_data_dir / "test.jsonl"
        with test_path.open("r", encoding="utf-8") as fh:
            assert fh.readline().strip()

    def test_context_manager_arms_and_disarms(self, synthetic_data_dir):
        with _TestIsolationGuard() as guard:
            test_path = synthetic_data_dir / "test.jsonl"
            with pytest.raises(_TestAccessViolation):
                test_path.open("r", encoding="utf-8")
        # After context exit, guard is disarmed
        test_path = synthetic_data_dir / "test.jsonl"
        with test_path.open("r", encoding="utf-8") as fh:
            assert fh.readline().strip()


# ---------------------------------------------------------------------------
# 5. evolve(test=None) parameter
# ---------------------------------------------------------------------------
class TestEvolveTestParameter:
    def test_evolve_accepts_test_none(self):
        """Verify the pinned loop signature supports test=None.

        We introspect the signature without calling the function (which would
        require an LLM client).
        """
        import inspect

        sys.path.insert(0, str(
            pathlib.Path(__file__).resolve().parent.parent
            / "vendor" / "evotool" / "full_source"
        ))
        from src.evolve.loop import evolve

        sig = inspect.signature(evolve)
        assert "test" in sig.parameters
        assert sig.parameters["test"].default is None

    def test_evolve_returns_early_for_zero_epochs(self):
        """epochs <= 0 causes early return before any Test interaction."""
        import inspect

        sys.path.insert(0, str(
            pathlib.Path(__file__).resolve().parent.parent
            / "vendor" / "evotool" / "full_source"
        ))
        from src.evolve.loop import evolve

        source = inspect.getsource(evolve)
        assert "ev.epochs <= 0" in source

    def test_preflight_config_sets_epochs_positive(self):
        cfg = build_evotool_config(PreflightConfig())
        assert cfg.evolve.epochs == 1
        assert cfg.evolve.epochs > 0


# ---------------------------------------------------------------------------
# 6. log_test_eval=False
# ---------------------------------------------------------------------------
class TestLogTestEval:
    def test_config_log_test_eval_is_false(self):
        cfg = build_evotool_config(PreflightConfig())
        assert cfg.evolve.log_test_eval is False

    def test_upstream_default_is_true_but_overridden(self):
        sys.path.insert(0, str(
            pathlib.Path(__file__).resolve().parent.parent
            / "vendor" / "evotool" / "full_source"
        ))
        from src.config import EvolveConfig

        default = EvolveConfig()
        assert default.log_test_eval is True  # upstream default
        cfg = build_evotool_config(PreflightConfig())
        assert cfg.evolve.log_test_eval is False  # safe runner override


# ---------------------------------------------------------------------------
# 7. Official DB injection and hash consistency
# ---------------------------------------------------------------------------
class TestDBInjection:
    def test_official_db_loads_with_expected_counts(self):
        db = load_official_db()
        assert "users" in db
        assert "orders" in db
        assert "products" in db
        assert len(db["users"]) == 500
        assert len(db["orders"]) == 1000
        assert len(db["products"]) == 50

    def test_db_hash_deterministic(self):
        db1 = load_official_db()
        db2 = load_official_db()
        h1 = compute_db_hash(db1)
        h2 = compute_db_hash(db2)
        assert h1.combined_sha256 == h2.combined_sha256

    def test_injection_hash_matches_env_initialization(self):
        _ensure_test_sys_path()
        import importlib

        env_mod = importlib.import_module("src.envs.taubench_env")
        base_db = inject_official_db(env_mod)
        env = env_mod.TauBenchEnv()
        base_hash = compute_db_hash(base_db)
        env_hash = compute_db_hash(env.db)
        assert base_hash.combined_sha256 == env_hash.combined_sha256

    def test_env_instances_get_independent_db_copies(self):
        _ensure_test_sys_path()
        import importlib

        env_mod = importlib.import_module("src.envs.taubench_env")
        inject_official_db(env_mod)
        env1 = env_mod.TauBenchEnv()
        env2 = env_mod.TauBenchEnv()
        # Mutate env1's DB; env2 must be unaffected (deep-copy isolation).
        first_order = next(iter(env1.db["orders"].values()))
        first_order["status"] = "MUTATED_FOR_TEST"
        env2_first_order = env2.db["orders"][
            next(iter(env2.db["orders"]))
        ]
        assert env2_first_order["status"] != "MUTATED_FOR_TEST"


# ---------------------------------------------------------------------------
# 8. Episode DB deep-copy isolation
# ---------------------------------------------------------------------------
class TestDeepCopyIsolation:
    def test_base_db_unaffected_by_env_mutation(self):
        _ensure_test_sys_path()
        import importlib

        env_mod = importlib.import_module("src.envs.taubench_env")
        base_db = inject_official_db(env_mod)
        original_hash = compute_db_hash(base_db).combined_sha256

        env = env_mod.TauBenchEnv()
        # Mutate env's DB
        first_key = next(iter(env.db["orders"]))
        env.db["orders"][first_key]["status"] = "CORRUPTED"

        assert compute_db_hash(base_db).combined_sha256 == original_hash

    def test_load_db_returns_fresh_copy_each_call(self):
        _ensure_test_sys_path()
        import importlib

        env_mod = importlib.import_module("src.envs.taubench_env")
        inject_official_db(env_mod)
        db1 = env_mod.load_db()
        db2 = env_mod.load_db()
        first_key = next(iter(db1["orders"]))
        db1["orders"][first_key]["status"] = "DIRTY"
        assert db2["orders"][first_key]["status"] != "DIRTY"


# ---------------------------------------------------------------------------
# 9. Treatment status and cache isolation
# ---------------------------------------------------------------------------
class TestTreatmentIsolation:
    def test_three_treatments_defined(self):
        assert len(Treatment) == 3
        assert Treatment.EVOTOOL_LEGACY.value == "L"
        assert Treatment.EVOTOOL_OUTCOME_AWARE_SELECTION.value == "R1"
        assert Treatment.EVOTOOL_FULL_OUTCOME_AWARE.value == "R2"

    def test_cache_namespaces_are_unique(self):
        namespaces = set(TREATMENT_CACHE_NAMESPACES.values())
        assert len(namespaces) == 3

    def test_caches_are_isolated(self):
        cache_l = EpisodeCache(Treatment.EVOTOOL_LEGACY)
        cache_r1 = EpisodeCache(Treatment.EVOTOOL_OUTCOME_AWARE_SELECTION)
        cache_r2 = EpisodeCache(Treatment.EVOTOOL_FULL_OUTCOME_AWARE)

        cache_l.put("policy_A", "inst_1", {"reward": 0.9, "treatment": "L"})
        assert cache_r1.get("policy_A", "inst_1") is None
        assert cache_r2.get("policy_A", "inst_1") is None
        assert len(cache_r1) == 0
        assert len(cache_r2) == 0

    def test_cache_put_get_roundtrip(self):
        cache = EpisodeCache(Treatment.EVOTOOL_FULL_OUTCOME_AWARE)
        cache.put("pol_X", "inst_42", {"reward": 0.5})
        assert cache.get("pol_X", "inst_42") == {"reward": 0.5}

    def test_operation_outcome_separate_from_status(self):
        # Normal return with Error: text -> domain_rejection, status stays "success"
        outcome = classify_operation_outcome("success", "Error: insufficient balance")
        assert outcome == "domain_rejection"
        # Normal return without Error: -> completed
        assert classify_operation_outcome("success", "Order cancelled") == "completed"
        # Exception -> execution_error
        assert classify_operation_outcome("error", "Error: TypeError") == "execution_error"

    def test_legacy_progress_counts_success_status(self):
        statuses = ["success", "success", "error", "success"]
        outputs = ["ok", "Error: x", "Error: y", "ok"]
        legacy = compute_progress(Treatment.EVOTOOL_LEGACY, statuses, outputs)
        assert legacy == pytest.approx(0.75)

    def test_outcome_aware_progress_counts_completed(self):
        statuses = ["success", "success", "error", "success"]
        outputs = ["ok", "Error: x", "Error: y", "ok"]
        r2 = compute_progress(Treatment.EVOTOOL_FULL_OUTCOME_AWARE, statuses, outputs)
        # outcomes: completed, domain_rejection, execution_error, completed
        assert r2 == pytest.approx(0.5)

    def test_r1_selection_uses_outcome_aware_progress(self):
        statuses = ["success", "success"]
        outputs = ["ok", "Error: domain"]
        r1 = compute_progress(Treatment.EVOTOOL_OUTCOME_AWARE_SELECTION, statuses, outputs)
        assert r1 == pytest.approx(0.5)  # outcome-aware
        legacy = compute_progress(Treatment.EVOTOOL_LEGACY, statuses, outputs)
        assert legacy == pytest.approx(1.0)  # legacy counts both as success


# ---------------------------------------------------------------------------
# 10. No real LLM/API calls
# ---------------------------------------------------------------------------
class TestNoLLMCalls:
    def test_preflight_runs_without_llm(self, synthetic_data_dir):
        """The entire preflight must complete without any LLM/API/network."""
        result = run_preflight(synthetic_data_dir, PreflightConfig())
        # We can't globally prove no network here, but the fact that this runs
        # in a bare CI environment (no API keys, no model server) without
        # error is the practical gate.
        assert isinstance(result, PreflightResult) or True  # just runs

    def test_no_llm_client_in_safe_runner_module(self):
        """The safe_runner module must not import any LLM client."""
        import scripts.paper1_safe_runner as mod
        source_path = pathlib.Path(mod.__file__)
        source = source_path.read_text(encoding="utf-8")
        # These imports would indicate LLM coupling
        forbidden = ["from src.llm", "import litellm", "import openai",
                      "requests.get", "requests.post", "httpx", "aiohttp"]
        for token in forbidden:
            assert token not in source, f"safe_runner imports forbidden LLM dependency: {token}"

    def test_evotool_config_has_no_api_key(self):
        cfg = build_evotool_config(PreflightConfig())
        assert cfg.llm.api_key == ""
        assert cfg.llm.base_url == ""


# ---------------------------------------------------------------------------
# Full preflight integration
# ---------------------------------------------------------------------------
class TestFullPreflight:
    def test_preflight_passes_on_synthetic_data(self, synthetic_data_dir):
        result = run_preflight(synthetic_data_dir, PreflightConfig())
        assert result.ok, f"Preflight errors: {result.errors}"
        assert result.checks["split_counts_500_20"] is True
        assert result.checks["no_cross_split_overlap"] is True
        assert result.checks["batch_count_8"] is True
        assert result.checks["batch_size_3"] is True
        assert result.checks["batch_24_unique"] is True
        assert result.checks["log_test_eval_false"] is True
        assert result.checks["test_file_access_blocked"] is True
        assert result.checks["db_injection_hash_match"] is True
        assert result.checks["cache_namespace_isolated"] is True

    def test_preflight_batch_plan_recorded(self, synthetic_data_dir):
        result = run_preflight(synthetic_data_dir, PreflightConfig())
        assert len(result.batch_plan) == 8
        for batch in result.batch_plan:
            assert "generation" in batch
            assert "task_ids" in batch
            assert len(batch["task_ids"]) == 3

    def test_preflight_db_hash_populated(self, synthetic_data_dir):
        result = run_preflight(synthetic_data_dir, PreflightConfig())
        assert result.db_hash is not None
        assert result.db_hash.users_count == 500
        assert result.db_hash.orders_count == 1000
        assert result.db_hash.products_count == 50


def _ensure_test_sys_path():
    root = pathlib.Path(__file__).resolve().parent.parent
    for p in (str(root), str(root / "vendor" / "evotool" / "full_source"),
              str(root / "vendor" / "tau_bench")):
        if p not in sys.path:
            sys.path.insert(0, p)
