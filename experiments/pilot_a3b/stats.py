"""Pooled hierarchical cluster statistics (57 S1 fix).

Statistical hierarchy:
- sampling unit = (task-family x fault-composition) cluster;
- within cluster: paired scenario differences (averaged over algorithm seeds
  first, so seeds are nested repeats, NOT independent samples);
- inference: cluster bootstrap (percentile CI) + sign-flip permutation on
  cluster means; Holm correction across the secondary family;
- seed stability reported separately as descriptive statistics.

This module NEVER averages CI endpoints or p-values across seeds.
"""
from __future__ import annotations

import json
import random
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).parent


def cluster_key(row):
    return (row["task"], row["composition"])


def pooled_paired_stats(rows_a, rows_b, field="class_success", reps=4000, seed=20261108):
    """Pooled hierarchical paired analysis: a - b.

    1. per scenario: mean over algorithm seeds of (a - b);
    2. per cluster: mean over its scenarios;
    3. bootstrap clusters; sign-flip permutation on cluster means.
    """
    by_ms_a = defaultdict(dict)  # scenario -> seed -> value
    by_ms_b = defaultdict(dict)
    meta = {}
    for r in rows_a:
        by_ms_a[r["scenario_id"]][r.get("seed", 0)] = r.get(field)
        meta[r["scenario_id"]] = cluster_key(r)
    for r in rows_b:
        by_ms_b[r["scenario_id"]][r.get("seed", 0)] = r.get(field)

    sc_diffs = {}
    for sid, per_seed in by_ms_a.items():
        vals = []
        for sd, va in per_seed.items():
            vb = by_ms_b.get(sid, {}).get(sd)
            if va is None or vb is None:
                continue
            vals.append(float(va) - float(vb))
        if vals:
            sc_diffs[sid] = sum(vals) / len(vals)

    clusters = defaultdict(list)
    for sid, d in sc_diffs.items():
        clusters[meta[sid]].append(d)
    keys = sorted(clusters)
    if not keys:
        return None
    cluster_means = {k: sum(v) / len(v) for k, v in clusters.items()}
    all_vals = [cluster_means[k] for k in keys]
    mean = sum(all_vals) / len(all_vals)

    rng = random.Random(seed)
    boot = []
    for _ in range(reps):
        sampled = [rng.choice(keys) for _ in keys]
        boot.append(sum(cluster_means[k] for k in sampled) / len(sampled))
    boot.sort()
    lo = boot[int(0.025 * (len(boot) - 1))]
    hi = boot[int(0.975 * (len(boot) - 1))]

    obs = abs(mean)
    extreme = 0
    for _ in range(4000):
        s = sum(c * (1 if rng.random() < 0.5 else -1) for c in all_vals) / len(all_vals)
        if abs(s) >= obs - 1e-12:
            extreme += 1
    p = (extreme + 1) / 4001

    sd = (sum((x - mean) ** 2 for x in all_vals) / max(1, len(all_vals) - 1)) ** 0.5
    return {
        "mean_diff": round(mean, 4),
        "ci95": [round(lo, 4), round(hi, 4)],
        "clusters": len(keys),
        "permutation_p": round(p, 4),
        "cluster_sd": round(sd, 4),
        "effect_size_d": round(mean / sd, 4) if sd > 1e-9 else None,
    }


def holm(ps):
    m = len(ps)
    order = sorted(range(m), key=lambda i: ps[i])
    adj = [0.0] * m
    running = 0.0
    for rank, i in enumerate(order):
        val = (m - rank) * ps[i]
        running = max(running, val)
        adj[i] = min(1.0, running)
    return adj


def seed_stability(rows_by_seed, field="class_success"):
    vals = []
    for seed, rows in rows_by_seed.items():
        good = [r[field] for r in rows if r.get(field) is not None]
        vals.append(round(sum(good) / len(good), 4) if good else None)
    nums = [v for v in vals if v is not None]
    mean = sum(nums) / len(nums) if nums else None
    sd = (sum((x - mean) ** 2 for x in nums) / max(1, len(nums) - 1)) ** 0.5 if len(nums) > 1 else 0.0
    return {"per_seed": vals, "mean": round(mean, 4) if mean is not None else None,
            "sd": round(sd, 4)}


