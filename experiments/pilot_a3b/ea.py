"""Evolutionary search v2: standard baselines + fixed mechanisms A/B.

57-review fixes:
- S2: NSGA-II uses proper (rank, crowding) binary tournament; NSGA-III uses
  reference-direction association + niche counting (labelled as our
  reimplementation); GA = tournament + weighted sum + uniform crossover;
  Random Search = uniform random sampling (no survivor tricks).
- F6: counterexample pool aggregates the WHOLE population once per
  generation; full signatures; implicated genes from decision traces;
  weights actually reach the evaluator; targeted mutation REPLACES standard
  mutation (matched mutation-count budget).
- M1: identical initial pool / representation / scenario set / rollout budget
  across methods. GP is excluded (decision-table FSM over a small discrete
  action set; tree GP would change the representation -- see report 58).
"""
from __future__ import annotations

import itertools
import math
import random
from collections import Counter, defaultdict

from a3_bridge import (
    ACTIONS,
    OBS_ALL,
    Gene,
    StatefulFSM,
    evaluate_controller,
    make_gene_rule_table,
    random_fsm,
    repair_fsm,
    run_episode_fsm,
)

from split_access import validate_evolution_scenarios

# ---------------------------------------------------------------------------
# Variation (all methods: exactly ONE mutate call per child)
# ---------------------------------------------------------------------------
def mutate(fsm: StatefulFSM, rng: random.Random, rate: float = 0.15) -> StatefulFSM:
    g = fsm.clone()
    genes = g.genes_list()
    n_touch = max(1, int(len(genes) * rate))
    for _ in range(n_touch):
        gene = rng.choice(genes)
        gene.action = rng.choice(ACTIONS)
        if rng.random() < 0.3:
            gene.wait_n = rng.randint(1, 4)
    return g


def crossover(a: StatefulFSM, b: StatefulFSM, rng: random.Random) -> StatefulFSM:
    genes = []
    for key in sorted(set(a.genes) | set(b.genes)):
        src = a.genes.get(key) if rng.random() < 0.5 else b.genes.get(key)
        if src is None:
            src = a.genes.get(key) or b.genes[key]
        genes.append(src.clone())
    default = (a.default_action, a.default_wait) if rng.random() < 0.5 else (b.default_action, b.default_wait)
    return StatefulFSM(genes, default, a.sla_aware or b.sla_aware, a.fixed_wait or b.fixed_wait)


# ---------------------------------------------------------------------------
# Mechanism B-new: counterexample-guided CONTRACT-PRESERVING mutation (D-062)
# ---------------------------------------------------------------------------
# failure signature -> preferred repair action for implicated genes
_SIG_REPAIR = {
    "dup_retry": ("WAIT", "VERIFY", "COMPENSATE"),      # duplicate from blind retry
    "sla_retry": ("WAIT", "VERIFY"),                     # retry before SLA clearance
    "residual": ("COMPENSATE", "ROLLBACK"),              # avoidable residue
    "comp_fail_loop": ("ESCALATE", "ROLLBACK"),          # compensation failing repeatedly
    "unnecessary_escalation": ("VERIFY", "WAIT", "RETRY"),
    "incomplete": ("RETRY", "VERIFY", "WAIT"),
}


