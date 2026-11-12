"""Paper 1 safe runner preflight framework.

Deterministic, model-free scaffolding that validates every safety gate before
an EvoTool evolutionary run is permitted.  Nothing here calls an LLM, opens a
network socket, or reads the held-out Test split.

Responsibilities
----------------
1. Data loading: Train 500 / Dev 20 / Test 115, never merged or shuffled.
2. Evolution budget: G=8, B=3, epochs=1 -> 8 batches x 3 distinct Train tasks.
3. Selection: population and final-policy selection on Dev only.
4. Test isolation: file-access-level guard; Test is deferred until policy freeze
   plus explicit authorization.
5. DB injection: locked official tau-bench Retail DB loader replaces EvoTool's
   missing local `taubench_data` path.
6. Treatment interface: L / R1 / R2 with independent episode caches.

This module is safe to import and execute without any model, API, or network
access.  Every public function is deterministic.
"""
from __future__ import annotations

import copy
import hashlib
import json
import random
import sys
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Callable

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
REPO_ROOT = Path(__file__).resolve().parent.parent
EVOTOOL_FULL_SOURCE = REPO_ROOT / "vendor" / "evotool" / "full_source"
TAU_BENCH_VENDOR = REPO_ROOT / "vendor" / "tau_bench"
DATA_DIR = REPO_ROOT / "data" / "taubench_legacy" / "retail"

# Ensure the vendored tau-bench package is importable.
_sys_path_added = False


def _ensure_sys_path() -> None:
    global _sys_path_added
    if not _sys_path_added:
        for p in (str(EVOTOOL_FULL_SOURCE), str(TAU_BENCH_VENDOR), str(REPO_ROOT)):
            if p not in sys.path:
                sys.path.insert(0, p)
        _sys_path_added = True


# ---------------------------------------------------------------------------
# Treatment definitions (docs/11 three-arm design)
# ---------------------------------------------------------------------------
class Treatment(Enum):
    """Three status-semantics arms.  None is assumed superior in advance."""

    EVOTOOL_LEGACY = "L"
    EVOTOOL_OUTCOME_AWARE_SELECTION = "R1"
    EVOTOOL_FULL_OUTCOME_AWARE = "R2"


TREATMENT_CACHE_NAMESPACES: dict[Treatment, str] = {
    Treatment.EVOTOOL_LEGACY: "cache_L_legacy",
    Treatment.EVOTOOL_OUTCOME_AWARE_SELECTION: "cache_R1_outcome_aware_selection",
    Treatment.EVOTOOL_FULL_OUTCOME_AWARE: "cache_R2_full_outcome_aware",
}


# ---------------------------------------------------------------------------
# Episode cache with treatment isolation
# ---------------------------------------------------------------------------
class EpisodeCache:
    """Per-treatment episode cache.  Keys include the treatment ID so that no
    cross-treatment contamination is possible even within a single process."""

    def __init__(self, treatment: Treatment):
        self.treatment = treatment
        self.namespace = TREATMENT_CACHE_NAMESPACES[treatment]
        self._store: dict[tuple[str, str], Any] = {}

    def _key(self, policy_id: str, instance_id: str) -> tuple[str, str]:
        return (self.namespace, f"{policy_id}|{instance_id}")

    def get(self, policy_id: str, instance_id: str) -> Any | None:
        return self._store.get(self._key(policy_id, instance_id))

    def put(self, policy_id: str, instance_id: str, episode: Any) -> None:
        self._store[self._key(policy_id, instance_id)] = episode

    def __len__(self) -> int:
        return len(self._store)

    def clear(self) -> None:
        self._store.clear()


# ---------------------------------------------------------------------------
# Operation outcome extraction (separate from execution status)
# ---------------------------------------------------------------------------
def classify_operation_outcome(status: str, output: str) -> str:
    """Return `operation_outcome` orthogonal to the execution `status`.

    - ``completed``          : normal return, not a domain error.
    - ``domain_rejection``   : normal return whose text starts with ``Error:``.
    - ``execution_error``    : the tool raised / unknown tool (status == "error").

    The raw ``status`` field is never overwritten.  This is the separation
    mandated by D-011 / docs/11.
    """
    if status == "error":
        return "execution_error"
    if isinstance(output, str) and output.startswith("Error:"):
        return "domain_rejection"
    return "completed"


