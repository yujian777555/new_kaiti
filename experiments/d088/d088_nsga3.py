"""D-088 NSGA-III evolutionary search for mechanism-parameter genomes.

Adapts the canonical NSGA-III from ea.py to operate on D088Genome.
All evaluation is deterministic simulator-only (no LLM/API).
"""
from __future__ import annotations

import math
import random
import sys
from collections import defaultdict
from pathlib import Path

_D087_SRC = Path(__file__).resolve().parent.parent.parent / "data" / "historical" / "d087" / "source"
if str(_D087_SRC) not in sys.path:
    sys.path.insert(0, str(_D087_SRC))

from dependency_recovery import run_episode  # noqa: E402

from mechanism_genome import (  # noqa: E402
    D088Genome, random_d088_genome, mutate_d088, crossover_d088,
)
from mechanism_policies import D088Policy  # noqa: E402


# ---------------------------------------------------------------------------
# NSGA-III helpers (same canonical algorithm as ea.py)
# ---------------------------------------------------------------------------
def _solve_linear_system(matrix: list[list[float]], rhs: list[float]) -> list[float]:
    n = len(matrix)
    aug = [list(matrix[i]) + [rhs[i]] for i in range(n)]
    for col in range(n):
        pivot = max(range(col, n), key=lambda r: abs(aug[r][col]))
        aug[col], aug[pivot] = aug[pivot], aug[col]
        if abs(aug[col][col]) < 1e-12:
            raise ArithmeticError("singular matrix")
        for row in range(n):
            if row == col:
                continue
            factor = aug[row][col] / aug[col][col]
            aug[row] = [a - factor * b for a, b in zip(aug[row], aug[col])]
    return [aug[i][-1] for i in range(n)]


def _nsga3_normalize(objs, extreme_indices=None):
    if not objs or not objs[0]:
        raise ValueError("NSGA-III requires a non-empty objective matrix")
    m = len(objs[0])
    ideal = [min(row[j] for row in objs) for j in range(m)]
    shifted = [[float(row[j]) - ideal[j] for j in range(m)] for row in objs]
    extreme_indices = list(range(len(shifted))) if extreme_indices is None else list(extreme_indices)
    extremes = []
    for objective in range(m):
        weights = [1e-6] * m
        weights[objective] = 1.0
        index = min(extreme_indices, key=lambda i: max(shifted[i][j] / weights[j] for j in range(m)))
        extremes.append(shifted[index])
    intercepts = None
    try:
        coefficients = _solve_linear_system(extremes, [1.0] * m)
        candidate = [1.0 / value for value in coefficients]
        if all(math.isfinite(value) and value > 1e-12 for value in candidate):
            intercepts = candidate
    except (ArithmeticError, ZeroDivisionError):
        intercepts = None
    if intercepts is None:
        intercepts = [max(row[j] for row in shifted) for j in range(m)]
    intercepts = [value if value > 1e-12 else 1.0 for value in intercepts]
    normalized = [[shifted[i][j] / intercepts[j] for j in range(m)] for i in range(len(objs))]
    return normalized, ideal, intercepts


def _associate_reference_directions(normalized, dirs):
    associations, distances = [], []
    for vector in normalized:
        best_direction, best_distance = 0, float("inf")
        for direction_index, direction in enumerate(dirs):
            norm_sq = sum(v * v for v in direction)
            projection = sum(vector[k] * direction[k] for k in range(len(vector))) / norm_sq
            distance = math.sqrt(max(0.0, sum((vector[k] - projection * direction[k]) ** 2 for k in range(len(vector)))))
            if distance < best_distance:
                best_direction, best_distance = direction_index, distance
        associations.append(best_direction)
        distances.append(best_distance)
    return associations, distances


def _generate_reference_directions(dim: int, divisions: int = 3) -> list[list[float]]:
    """Das-Dennis simplex-lattice reference directions."""
    dirs = []
    def _compositions(n, k, prefix=()):
        if k == 1:
            yield prefix + (n,)
        else:
            for i in range(n + 1):
                yield from _compositions(n - i, k - 1, prefix + (i,))
    for combo in _compositions(divisions, dim):
        dirs.append([c / divisions for c in combo])
    return dirs


def _fast_non_dominated_sort(objs: list[list[float]]) -> list[list[int]]:
    """Minimize all objectives."""
    n = len(objs)
    dominates = [[] for _ in range(n)]
    dominated_count = [0] * n
    for i in range(n):
        for j in range(n):
            if i == j:
                continue
            if all(objs[i][k] <= objs[j][k] for k in range(len(objs[i]))) and \
               any(objs[i][k] < objs[j][k] for k in range(len(objs[i]))):
                dominates[i].append(j)
            elif all(objs[j][k] <= objs[i][k] for k in range(len(objs[i]))) and \
                 any(objs[j][k] < objs[i][k] for k in range(len(objs[i]))):
                dominated_count[i] += 1
    fronts = []
    current = [i for i in range(n) if dominated_count[i] == 0]
    while current:
        fronts.append(current)
        next_front = []
        for i in current:
            for j in dominates[i]:
                dominated_count[j] -= 1
                if dominated_count[j] == 0:
                    next_front.append(j)
        current = next_front
    return fronts