class CounterexamplePool:
    """Aggregates failures across the whole population once per generation.

    Signatures are ACTION-SEQUENCE patterns (not coarse labels): each failing
    episode yields the (obs, action) decision sequence and a failure cause.
    Targeted mutation touches ONLY genes consulted in failing traces and
    proposes a cause-specific repair action, then the genome passes through
    the standard contract repair (so B cannot reintroduce illegal rules).
    """

    def __init__(self):
        self.cluster_counts = Counter()
        self.cluster_genes = defaultdict(Counter)  # sig -> gene key -> count
        self.cluster_cause = Counter()
        self.n_examples = 0

    def clear(self):
        self.cluster_counts.clear()
        self.cluster_genes.clear()
        self.cluster_cause.clear()
        self.n_examples = 0

    @staticmethod
    def _cause(row):
        if row["duplicate"]:
            return "dup_retry"
        if row.get("sla_violation"):
            return "sla_retry"
        if row.get("avoidable_harm", 0) > 0:
            return "residual"
        if row.get("compensation_failure"):
            return "comp_fail_loop"
        if row.get("policy_selected_escalation") and row.get("class_success") in (0, None):
            return "unnecessary_escalation"
        return "incomplete"

    @staticmethod
    def _signature(row):
        trace = row.get("decision_trace") or []
        window = tuple((o, a) for o, _at, _st, a in trace[-4:])
        return (CounterexamplePool._cause(row), window)

    def aggregate(self, results):
        for res in results:
            for r in res["rows"]:
                if r["class_success"] in (1, None):
                    continue
                if not r.get("decision_trace"):
                    continue
                self.n_examples += 1
                sig = self._signature(r)
                self.cluster_counts[sig] += 1
                self.cluster_cause[self._cause(r)] += 1
                for (obs, att, stack, _act) in r["decision_trace"]:
                    self.cluster_genes[sig][(obs, att, stack)] += 1

    def implicated_genes(self, top_clusters=3):
        keys = Counter()
        for sig, _c in self.cluster_counts.most_common(top_clusters):
            keys.update(self.cluster_genes[sig])
        return list(keys)

    def targeted_mutate(self, fsm: StatefulFSM, rng: random.Random) -> StatefulFSM:
        """Counterexample-guided CONTRACT-PRESERVING mutation: modify one
        implicated gene toward a cause-specific repair action. Exactly one
        mutation event (budget-matched with standard mutate)."""
        g = fsm.clone()
        if not self.cluster_counts:
            return mutate(g, rng)
        sig, _count = self.cluster_counts.most_common(1)[0]
        cause = sig[0]
        candidates = []
        for (obs, att, stack) in self.implicated_genes():
            gene = g.genes.get((obs, att, stack))
            if gene is not None:
                candidates.append(gene)
        gene = rng.choice(candidates) if candidates else rng.choice(g.genes_list())
        repairs = _SIG_REPAIR.get(cause, ACTIONS)
        gene.action = rng.choice(repairs)
        if rng.random() < 0.3:
            gene.wait_n = rng.randint(1, 4)
        return g


# ---------------------------------------------------------------------------
# Safety Gate (D-062 Stage 3): behavioural hard filter before survivor use
# ---------------------------------------------------------------------------
SAFETY_BATTERY = None  # populated by driver with fixed critical scenarios


def safety_battery_pass(fsm, battery, verdicts):
    """Hard behavioural screen: candidates producing duplicates or SLA
    violations on the fixed safety battery are REJECTED (cannot be traded off
    against success)."""
    for sc in battery:
        row = run_episode_fsm(fsm, sc)
        if row["duplicate"] or row.get("sla_violation"):
            return False
    return True


# ---------------------------------------------------------------------------
# Selection helpers
# ---------------------------------------------------------------------------
def dominates(u, v):
    return all(x <= y for x, y in zip(u, v)) and any(x < y for x, y in zip(u, v))


def fast_non_dominated_sort(objs):
    n = len(objs)
    S = [[] for _ in range(n)]
    cnt = [0] * n
    fronts = [[]]
    for i in range(n):
        for j in range(n):
            if i == j:
                continue
            if dominates(objs[i], objs[j]):
                S[i].append(j)
            elif dominates(objs[j], objs[i]):
                cnt[i] += 1
        if cnt[i] == 0:
            fronts[0].append(i)
    k = 0
    while fronts[k]:
        nxt = []
        for i in fronts[k]:
            for j in S[i]:
                cnt[j] -= 1
                if cnt[j] == 0:
                    nxt.append(j)
        k += 1
        fronts.append(nxt)
    return fronts[:-1]


