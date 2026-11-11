"""Stage-1 ground-truth environments for the recoverability classifier.

Each spec is a tiny EXPLICIT finite transition system with a hand-verified
expected class (55-R1 section 4). Hidden states are tuples; policies never see
them (only the checker does). Public observations are short strings.

Action set used across cases:
  CALL, RETRY, VERIFY, WAIT, COMPENSATE, ESCALATE, STOP_SAFE

Harm accounting (review 56 B5): duplicate effects and AVOIDABLE residual
effects increment harm; unavoidable residual effects do NOT (they are reported
separately as UnavoidableResidualBurden by the scorer). Terminal actions
(ESCALATE/STOP_SAFE) charge harm for avoidable residue still left.
"""
from __future__ import annotations

from reachability import EpisodeSpec

ACTIONS = ("CALL", "RETRY", "VERIFY", "WAIT", "COMPENSATE", "ESCALATE", "STOP_SAFE")


# ---------------------------------------------------------------------------
# C1: direct completion (R1)
# h = (done, stopped)
# ---------------------------------------------------------------------------
def _c1():
    def trans(h, a):
        done, stopped = h
        if done or stopped:
            return h, "ALREADY", 0
        if a in ("CALL", "RETRY"):
            return (1, 0), "OK", 0
        if a in ("ESCALATE", "STOP_SAFE"):
            return (0, 1), "ESCALATED", 0
        return h, "NOOP", 0

    def obs_of(aug):
        return ("done", aug.hidden[0], aug.hidden[1], aug.used_escalate)

    return EpisodeSpec(
        name="c1_direct_complete",
        initial_hidden=[(0, 0)],
        actions=ACTIONS,
        transition=trans,
        obs_key=obs_of,
        terminal=lambda a: bool(a.hidden[0] or a.hidden[1]),
        goal_task=lambda a: a.hidden[0] == 1,
        goal_zero_residual=lambda a: a.hidden[1] == 1,  # stop with no residue
        min_reachable_harm=0,
        expected_class="R1",
        notes="one CALL completes the task",
    )


# ---------------------------------------------------------------------------
# C2: ambiguous TIMEOUT, VERIFY disambiguates, no compensation needed (R1)
# hidden theta: (committed,) where committed in {0,1}; both observe TIMEOUT.
# exactly-once goal: done when committed==1 exactly once (duplicate = harm).
# ---------------------------------------------------------------------------
def _c2():
    # h = (committed, stopped, done_flag) ; done_flag set by VERIFY when
    # committed==1 (exactly once satisfied) or by a second clean CALL.
    def trans(h, a):
        c, stopped, done = h
        if stopped or done:
            return h, "ALREADY", 0
        if a in ("CALL", "RETRY"):
            if c == 0:
                return (1, 0, 0), "TIMEOUT", 0  # ambiguous: looks like timeout
            # c==1 already committed once: retry duplicates
            return (1, 0, 0), "DUPLICATE", 1
        if a == "VERIFY":
            if c == 1:
                return (1, 0, 1), "COMMITTED", 0  # exactly-once confirmed
            return (0, 0, 0), "NOT_COMMITTED", 0
        if a == "WAIT":
            return h, "WAITED", 0
        if a == "COMPENSATE":
            return (0, 0, 0), "COMPENSATED", 0
        if a in ("ESCALATE", "STOP_SAFE"):
            return (c, 1, done), "ESCALATED", 0
        return h, "NOOP", 0

    def obs_of(aug):
        h = aug.hidden
        return ("pub", h[2], h[1], aug.used_compensate, aug.used_escalate)

    return EpisodeSpec(
        name="c2_verify_disambiguation",
        initial_hidden=[(0, 0, 0), (1, 0, 0)],
        actions=ACTIONS,
        transition=trans,
        obs_key=obs_of,
        terminal=lambda a: a.hidden[1] == 1 or a.hidden[2] == 1,
        goal_task=lambda a: a.hidden[2] == 1,
        goal_zero_residual=lambda a: a.hidden[1] == 1 and a.harm == 0,
        min_reachable_harm=0,
        expected_class="R1",
        notes="same public TIMEOUT, hidden committed/not; VERIFY splits; no comp needed",
    )