def legacy_progress(statuses: list[str]) -> float:
    """EvoTool legacy progress: fraction of steps with status == "success"."""
    if not statuses:
        return 0.0
    return sum(1 for s in statuses if s == "success") / len(statuses)


def outcome_aware_progress(outcomes: list[str]) -> float:
    """Outcome-aware progress: fraction of steps with outcome == "completed"."""
    if not outcomes:
        return 0.0
    return sum(1 for o in outcomes if o == "completed") / len(outcomes)


def compute_progress(treatment: Treatment, statuses: list[str],
                     outputs: list[str]) -> float:
    """Dispatch progress computation to the correct treatment semantics."""
    if treatment == Treatment.EVOTOOL_LEGACY:
        return legacy_progress(statuses)
    outcomes = [classify_operation_outcome(s, o) for s, o in zip(statuses, outputs)]
    return outcome_aware_progress(outcomes)


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------
@dataclass
class SplitData:
    train: list[dict] = field(default_factory=list)
    dev: list[dict] = field(default_factory=list)
    test: list[dict] | None = None  # deferred until freeze + authorization
    train_ids: list[str] = field(default_factory=list)
    dev_ids: list[str] = field(default_factory=list)


def load_splits(data_dir: Path | str | None = None,
                expected: dict[str, int] | None = None) -> SplitData:
    """Load Train and Dev; Test is NOT loaded here.

    Raises on any cross-split task_id overlap or count mismatch.
    """
    _ensure_sys_path()
    from scripts.paper1_tau_bench_splits import load_train_dev_splits

    data_dir = Path(data_dir) if data_dir else DATA_DIR
    counts = expected or {"train": 500, "dev": 20}
    train, dev = load_train_dev_splits(data_dir, expected_counts=counts)
    return SplitData(
        train=train,
        dev=dev,
        train_ids=[r["task_id"] for r in train],
        dev_ids=[r["task_id"] for r in dev],
    )


# ---------------------------------------------------------------------------
# Batch plan
# ---------------------------------------------------------------------------
def build_batch_plan(train_ids: list[str], seed: int,
                     generations: int = 8, batch_size: int = 3) -> list[dict]:
    """Return the deterministic G=8/B=3 first-epoch batch plan."""
    _ensure_sys_path()
    from scripts.paper1_tau_bench_splits import build_generation_batch_plan

    train_instances = [{"id": tid} for tid in train_ids]
    return build_generation_batch_plan(
        train_instances, seed=seed,
        generations=generations, batch_size=batch_size,
    )


# ---------------------------------------------------------------------------
# DB injection
# ---------------------------------------------------------------------------
@dataclass
class DBHashReport:
    users_sha256: str
    orders_sha256: str
    products_sha256: str
    combined_sha256: str
    users_count: int
    orders_count: int
    products_count: int


def _canonical_hash(obj: Any) -> str:
    raw = json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def compute_db_hash(db: dict[str, Any]) -> DBHashReport:
    users = db.get("users", {})
    orders = db.get("orders", {})
    products = db.get("products", {})
    combined = {"users": users, "orders": orders, "products": products}
    return DBHashReport(
        users_sha256=_canonical_hash(users),
        orders_sha256=_canonical_hash(orders),
        products_sha256=_canonical_hash(products),
        combined_sha256=_canonical_hash(combined),
        users_count=len(users),
        orders_count=len(orders),
        products_count=len(products),
    )


def load_official_db() -> dict[str, Any]:
    """Load the pinned official tau-bench Retail DB JSON files directly.

    Reads the three JSON files without importing the ``tau_bench`` Python
    package (whose ``__init__`` chain requires ``litellm``).  The data files
    are under ``vendor/tau_bench/tau_bench/envs/retail/data/``.
    """
    data_path = TAU_BENCH_VENDOR / "tau_bench" / "envs" / "retail" / "data"
    db: dict[str, Any] = {}
    for part in ("users", "orders", "products"):
        fpath = data_path / f"{part}.json"
        with fpath.open("r", encoding="utf-8") as fh:
            db[part] = json.load(fh)
    return db