def crowding_distance(objs, front):
    n = len(front)
    dist = {i: 0.0 for i in front}
    if n <= 2:
        return {i: float("inf") for i in front}
    m = len(objs[0])
    for d in range(m):
        srt = sorted(front, key=lambda i: objs[i][d])
        dist[srt[0]] = dist[srt[-1]] = float("inf")
        lo, hi = objs[srt[0]][d], objs[srt[-1]][d]
        span = (hi - lo) or 1.0
        for k in range(1, n - 1):
            dist[srt[k]] += (objs[srt[k + 1]][d] - objs[srt[k - 1]][d]) / span
    return dist


def reference_dirs(m=3, p=6):
    dirs = []

    def rec(remain, dims, acc):
        if dims == 1:
            acc2 = acc + [remain]
            s = sum(acc2) or 1
            dirs.append([x / s for x in acc2])
            return
        for v in range(remain + 1):
            rec(remain - v, dims - 1, acc + [v])

    rec(p, m, [])
    return dirs


def _solve_linear_system(matrix, rhs):
    """Small deterministic Gaussian elimination with partial pivoting."""
    n = len(rhs)
    aug = [list(map(float, matrix[i])) + [float(rhs[i])] for i in range(n)]
    for col in range(n):
        pivot = max(range(col, n), key=lambda row: abs(aug[row][col]))
        if abs(aug[pivot][col]) < 1e-12:
            raise ArithmeticError("singular extreme-point hyperplane")
        aug[col], aug[pivot] = aug[pivot], aug[col]
        scale = aug[col][col]
        aug[col] = [value / scale for value in aug[col]]
        for row in range(n):
            if row == col:
                continue
            factor = aug[row][col]
            if factor:
                aug[row] = [a - factor * b for a, b in zip(aug[row], aug[col])]
    return [aug[i][-1] for i in range(n)]


def _nsga3_normalize(objs, extreme_indices=None):
    """Canonical NSGA-III ideal/extreme-point/intercept normalization."""
    if not objs or not objs[0]:
        raise ValueError("NSGA-III requires a non-empty objective matrix")
    m = len(objs[0])
    if any(len(row) != m for row in objs):
        raise ValueError("objective dimensions are inconsistent")
    ideal = [min(row[j] for row in objs) for j in range(m)]
    shifted = [[float(row[j]) - ideal[j] for j in range(m)] for row in objs]

    extreme_indices = list(range(len(shifted))) if extreme_indices is None else list(extreme_indices)
    if not extreme_indices:
        raise ValueError("NSGA-III normalization requires a non-empty first front")
    extremes = []
    for objective in range(m):
        weights = [1e-6] * m
        weights[objective] = 1.0
        index = min(
            extreme_indices,
            key=lambda i: max(shifted[i][j] / weights[j] for j in range(m)),
        )
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
            norm_sq = sum(value * value for value in direction)
            if norm_sq <= 0:
                raise ValueError("reference direction must be non-zero")
            projection = sum(vector[k] * direction[k] for k in range(len(vector))) / norm_sq
            distance = math.sqrt(max(
                0.0,
                sum((vector[k] - projection * direction[k]) ** 2 for k in range(len(vector))),
            ))
            if distance < best_distance:
                best_direction, best_distance = direction_index, distance
        associations.append(best_direction)
        distances.append(best_distance)
    return associations, distances


def niching_select(objs, front, dirs, selected=(), rng=None, extreme_indices=None):
    """Canonical NSGA-III splitting-front niching using full-population normalization.

    Earlier accepted fronts contribute to niche counts. Empty niches select their
    closest associated member; occupied niches select a seeded random member.
    """
    if not front:
        return []
    if not dirs:
        raise ValueError("NSGA-III requires at least one reference direction")
    normalized, _ideal, _intercepts = _nsga3_normalize(objs, extreme_indices=extreme_indices)
    associations, distances = _associate_reference_directions(normalized, dirs)
    niche_count = [0] * len(dirs)
    for index in selected:
        if index < 0 or index >= len(objs):
            raise IndexError("selected NSGA-III index is out of range")
        niche_count[associations[index]] += 1

    remaining_by_direction = defaultdict(list)
    for index in front:
        remaining_by_direction[associations[index]].append(index)
    for members in remaining_by_direction.values():
        members.sort()
    rng = rng or random.Random(0)
    chosen = []
    while len(chosen) < len(front):
        available = [d for d, members in remaining_by_direction.items() if members]
        if not available:
            break
        direction = min(available, key=lambda d: (niche_count[d], d))
        candidates = remaining_by_direction[direction]
        if niche_count[direction] == 0:
            pick = min(candidates, key=lambda i: (distances[i], i))
        else:
            pick = rng.choice(candidates)
        candidates.remove(pick)
        chosen.append(pick)
        niche_count[direction] += 1
    return chosen