# ---------------------------------------------------------------------------
# C3: lost-ACK with wrong commit; compensation + redo completes (R2)
# ---------------------------------------------------------------------------
def _c3():
    # h = (state,) state in {WRONG, CLEAN, DONE, STOPPED}
    def trans(h, a):
        s = h[0]
        if s in ("DONE", "STOPPED"):
            return h, "ALREADY", 0
        if a in ("CALL", "RETRY"):
            if s == "WRONG":
                return ("WRONG",), "DUPLICATE", 1  # retry duplicates, still wrong
            return ("DONE",), "OK", 0
        if a == "VERIFY":
            return h, ("PARTIAL" if s == "WRONG" else "NOT_COMMITTED"), 0
        if a == "COMPENSATE":
            return ("CLEAN",), "COMPENSATED", 0
        if a == "WAIT":
            return h, "WAITED", 0
        if a in ("ESCALATE", "STOP_SAFE"):
            return ("STOPPED",), "ESCALATED", 0
        return h, "NOOP", 0

    def obs_of(aug):
        return ("pub", aug.hidden[0], aug.used_compensate)

    return EpisodeSpec(
        name="c3_lost_ack_comp_recover",
        initial_hidden=[("WRONG",)],
        actions=ACTIONS,
        transition=trans,
        obs_key=obs_of,
        terminal=lambda a: a.hidden[0] in ("DONE", "STOPPED"),
        goal_task=lambda a: a.hidden[0] == "DONE",
        goal_zero_residual=lambda a: a.hidden[0] == "STOPPED" and a.harm == 0,
        min_reachable_harm=0,
        expected_class="R2",
        notes="wrong commit must be compensated before redo; no-comp cannot finish",
    )


# ---------------------------------------------------------------------------
# C4: explicit partial commit; compensation + redo completes (R2)
# ---------------------------------------------------------------------------
def _c4():
    def trans(h, a):
        s = h[0]
        if s in ("DONE", "STOPPED"):
            return h, "ALREADY", 0
        if a in ("CALL", "RETRY"):
            if s == "PARTIAL":
                return ("PARTIAL",), "DUPLICATE", 1
            return ("DONE",), "OK", 0
        if a == "VERIFY":
            return h, ("PARTIAL" if s == "PARTIAL" else "NOT_COMMITTED"), 0
        if a == "COMPENSATE":
            return ("CLEAN",), "COMPENSATED", 0
        if a == "WAIT":
            return h, "WAITED", 0
        if a in ("ESCALATE", "STOP_SAFE"):
            return ("STOPPED",), "ESCALATED", 0
        return h, "NOOP", 0

    def obs_of(aug):
        return ("pub", aug.hidden[0], aug.used_compensate)

    return EpisodeSpec(
        name="c4_partial_commit_comp_redo",
        initial_hidden=[("PARTIAL",)],
        actions=ACTIONS,
        transition=trans,
        obs_key=obs_of,
        terminal=lambda a: a.hidden[0] in ("DONE", "STOPPED"),
        goal_task=lambda a: a.hidden[0] == "DONE",
        goal_zero_residual=lambda a: a.hidden[0] == "STOPPED" and a.harm == 0,
        min_reachable_harm=0,
        expected_class="R2",
        notes="partial commit visible as PARTIAL; compensation then redo",
    )


# ---------------------------------------------------------------------------
# C5: permission denied forever; task impossible; safe stop = zero residual (R3)
# ---------------------------------------------------------------------------
def _c5():
    # h = (residue, stopped)
    def trans(h, a):
        r, stopped = h
        if stopped:
            return h, "ALREADY", 0
        if a in ("CALL", "RETRY"):
            return (r, 0), "DENIED", 0
        if a == "VERIFY":
            return h, "NOT_COMMITTED", 0
        if a == "COMPENSATE":
            return (0, 0), "COMPENSATED", 0
        if a == "WAIT":
            return h, "WAITED", 0
        if a in ("ESCALATE", "STOP_SAFE"):
            return (0, 1), "ESCALATED", 0
        return h, "NOOP", 0

    def obs_of(aug):
        return ("pub", aug.hidden[1], aug.used_escalate)

    return EpisodeSpec(
        name="c5_permission_denied_safe_escalate",
        initial_hidden=[(0, 0)],
        actions=ACTIONS,
        transition=trans,
        obs_key=obs_of,
        terminal=lambda a: a.hidden[1] == 1,
        goal_task=lambda a: False,
        goal_zero_residual=lambda a: a.hidden[1] == 1 and a.harm == 0,
        min_reachable_harm=0,
        expected_class="R3",
        notes="task impossible; escalation reaches zero-residual terminal",
    )