def analyse(data):
    runs = data["runs"]
    methods = data["methods"]
    seeds = data["seeds"]
    by_ms = {(r["method"], r["seed"]): r for r in runs}

    def rows_of(method):
        out = []
        for s in seeds:
            r = by_ms.get((method, s))
            if not r:
                continue
            for row in r["rows"]:
                row = dict(row)
                row["seed"] = s
                out.append(row)
        return out

    def rows_of_split(method, split):
        out = []
        for s in seeds:
            r = by_ms.get((method, s))
            if not r:
                continue
            for row in r["rows"]:
                if row.get("split") != split:
                    continue
                row = dict(row)
                row["seed"] = s
                out.append(row)
        return out

    agg = {}
    for m in methods:
        rows = rows_of(m)
        agg[m] = {}
        for field in ("class_success", "invariant_violation", "duplicate",
                      "avoidable_harm", "policy_selected_escalation"):
            good = [r[field] for r in rows if r.get(field) is not None]
            agg[m][field + "_mean"] = round(sum(good) / len(good), 4) if good else None
        by_seed = defaultdict(list)
        for s in seeds:
            r = by_ms.get((m, s))
            if r:
                by_seed[s] = r["rows"]
        agg[m]["class_success_stability"] = seed_stability(by_seed)
        agg[m]["validator_illegal_ratio"] = round(
            sum(by_ms[(m, s)].get("validator_illegal_ratio", 0.0) for s in seeds
                if (m, s) in by_ms) / max(1, len([s for s in seeds if (m, s) in by_ms])), 4)
        agg[m]["episodes_total"] = sum(by_ms[(m, s)]["episodes"] for s in seeds if (m, s) in by_ms)

    def contrast(ma, mb, split=None):
        ra = rows_of_split(ma, split) if split else rows_of(ma)
        rb = rows_of_split(mb, split) if split else rows_of(mb)
        return pooled_paired_stats(ra, rb)

    primary = {"name": "AB vs nsga2 (all)", "stats": contrast("AB", "nsga2")}
    second_names = [("A", "nsga2"), ("B", "nsga2"), ("AB", "A"), ("AB", "B"),
                    ("AB", "ga"), ("AB", "nsga3"), ("AB", "hand")]
    secondary = {}
    for a, b in second_names:
        secondary[f"{a} vs {b}"] = contrast(a, b)
    ps = [secondary[f"{a} vs {b}"]["permutation_p"] for a, b in second_names
          if secondary.get(f"{a} vs {b}")]
    for (a, b), adj in zip(second_names, holm(ps)):
        key = f"{a} vs {b}"
        if secondary.get(key):
            secondary[key]["holm_p"] = round(adj, 4)

    # Q6: validation split (never used in search)
    q6 = {}
    for m in methods:
        rows = rows_of_split(m, "validation")
        good = [r["class_success"] for r in rows if r.get("class_success") is not None]
        q6[m] = round(sum(good) / len(good), 4) if good else None
    q6_contrast = contrast("AB", "nsga2", split="validation")

    return {
        "aggregate": agg,
        "primary_contrast": primary,
        "secondary_contrasts": secondary,
        "validation_class_success": q6,
        "q6_AB_vs_nsga2_validation": q6_contrast,
    }


def main():
    data = json.loads((HERE / "diagnostic2_results.json").read_text(encoding="utf-8"))
    rep = analyse(data)
    (HERE / "diagnostic2_stats.json").write_text(json.dumps(rep, indent=2), encoding="utf-8")
    print("== aggregate ==")
    for m, a in rep["aggregate"].items():
        print(f"{m:8s} class_succ={a['class_success_mean']} viol={a['invariant_violation_mean']} "
              f"dup={a['duplicate_mean']} illegal={a['validator_illegal_ratio']} "
              f"eps={a['episodes_total']}")
    print("primary:", json.dumps(rep["primary_contrast"], indent=1))
    print("secondary:")
    for k, v in rep["secondary_contrasts"].items():
        if v:
            print(f"  {k:14s} d={v['mean_diff']:+.4f} ci={v['ci95']} p={v['permutation_p']} holm={v.get('holm_p')}")
    print("validation (Q6):", rep["validation_class_success"])
    print("Q6 contrast:", json.dumps(rep["q6_AB_vs_nsga2_validation"], indent=1))


if __name__ == "__main__":
    main()
