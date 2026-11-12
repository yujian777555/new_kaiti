# D-087 CI failure analysis — run 43154910372

The regression run on `cf162756a075358767f93d56df7001949cfeaef7` failed only `test_independent_audit_and_immutable_outputs` because `artifact_hashes` was false. All 397 tests otherwise completed; replication metrics and decision checks were true.

Raw worktree hashes changed after Git newline normalization, while canonical content was identical for every artifact. The artifact manifest now stores both raw SHA-256 and canonical SHA-256 with line endings normalized to LF. Independent audit uses canonical hashes; raw hashes remain provenance only.

The complete failed CI log is preserved byte-for-byte as `d087_ci_43154910372_failure.log.gz`. The prior manifest is preserved as `d087_artifact_manifest.pre_canonical_hash.json`. No scenario, policy, metric, candidate, budget, or replication decision changed.
