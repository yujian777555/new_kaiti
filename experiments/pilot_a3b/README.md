# Transferred A-3B / SBCG pilot subset

This directory contains a source-preserving subset transferred from `yujian777555/kaitibaogao`, branch `pilot-a-stateful-recovery`, source HEAD `33672562ebaeb6c3a533e7e0fd975cbac045b5e3`.

Included: D-079 Train-only challenge generator/diagnostics/lock, A-3B stateful simulator and verdict logic, typed task semantics, split guard, contract validator, EA utilities, SBCG implementation/runner, selected tests, and immutable diagnostic artifacts.

The copied subset is **not yet declared independently runnable**. The new repository's CI must pass, the D-079 manifest must regenerate to the locked SHA, and all dependencies must be accounted for before this subset is used for new experiments.

D-079 v2 is Train-only and non-confirmatory. Its manifest lock does not authorize optimizer execution or Validation/Test access.