def inject_official_db(evotool_env_module: Any) -> dict[str, Any]:
    """Patch EvoTool's ``load_db`` to return the pinned official DB.

    Returns the base DB dict so the caller can verify hashes.
    """
    base = load_official_db()
    evotool_env_module.load_db = lambda: copy.deepcopy(base)
    return base


# ---------------------------------------------------------------------------
# Test isolation guard
# ---------------------------------------------------------------------------
class TestAccessViolation(PermissionError):
    """Raised when Test data is accessed before policy freeze + authorization."""


class TestIsolationGuard:
    """File-access-level guard that blocks reads of the Test split.

    Intercepts ``pathlib.Path.open`` and ``builtins.open`` calls whose path
    targets the Test JSONL.  Any attempt before the guard is explicitly lifted
    raises :class:`TestAccessViolation`.
    """

    def __init__(self, test_filename: str = "test.jsonl"):
        self.test_filename = test_filename
        self._armed = True
        self._violations: list[str] = []
        self._original_path_open = None
        self._original_builtin_open = None

    def _is_test_path(self, file: Any) -> bool:
        try:
            name = str(file)
        except Exception:
            return False
        return self.test_filename in name

    def _guarded_open(self, original: Callable) -> Callable:
        guard = self

        def wrapper(*args: Any, **kwargs: Any) -> Any:
            if guard._armed and args:
                if guard._is_test_path(args[0]):
                    guard._violations.append(str(args[0]))
                    raise TestAccessViolation(
                        f"Test data access blocked before policy freeze: {args[0]}"
                    )
            return original(*args, **kwargs)

        return wrapper

    def arm(self) -> None:
        """Install the file-access guard."""
        import builtins
        import pathlib

        if self._original_path_open is None:
            self._original_path_open = pathlib.Path.open
            pathlib.Path.open = self._guarded_open(self._original_path_open)  # type: ignore[assignment]
        if self._original_builtin_open is None:
            self._original_builtin_open = builtins.open
            builtins.open = self._guarded_open(self._original_builtin_open)  # type: ignore[assignment]
        self._armed = True

    def disarm(self) -> None:
        """Remove the guard (used only after policy freeze + explicit auth)."""
        import builtins
        import pathlib

        if self._original_path_open is not None:
            pathlib.Path.open = self._original_path_open  # type: ignore[assignment]
            self._original_path_open = None
        if self._original_builtin_open is not None:
            builtins.open = self._original_builtin_open  # type: ignore[assignment]
            self._original_builtin_open = None
        self._armed = False

    @property
    def violations(self) -> list[str]:
        return list(self._violations)

    def __enter__(self) -> "TestIsolationGuard":
        self.arm()
        return self

    def __exit__(self, *exc: Any) -> None:
        self.disarm()


# ---------------------------------------------------------------------------
# EvoTool config builder
# ---------------------------------------------------------------------------
@dataclass
class PreflightConfig:
    """Frozen preflight parameters for one safe runner invocation."""

    seed: int = 42
    generations: int = 8
    batch_size: int = 3
    epochs: int = 1
    max_steps: int = 6
    log_test_eval: bool = False
    treatment: Treatment = Treatment.EVOTOOL_LEGACY


def build_evotool_config(preflight: PreflightConfig) -> Any:
    """Construct the pinned EvoToolConfig with the safe-runner overrides."""
    _ensure_sys_path()
    from src.config import EvoToolConfig

    cfg = EvoToolConfig()
    cfg.seed = preflight.seed
    cfg.max_steps = preflight.max_steps
    cfg.evolve.generations = preflight.generations
    cfg.evolve.batch_size = preflight.batch_size
    cfg.evolve.epochs = preflight.epochs
    cfg.evolve.log_test_eval = preflight.log_test_eval
    return cfg


# ---------------------------------------------------------------------------
# Preflight validation
# ---------------------------------------------------------------------------
@dataclass
class PreflightResult:
    ok: bool
    checks: dict[str, bool]
    batch_plan: list[dict]
    db_hash: DBHashReport | None
    treatment: Treatment
    cache_namespace: str
    errors: list[str]