# ---------------------------------------------------------------------------
# C6: compensation failure leaves unavoidable residue; only containment (R4)
# h = (residue_unavoidable, stopped)  residue is created by the failing CALL.
# ---------------------------------------------------------------------------
def _c6():
    def trans(h, a):
        r, stopped = h
        if stopped:
            return h, "ALREADY", 0
        if a in ("CALL", "RETRY"):
            if r == 0:
                return (1, 0), "PARTIAL", 0  # irreversible residue appears (unavoidable)
            return (1, 0), "DUPLICATE", 1  # further attempts only add avoidable harm
        if a == "VERIFY":
            return h, ("PARTIAL" if r else "NOT_COMMITTED"), 0
        if a == "COMPENSATE":
            return (1, 0), "COMP_FAILED", 0  # cannot clear unavoidable residue
        if a == "WAIT":
            return h, "WAITED", 0
        if a in ("ESCALATE", "STOP_SAFE"):
            # terminal: unavoidable residue stays but is NOT avoidable harm
            return (1, 1), "ESCALATED", 0
        return h, "NOOP", 0

    def obs_of(aug):
        return ("pub", aug.hidden[1], aug.used_escalate)

    return EpisodeSpec(
        name="c6_comp_failure_unavoidable_residue",
        initial_hidden=[(0, 0)],
        actions=ACTIONS,
        transition=trans,
        obs_key=obs_of,
        terminal=lambda a: a.hidden[1] == 1,
        goal_task=lambda a: False,
        goal_zero_residual=lambda a: False,  # residue cannot be cleared
        min_reachable_harm=0,
        expected_class="R4",
        notes="unavoidable residue (excluded from harm); containment via escalate",
    )


# ---------------------------------------------------------------------------
# C7: same public observation, hidden delay variants; robust WAIT policy (R1)
# h = (delay, ticks, committed, done)
# ---------------------------------------------------------------------------
def _c7():
    def trans(h, a):
        delay, ticks, c, done = h
        if done:
            return h, "ALREADY", 0
        if a in ("CALL", "RETRY"):
            if c == 0:
                return (delay, ticks, 1, 0), "TIMEOUT", 0  # committed but invisible
            return (delay, ticks, 1, 0), "DUPLICATE", 1
        if a == "WAIT":
            t = ticks + 1
            if c == 1 and t >= delay:
                return (delay, t, 1, 1), "COMMITTED", 0
            return (delay, t, c, 0), "WAITED", 0
        if a == "VERIFY":
            if c == 1 and ticks >= delay:
                return (delay, ticks, 1, 1), "COMMITTED", 0
            return (delay, ticks, c, 0), "NOT_COMMITTED", 0
        if a == "COMPENSATE":
            return (delay, ticks, 0, 0), "COMPENSATED", 0
        if a in ("ESCALATE", "STOP_SAFE"):
            return (delay, ticks, c, 0), "ESCALATED", 0
        return h, "NOOP", 0

    def obs_of(aug):
        h = aug.hidden
        # delay is HIDDEN; ticks are the policy's own waits (observable count)
        return ("pub", h[3], h[2] == 1 and h[1] >= h[0], aug.used_compensate)

    return EpisodeSpec(
        name="c7_hidden_delay_variants",
        initial_hidden=[(1, 0, 0, 0), (2, 0, 0, 0), (3, 0, 0, 0)],
        actions=ACTIONS,
        transition=trans,
        obs_key=obs_of,
        terminal=lambda a: a.hidden[3] == 1,
        goal_task=lambda a: a.hidden[3] == 1,
        goal_zero_residual=lambda a: False,
        min_reachable_harm=0,
        expected_class="R1",
        notes="hidden delay 1..3 share obs; one robust WAIT-then-VERIFY policy works",
    )