def _nsga3_select(population, objs, pop_size, rng, dirs=None):
    """NSGA-III environmental selection."""
    if dirs is None:
        dirs = _generate_reference_directions(len(objs[0]))
    fronts = _fast_non_dominated_sort(objs)
    selected = []
    for front in fronts:
        if len(selected) + len(front) <= pop_size:
            selected.extend(front)
        else:
            # Niching on the splitting front
            normalized, _, _ = _nsga3_normalize(objs, extreme_indices=fronts[0] if fronts else front)
            associations, distances = _associate_reference_directions(normalized, dirs)
            niche_count = [0] * len(dirs)
            for idx in selected:
                niche_count[associations[idx]] += 1
            remaining_by_dir = defaultdict(list)
            for idx in front:
                remaining_by_dir[associations[idx]].append(idx)
            for members in remaining_by_dir.values():
                members.sort()
            chosen = []
            while len(chosen) < pop_size - len(selected):
                available = [d for d, m in remaining_by_dir.items() if m]
                if not available:
                    break
                direction = min(available, key=lambda d: (niche_count[d], d))
                candidates = remaining_by_dir[direction]
                if niche_count[direction] == 0:
                    pick = min(candidates, key=lambda i: (distances[i], i))
                else:
                    pick = rng.choice(candidates)
                candidates.remove(pick)
                chosen.append(pick)
                niche_count[direction] += 1
            selected.extend(chosen)
            break
    return [population[i] for i in selected[:pop_size]]


# ---------------------------------------------------------------------------
# Objective computation
# ---------------------------------------------------------------------------
# Objectives (all minimized):
# 0: 1 - CondRecSucc
# 1: AvoidableHarm
# 2: UnnecessaryActionCost (class-conditional action cost)
# 3: 1 - CorrectEscalation (R3)
# 4: 1 - DamageContainment (R4)
N_OBJECTIVES = 5


def compute_objectives(genome: D088Genome, scenarios: list[dict]) -> list[float]:
    """Evaluate a genome on scenarios and return 5 minimized objective values."""
    policy = D088Policy(genome)
    rows = []
    for scenario in scenarios:
        report = run_episode(policy, scenario, max_actions=24)
        rows.append(report)

    r1r2 = [r for r in rows if r["label"] in ("R1", "R2")]
    r3 = [r for r in rows if r["label"] == "R3"]
    r4 = [r for r in rows if r["label"] == "R4"]

    cond_rec = (
        sum(r["conditional_recovery_success"] for r in r1r2) / max(1, len(r1r2))
    )
    correct_esc = (
        sum(r["correct_escalation"] for r in r3) / max(1, len(r3))
    )
    damage_cont = (
        sum(r["class_success"] for r in r4) / max(1, len(r4))
    )
    avoid_harm = sum(r["avoidable_harm"] for r in rows) / max(1, len(rows))
    action_cost = sum(r["action_cost"] for r in rows) / max(1, len(rows))

    return [
        1.0 - cond_rec,
        avoid_harm,
        action_cost,
        1.0 - correct_esc,
        1.0 - damage_cont,
    ]


# ---------------------------------------------------------------------------
# Evolution driver
# ---------------------------------------------------------------------------
def run_evolution(
    scenarios: list[dict],
    mech_flags: dict[str, bool],
    pop_size: int = 24,
    generations: int = 30,
    seed: int = 42,
    initial_pool_size: int = 36,
) -> dict:
    """Run NSGA-III evolution for one experimental group.

    Returns a result dict with population, objectives, and per-generation history.
    """
    rng = random.Random(seed)
    # Initial population
    population = []
    for i in range(initial_pool_size):
        g = random_d088_genome(random.Random(seed * 7919 + i * 131 + 29), mech_flags)
        population.append(g)
    population = population[:pop_size]

    # Evaluate initial population
    objectives = [compute_objectives(g, scenarios) for g in population]
    history = []

    for gen in range(generations):
        # Offspring generation
        offspring = []
        for _ in range(pop_size):
            if rng.random() < 0.7:
                child = mutate_d088(rng.choice(population), rng)
            else:
                p1 = rng.choice(population)
                p2 = rng.choice(population)
                child = crossover_d088(p1, p2, rng)
                child = mutate_d088(child, rng)
            offspring.append(child)

        offspring_objs = [compute_objectives(g, scenarios) for g in offspring]

        # Combine and select
        combined = population + offspring
        combined_objs = objectives + offspring_objs
        population = _nsga3_select(combined, combined_objs, pop_size, rng)
        # Recompute objectives for the selected population (indices shifted)
        # For efficiency, track objectives alongside
        obj_map = {id(g): o for g, o in zip(combined, combined_objs)}
        objectives = [obj_map[id(g)] for g in population]

        best_obj = [min(o[j] for o in objectives) for j in range(N_OBJECTIVES)]
        history.append({
            "generation": gen,
            "best_objectives": best_obj,
            "mean_cond_rec": 1.0 - sum(o[0] for o in objectives) / len(objectives),
            "mean_r3": 1.0 - sum(o[3] for o in objectives) / len(objectives),
            "mean_r4": 1.0 - sum(o[4] for o in objectives) / len(objectives),
        })

    # Final evaluation
    final_metrics = []
    for g, o in zip(population, objectives):
        final_metrics.append({
            "genome": g.fingerprint(),
            "objectives": o,
            "cond_rec": 1.0 - o[0],
            "r3_success": 1.0 - o[3],
            "r4_success": 1.0 - o[4],
            "avoid_harm": o[1],
            "action_cost": o[2],
        })

    # Select best by lexicographic: hard constraints, then R3, R4, then cost
    best = max(final_metrics, key=lambda m: (m["r3_success"], m["r4_success"], -m["action_cost"]))

    return {
        "seed": seed,
        "mech_flags": mech_flags,
        "pop_size": pop_size,
        "generations": generations,
        "history": history,
        "final_population": final_metrics,
        "best": best,
    }
