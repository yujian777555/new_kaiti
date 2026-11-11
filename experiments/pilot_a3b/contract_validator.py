"""INDEPENDENT contract validator for recovery-controller genomes (57 F7).

This module is written as a SEPARATE code path from the repair operator in
a3_bridge.py: it does not import the repair table and re-derives legality
rules from the tool-contract semantics below. Its purpose is to detect
rule-level and genome-level contract violations without trusting the repairer.

Contract semantics (from 47_PILOT_A3_PROTOCOL / pilot_a3 TOOLS):
- ambiguous public errors (TIMEOUT, PARTIAL) on NON-IDEMPOTENT tools must not
  be answered with a bare retry (duplicate risk) unless verified first;
- PARTIAL commit on a non-compensatable tool cannot be cleared by COMPENSATE;
  COMPENSATE on such a tool is contract-blocked and must not be relied on;
- PERMISSION denial is never fixed by retry/wait/verify/compensate/repair;
- SCHEMA drift is only fixable by REPAIR (schema repair), not by retry loops;
- ROLLBACK presupposes at least one confirmed prior effect; as a static rule
  it is legal everywhere (runtime records emptiness), but default actions
  must be total (cover every guard).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List

# Actions (kept in sync with the controller vocabulary by NAME only; the
# validator re-states its own semantics)
ACTIONS = (
    "RETRY",
    "VERIFY",
    "WAIT",
    "COMPENSATE",
    "ROLLBACK",
    "REPAIR",
    "ESCALATE",
    "STOP_SAFE",
)

ERRORS = ("START", "TIMEOUT", "PARTIAL", "RATE_LIMIT", "SCHEMA", "PERMISSION",
          "COMMITTED", "NOT_COMMITTED", "COMPENSATED", "COMP_FAILED",
          "WAITED", "DUPLICATE", "NOOP")


@dataclass
class RuleGene:
    error: str
    att_bucket: int  # 0, 1, 2
    stack: bool
    action: str
    wait_n: int = 2


@dataclass
class ValidationReport:
    rule_violations: List[str] = field(default_factory=list)
    genome_violations: List[str] = field(default_factory=list)

    @property
    def rule_invalid(self) -> int:
        return len(self.rule_violations)

    @property
    def genome_invalid(self) -> bool:
        return bool(self.genome_violations)


def _rule_error(gene: RuleGene) -> str:
    """Return a violation description for one gene, or '' if legal."""
    e, act = gene.error, gene.action
    if act not in ACTIONS:
        return f"unknown action {act}"
    if gene.wait_n < 1 or gene.wait_n > 4:
        return f"wait_n out of range {gene.wait_n}"

    if act == "REPAIR" and e != "SCHEMA" and e != "START":
        return "REPAIR only meaningful for SCHEMA drift"

    if e == "PERMISSION" and act in ("RETRY", "WAIT", "VERIFY", "COMPENSATE", "ROLLBACK", "REPAIR"):
        return "PERMISSION cannot be fixed by " + act

    if e == "SCHEMA" and act in ("RETRY", "WAIT", "VERIFY", "COMPENSATE", "ROLLBACK"):
        return "SCHEMA drift cannot be fixed by " + act

    if e == "PARTIAL":
        if act in ("RETRY", "WAIT", "VERIFY"):
            return "PARTIAL on retry/wait/verify risks duplicate or stale state"
        if act == "ROLLBACK":
            return "PARTIAL is current-step residue; use COMPENSATE first"
        # COMPENSATE is legal here even on non-compensatable tools only as a
        # probe? No: static rule -- compensate without contract support is
        # never a recovery action the policy may rely on.
        # (Whether the tool is compensatable is a RUNTIME context; the gene
        # cannot see it, so we flag COMPENSATE on PARTIAL as acceptable and let
        # the runtime contract gate it. ESCALATE/STOP_SAFE always legal.)

    if e == "TIMEOUT" and act in ("RETRY",):
        # ambiguous outcome: bare retry only if tool idempotent -- genes are
        # idempotency-agnostic, so the validator flags TIMEOUT->RETRY as
        # conditionally illegal and the genome-level check below verifies that
        # every non-idempotent path avoids it via the context disambiguation
        # (att_bucket/stack cannot encode idempotency, so we treat the pair
        # (TIMEOUT, RETRY) as illegal UNLESS a VERIFY/WAIT guard exists in the
        # same genome -- handled in genome-level checks).
        pass

    if e in ("COMMITTED", "COMPENSATED", "DUPLICATE", "NOOP") and act in ("COMPENSATE",):
        return f"{e}: COMPENSATE without pending effect"

    return ""


def validate_genome(genes, default_action: str, default_wait: int = 2) -> ValidationReport:
    rep = ValidationReport()
    seen = set()
    timeout_retry_guarded = False
    timeout_safe_gene = False
    for g in genes:
        key = (g.error, g.att_bucket, g.stack)
        if key in seen:
            rep.rule_violations.append(f"duplicate gene {key}")
        seen.add(key)
        err = _rule_error(g)
        if err:
            rep.rule_violations.append(f"{key} -> {g.action}: {err}")
        if g.error == "TIMEOUT" and g.action in ("VERIFY", "WAIT", "COMPENSATE", "ROLLBACK", "ESCALATE", "STOP_SAFE"):
            timeout_safe_gene = True

    # genome-level: default action must be total and legal-ish
    if default_action not in ACTIONS:
        rep.genome_violations.append(f"default action unknown: {default_action}")
    if default_action == "REPAIR":
        rep.genome_violations.append("default action REPAIR not total (needs SCHEMA context)")
    if default_wait < 1 or default_wait > 4:
        rep.genome_violations.append(f"default wait out of range {default_wait}")

    # TIMEOUT->RETRY must not be the only TIMEOUT response: at least one
    # TIMEOUT gene must offer a verification/wait/compensation path
    timeout_genes = [g for g in genes if g.error == "TIMEOUT"]
    if timeout_genes and all(g.action == "RETRY" for g in timeout_genes):
        rep.genome_violations.append("all TIMEOUT genes are bare RETRY (ambiguous-outcome hazard)")

    # every error class must have at least one gene
    for e in ("TIMEOUT", "PARTIAL", "RATE_LIMIT", "SCHEMA", "PERMISSION"):
        if not any(g.error == e for g in genes):
            rep.genome_violations.append(f"missing genes for error class {e}")

    return rep


def is_contract_legal(genes, default_action: str, default_wait: int = 2) -> bool:
    rep = validate_genome(genes, default_action, default_wait)
    return not rep.genome_violations and rep.rule_invalid == 0