# ---------------------------------------------------------------------------
# C8: non-robust partial reachability only -> UNKNOWN
# theta_good completes in 1 CALL; theta_bad can never complete, cannot stop
# without avoidable harm, and carries unavoidable residue so R3/R4 also fail.
# ---------------------------------------------------------------------------
def _c8():
    # h = (kind, residue, stopped) kind in {GOOD, BAD}
    def trans(h, a):
        kind, r, stopped = h
        if stopped or (kind == "GOOD" and r == 2):
            return h, "ALREADY", 0
        if a in ("CALL", "RETRY"):
            if kind == "GOOD":
                return ("GOOD", 2, 0), "OK", 0  # done marker r==2
            return ("BAD", 1, 0), "PARTIAL", 0  # unavoidable residue appears
        if a == "VERIFY":
            return h, "NOT_COMMITTED", 0
        if a == "COMPENSATE":
            return (kind, 1 if kind == "BAD" else r, 0), "COMP_FAILED", 0
        if a == "WAIT":
            return h, "WAITED", 0
        if a in ("ESCALATE", "STOP_SAFE"):
            # BAD branch: stopping charges avoidable harm 1 (min is 0)
            add = 1 if kind == "BAD" else 0
            return (kind, r, 1), "ESCALATED", add
        return h, "NOOP", 0

    def obs_of(aug):
        return ("pub", aug.hidden[2], aug.used_escalate)

    return EpisodeSpec(
        name="c8_partial_theta_unknown",
        initial_hidden=[("GOOD", 0, 0), ("BAD", 0, 0)],
        actions=ACTIONS,
        transition=trans,
        obs_key=obs_of,
        terminal=lambda a: a.hidden[2] == 1 or (a.hidden[0] == "GOOD" and a.hidden[1] == 2),
        goal_task=lambda a: a.hidden[0] == "GOOD" and a.hidden[1] == 2,
        goal_zero_residual=lambda a: a.hidden[2] == 1 and a.harm == 0 and a.hidden[1] != 1,
        min_reachable_harm=0,
        expected_class="UNKNOWN",
        notes="completion only for GOOD theta; BAD theta cannot reach any robust class",
    )


# ---------------------------------------------------------------------------
# C9: delayed commit visible after WAIT (R1)
# ---------------------------------------------------------------------------
def _c9():
    def trans(h, a):
        committed, visible, done = h
        if done:
            return h, "ALREADY", 0
        if a in ("CALL", "RETRY"):
            if committed == 0:
                return (1, 0, 0), "TIMEOUT", 0
            return (1, 0, 0), "DUPLICATE", 1
        if a == "WAIT":
            if committed == 1:
                return (1, 1, 1), "COMMITTED", 0
            return h, "WAITED", 0
        if a == "VERIFY":
            if visible:
                return (1, 1, 1), "COMMITTED", 0
            return h, "NOT_COMMITTED", 0
        if a == "COMPENSATE":
            return (0, 0, 0), "COMPENSATED", 0
        if a in ("ESCALATE", "STOP_SAFE"):
            return (committed, visible, 0), "ESCALATED", 0
        return h, "NOOP", 0

    def obs_of(aug):
        return ("pub", aug.hidden[2], aug.hidden[1])

    return EpisodeSpec(
        name="c9_delayed_commit",
        initial_hidden=[(0, 0, 0)],
        actions=ACTIONS,
        transition=trans,
        obs_key=obs_of,
        terminal=lambda a: a.hidden[2] == 1,
        goal_task=lambda a: a.hidden[2] == 1,
        goal_zero_residual=lambda a: False,
        min_reachable_harm=0,
        expected_class="R1",
        notes="commit invisible until WAIT; wait then complete",
    )