# ---------------------------------------------------------------------------
# Driver
# ---------------------------------------------------------------------------
def run_evolution(method, init_pool, scenarios, verdicts, pop_size, generations,
                  eval_budget, seed, safety_battery=None, battery_verdicts=None,
                  counterexample_cap=None):
    # Fail before cloning/evaluating any candidate if a non-Train split is supplied.
    validate_evolution_scenarios(scenarios)
    """method: random | ga | nsga2 | nsga3 | A | B | AB | ABG
    (A = contract repair; B = counterexample-guided mutation;
     G suffix = behavioural safety gate)."""
    rng = random.Random(seed)
    population = [g.clone() for g in init_pool[:pop_size]]
    episodes_used = 0
    unique_evaluations = 0
    cache_hits = 0
    evaluation_calls = 0
    battery = safety_battery if (safety_battery and method.endswith("G")) else None
    cache = {}

    def fingerprint(g):
        return tuple(sorted((k, gene.action, gene.wait_n) for k, gene in g.genes.items())) + (
            g.default_action, g.default_wait, g.sla_aware, g.fixed_wait)

    def evaluate_direct(g):
        nonlocal episodes_used, unique_evaluations, evaluation_calls
        res = evaluate_controller(g, scenarios, verdicts, None)
        episodes_used += len(scenarios)
        unique_evaluations += 1
        evaluation_calls += 1
        return res

    def evaluate(g):
        nonlocal cache_hits, evaluation_calls
        fp = fingerprint(g)
        if fp in cache:
            cache_hits += 1
            evaluation_calls += 1
            return cache[fp]
        if episodes_used + len(scenarios) > eval_budget:
            return None
        res = evaluate_direct(g)
        cache[fp] = res
        return res

    def gate_ok(g):
        nonlocal episodes_used
        if battery is None:
            return True
        episodes_used += len(battery)
        return safety_battery_pass(g, battery, battery_verdicts or verdicts)

    use_repair = method.startswith("A") or method.startswith("AB")
    use_cex = "B" in method
    cex = CounterexamplePool()

    results = []
    for g in population:
        res = evaluate(g)
        if res is None:
            res = evaluate_direct(g)
        results.append(res)
    objs = [r["objectives"] for r in results]
    history = []

    for gen in range(generations):
        fronts0 = fast_non_dominated_sort(objs)
        ranks = {}
        for fi, f in enumerate(fronts0):
            for i in f:
                ranks[i] = fi
        crowd = {}
        for f in fronts0:
            crowd.update(crowding_distance(objs, f))

        if use_cex:
            cex.clear()
            cex.aggregate(results)

        # --- variation: exactly one mutate per child ---------------------
        offspring = []
        attempts = 0
        if method == "random":
            while len(offspring) < pop_size and attempts < pop_size * 6:
                attempts += 1
                cand = random_fsm(rng)
                if gate_ok(cand):
                    offspring.append(cand)
            while len(offspring) < pop_size:
                offspring.append(random_fsm(rng))
        else:
            while len(offspring) < pop_size and attempts < pop_size * 6:
                attempts += 1
                if method == "ga":
                    def fit(i):
                        return sum(objs[i])
                    a = min(rng.sample(range(len(population)), 3), key=fit)
                    b = min(rng.sample(range(len(population)), 3), key=fit)
                else:
                    def pick():
                        i, j = rng.randrange(len(population)), rng.randrange(len(population))
                        ri, rj = ranks[i], ranks[j]
                        if ri != rj:
                            return i if ri < rj else j
                        return i if crowd.get(i, 0) >= crowd.get(j, 0) else j
                    a, b = pick(), pick()
                child = crossover(population[a], population[b], rng)
                if use_cex:
                    child = cex.targeted_mutate(child, rng)      # ONE mutation event
                else:
                    child = mutate(child, rng)                    # ONE mutation event
                if use_repair:
                    child = repair_fsm(child)
                if not gate_ok(child):
                    continue
                offspring.append(child)
            while len(offspring) < pop_size:
                g2 = mutate(population[rng.randrange(len(population))], rng)
                if use_repair:
                    g2 = repair_fsm(g2)
                offspring.append(g2)

        off_results = []
        for g in offspring:
            res = evaluate(g)
            if res is None:
                res = evaluate_direct(g)
            off_results.append(res)

        # --- survivor selection -----------------------------------------
        combined = population + offspring
        results_all = results + off_results
        objs_all = [r["objectives"] for r in results_all]

        if method == "random":
            # pure random search: keep best-by-sum from everything seen
            order = sorted(range(len(combined)), key=lambda i: sum(objs_all[i]))
            population = [combined[i] for i in order[:pop_size]]
        elif method == "ga":
            order = sorted(range(len(combined)), key=lambda i: sum(objs_all[i]))
            population = [combined[i] for i in order[:pop_size]]
        else:
            fronts = fast_non_dominated_sort(objs_all)
            ranks = {}
            for fi, f in enumerate(fronts):
                for i in f:
                    ranks[i] = fi
            picked = []
            for f in fronts:
                if len(picked) + len(f) <= pop_size:
                    picked.extend(f)
                else:
                    remain = pop_size - len(picked)
                    if method == "nsga3":
                        picked.extend(niching_select(objs_all, f, reference_dirs(), selected=picked, rng=rng, extreme_indices=fronts[0])[:remain])
                    else:
                        cd = crowding_distance(objs_all, f)
                        picked.extend(sorted(f, key=lambda i: -cd[i])[:remain])
                    break
            population = [combined[i] for i in picked]

        # Reuse the result already associated with each selected genome.
        # Re-querying the cache here is not an evaluation and must not inflate
        # cache_hits/evaluation_calls.
        result_by_fingerprint = {
            fingerprint(genome): result
            for genome, result in zip(combined, results_all)
        }
        results = [result_by_fingerprint[fingerprint(genome)] for genome in population]
        objs = [r["objectives"] for r in results]

        # ranks/crowd for next-gen tournament
        fronts = fast_non_dominated_sort(objs)
        ranks = {}
        for fi, f in enumerate(fronts):
            for i in f:
                ranks[i] = fi
        crowd = {}
        for f in fronts:
            crowd.update(crowding_distance(objs, f))

        best = min(objs, key=lambda o: sum(o))
        history.append({
            "gen": gen,
            "episodes": episodes_used,
            "best_sum_obj": sum(best),
            "mean_cond_rec": sum(r["cond_rec"] for r in results) / len(results),
        })

    best_idx = min(range(len(population)), key=lambda i: sum(objs[i]))
    return {
        "method": method,
        "seed": seed,
        "best": population[best_idx],
        "best_result": results[best_idx],
        "final_population": population,
        "final_results": results,
        "episodes": episodes_used,
        "unique_evaluations": unique_evaluations,
        "cache_hits": cache_hits,
        "evaluation_calls": evaluation_calls,
        "history": history,
    }


def validator_illegal_ratio(population):
    """Fraction of population with at least one contract-validator violation
    (independent of the repair table, 57 F7)."""
    from contract_validator import validate_genome
    bad = 0
    for fsm in population:
        rep = validate_genome(fsm.genes_list(), fsm.default_action, fsm.default_wait)
        if rep.genome_invalid or rep.rule_invalid:
            bad += 1
    return bad / max(1, len(population))