def run_preflight(
    data_dir: Path | str | None = None,
    preflight: PreflightConfig | None = None,
) -> PreflightResult:
    """Execute every deterministic safety gate and return a pass/fail report.

    No LLM, API, network, or Test-split access occurs inside this function.
    """
    pf = preflight or PreflightConfig()
    errors: list[str] = []
    checks: dict[str, bool] = {}

    # 1. Split preservation
    try:
        splits = load_splits(data_dir)
        checks["split_counts_500_20"] = (
            len(splits.train) == 500 and len(splits.dev) == 20
        )
        overlap = set(splits.train_ids) & set(splits.dev_ids)
        checks["no_cross_split_overlap"] = len(overlap) == 0
    except Exception as exc:
        errors.append(f"split loading failed: {exc}")
        splits = SplitData()
        checks["split_counts_500_20"] = False
        checks["no_cross_split_overlap"] = False

    # 2. Batch plan: 8 x 3 distinct
    try:
        plan = build_batch_plan(
            splits.train_ids, seed=pf.seed,
            generations=pf.generations, batch_size=pf.batch_size,
        )
        flat = [tid for b in plan for tid in b["task_ids"]]
        checks["batch_count_8"] = len(plan) == 8
        checks["batch_size_3"] = all(len(b["task_ids"]) == 3 for b in plan)
        checks["batch_24_unique"] = len(flat) == 24 and len(set(flat)) == 24
    except Exception as exc:
        errors.append(f"batch plan failed: {exc}")
        plan = []
        checks["batch_count_8"] = False
        checks["batch_size_3"] = False
        checks["batch_24_unique"] = False

    # 3. Config gates
    cfg = build_evotool_config(pf)
    checks["log_test_eval_false"] = cfg.evolve.log_test_eval is False
    checks["generations_8"] = cfg.evolve.generations == 8
    checks["batch_size_3"] = checks["batch_size_3"] and cfg.evolve.batch_size == 3
    checks["epochs_positive"] = cfg.evolve.epochs > 0

    # 4. Test isolation guard
    guard = TestIsolationGuard()
    guard.arm()
    try:
        test_path = Path(data_dir or DATA_DIR) / "test.jsonl"
        if test_path.is_file():
            try:
                with test_path.open("r", encoding="utf-8") as fh:
                    fh.read(1)
                checks["test_file_access_blocked"] = False
                errors.append("Test file access was NOT blocked by the guard")
            except TestAccessViolation:
                checks["test_file_access_blocked"] = True
        else:
            # File absent: guard still armed, nothing to block.
            checks["test_file_access_blocked"] = True
    finally:
        guard.disarm()

    # 5. DB injection + hash
    try:
        _ensure_sys_path()
        import importlib

        env_mod = importlib.import_module("src.envs.taubench_env")
        base_db = inject_official_db(env_mod)
        db_hash = compute_db_hash(base_db)
        env2 = env_mod.TauBenchEnv()
        db_hash2 = compute_db_hash(env2.db)
        checks["db_injection_hash_match"] = db_hash.combined_sha256 == db_hash2.combined_sha256
    except Exception as exc:
        errors.append(f"DB injection failed: {exc}")
        db_hash = None
        checks["db_injection_hash_match"] = False

    # 6. Treatment cache isolation
    cache_l = EpisodeCache(Treatment.EVOTOOL_LEGACY)
    cache_r1 = EpisodeCache(Treatment.EVOTOOL_OUTCOME_AWARE_SELECTION)
    cache_l.put("pol_A", "inst_0", {"reward": 1.0})
    checks["cache_namespace_isolated"] = (
        cache_r1.get("pol_A", "inst_0") is None
        and len(cache_r1) == 0
        and len(cache_l) == 1
    )

    ok = all(checks.values()) and not errors
    return PreflightResult(
        ok=ok,
        checks=checks,
        batch_plan=plan,
        db_hash=db_hash,
        treatment=pf.treatment,
        cache_namespace=TREATMENT_CACHE_NAMESPACES[pf.treatment],
        errors=errors,
    )