# ---------------------------------------------------------------------------
# C10: completion needs more steps than the horizon -> UNKNOWN
# escalation is a zero-residual safe terminal reachable within the horizon,
# so the classifier must NOT downgrade to R3 (57 F8 regression case).
# h = (ticks_done, stopped) ; need 6 WAITs then CALL; horizon test uses 4.
# ---------------------------------------------------------------------------
def _c10():
    def trans(h, a):
        t, stopped = h
        if stopped or t >= 7:
            return h, "ALREADY", 0
        if a == "WAIT":
            return (t + 1, 0), "WAITED", 0
        if a in ("CALL", "RETRY"):
            if t >= 6:
                return (7, 0), "OK", 0
            return (t, 0), "TOO_EARLY", 0
        if a == "VERIFY":
            return (t, 0), "NOT_COMMITTED", 0
        if a == "COMPENSATE":
            return (0, 0), "COMPENSATED", 0
        if a in ("ESCALATE", "STOP_SAFE"):
            return (t, 1), "ESCALATED", 0
        return h, "NOOP", 0

    def obs_of(aug):
        return ("pub", aug.hidden[0] >= 7, aug.hidden[1], aug.used_escalate)

    return EpisodeSpec(
        name="c10_depth_exceeded",
        initial_hidden=[(0, 0)],
        actions=ACTIONS,
        transition=trans,
        obs_key=obs_of,
        terminal=lambda a: a.hidden[0] >= 7 or a.hidden[1] == 1,
        goal_task=lambda a: a.hidden[0] >= 7,
        goal_zero_residual=lambda a: a.hidden[1] == 1 and a.harm == 0,
        min_reachable_harm=0,
        expected_class="UNKNOWN",
        notes="needs 7 steps; horizon=4 -> task UNKNOWN but safe-stop WIN -> must stay UNKNOWN; horizon=20 -> R1",
    )


# ---------------------------------------------------------------------------
# C11: duplicate side effect possible but avoidable by VERIFY policy (R1)
# same shape as C2; kept as its own ground-truth case per the required list.
# ---------------------------------------------------------------------------
def _c11():
    return _c2().__class__(
        name="c11_duplicate_avoidable",
        initial_hidden=[(0, 0, 0), (1, 0, 0)],
        actions=ACTIONS,
        transition=_c2().transition,
        obs_key=_c2().obs_key,
        terminal=_c2().terminal,
        goal_task=_c2().goal_task,
        goal_zero_residual=_c2().goal_zero_residual,
        min_reachable_harm=0,
        expected_class="R1",
        notes="blind RETRY duplicates on committed theta; VERIFY policy avoids harm",
    )


# ---------------------------------------------------------------------------
# C12: two-step saga; step-2 compensation failure leaves unavoidable residue,
# step-1 effect is avoidable residue unless compensated -> R4 (containment
# requires compensating step 1 before escalating).
# h = (step1, step2_residue, stopped)  step1 in {0,1}, step2_residue in {0,1}
# ---------------------------------------------------------------------------
def _c12():
    def trans(h, a):
        s1, s2, stopped = h
        if stopped:
            return h, "ALREADY", 0
        if a in ("CALL", "RETRY"):
            if s1 == 0:
                return (1, 0, 0), "OK_STEP1", 0
            if s2 == 0:
                return (1, 1, 0), "PARTIAL", 0  # step2 partial w/ irreversible residue
            return (1, 1, 0), "DUPLICATE", 1
        if a == "VERIFY":
            return h, ("PARTIAL" if s2 else ("OK_STEP1" if s1 else "NOT_COMMITTED")), 0
        if a == "COMPENSATE":
            # compensates the latest compensatable effect (step1); step2 residue stays
            return (0, s2, 0), "COMPENSATED", 0
        if a == "WAIT":
            return h, "WAITED", 0
        if a in ("ESCALATE", "STOP_SAFE"):
            # avoidable residue = leftover step1 effect (s1) if still present
            avoidable = 1 if s1 else 0
            return (s1, s2, 1), "ESCALATED", avoidable
        return h, "NOOP", 0

    def obs_of(aug):
        return ("pub", aug.hidden[2], aug.hidden[0], aug.hidden[1], aug.used_compensate)

    return EpisodeSpec(
        name="c12_saga_comp_failure_residue",
        initial_hidden=[(0, 0, 0)],
        actions=ACTIONS,
        transition=trans,
        obs_key=obs_of,
        terminal=lambda a: a.hidden[2] == 1,
        goal_task=lambda a: False,
        goal_zero_residual=lambda a: False,
        min_reachable_harm=0,
        expected_class="R4",
        notes="step2 residue unavoidable; step1 residue avoidable via COMPENSATE",
    )


def all_specs():
    return [
        _c1(), _c2(), _c3(), _c4(), _c5(), _c6(),
        _c7(), _c8(), _c9(), _c10(), _c11(), _c12(),
    ]
