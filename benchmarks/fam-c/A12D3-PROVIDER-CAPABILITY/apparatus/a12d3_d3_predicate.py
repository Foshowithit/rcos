#!/usr/bin/env python3
"""A12D3 / D3 frozen predicate, failure vocabulary, and reason mapping.

THIS FILE IS NOT A13 CODE AND AWARDS NO ELIGIBILITY.

The predicate text below is FROZEN by contract.  It is reproduced here as the
single source of truth: the harness computes the conjunct dict, this module turns
that dict into the predicate and into exactly one reason code, and the independent
checker (a12d3_d3_independent_checker.py) recomputes the same dict from raw
artifacts and re-runs the same functions.  Nothing here trusts a harness summary
line.

FROZEN FAILURE VOCABULARY -- exactly three codes are permitted:
    PROVIDER_CAPABILITY_INHERITED
    PROVIDER_CAPABILITY_ATTEMPT
    PROVIDER_BROKER_REACHABLE

Design intent, stated once so the controls are not mistaken for plumbing:

  D2 established that the counterfactual legs created zero additional cognition
  and that known provider artifacts were not statically reachable from them.
  D2's evidence was therefore about OPPORTUNITY ("nothing extra happened") and
  about STATIC REACHABILITY ("no provider marker was reachable in the binary").

  D3 asks a strictly stronger question that D2's mechanism cannot answer: even if
  no extra cognition occurred, did the legs POSSESS a usable provider-cognition
  capability?  A process can hold a live, already-connected provider socket and
  never use it -- opportunity counts stay at zero and static marker scans stay
  clean, yet the capability was possessed and could have been exercised.

  That is why D3's core evidence is a KERNEL-ENFORCED capability set measured
  from OUTSIDE the process at a barrier, and why two controls (D3-B, D3-E) are
  required to FAIL while D1 reports ZERO provider delta.  Those two arms are the
  falsifiers of any argument that counts-only or markers-only evidence suffices.
"""

from __future__ import annotations

import json

# ---------------------------------------------------------------------------
# The frozen predicate, verbatim.
# ---------------------------------------------------------------------------

COUNTERFACTUAL_PROVIDER_CAPABILITY_DENIED_TEXT = (
    "COUNTERFACTUAL_PROVIDER_CAPABILITY_DENIED := "
    "LEG_ENTRY_IDENTITIES_PRECOMMITTED AND "
    "LEG_DESCRIPTOR_ALLOWLIST_PRECOMMITTED AND "
    "LEG_DESCRIPTOR_SET_MEASURED AND "
    "NO_PROVIDER_CAPABLE_DESCRIPTOR_INHERITED AND "
    "NO_PROVIDER_CAPABLE_BROKER_ENDPOINT_INHERITED AND "
    "NETWORK_CREATION_DENIED_AFTER_LEG_ENTRY AND "
    "PROCESS_CREATION_DENIED_AFTER_LEG_ENTRY AND "
    "EXEC_DENIED_AFTER_LEG_ENTRY AND "
    "KERNEL_DENIAL_POLICY_PRECOMMITTED AND "
    "KERNEL_DENIAL_POLICY_ACTIVE_AT_POINT_OF_USE AND "
    "HONEST_COUNTERFACTUAL_LEGS_COMPLETE AND "
    "D1_PROVIDER_OPPORTUNITY_DELTA_ZERO AND "
    "TOTAL_MODEL_CELL_COUNT_UNCHANGED AND "
    "ORDER_CELL_COUNT_UNCHANGED AND "
    "ALL_CAPABILITY_BINDINGS_RECONCILED"
)

# Ordered exactly as they appear in the frozen predicate text.
CONJUNCTS = (
    "LEG_ENTRY_IDENTITIES_PRECOMMITTED",
    "LEG_DESCRIPTOR_ALLOWLIST_PRECOMMITTED",
    "LEG_DESCRIPTOR_SET_MEASURED",
    "NO_PROVIDER_CAPABLE_DESCRIPTOR_INHERITED",
    "NO_PROVIDER_CAPABLE_BROKER_ENDPOINT_INHERITED",
    "NETWORK_CREATION_DENIED_AFTER_LEG_ENTRY",
    "PROCESS_CREATION_DENIED_AFTER_LEG_ENTRY",
    "EXEC_DENIED_AFTER_LEG_ENTRY",
    "KERNEL_DENIAL_POLICY_PRECOMMITTED",
    "KERNEL_DENIAL_POLICY_ACTIVE_AT_POINT_OF_USE",
    "HONEST_COUNTERFACTUAL_LEGS_COMPLETE",
    "D1_PROVIDER_OPPORTUNITY_DELTA_ZERO",
    "TOTAL_MODEL_CELL_COUNT_UNCHANGED",
    "ORDER_CELL_COUNT_UNCHANGED",
    "ALL_CAPABILITY_BINDINGS_RECONCILED",
)

PREDICATE_NAME = "COUNTERFACTUAL_PROVIDER_CAPABILITY_DENIED"

# ---------------------------------------------------------------------------
# Frozen failure vocabulary -- these three and no others.
# ---------------------------------------------------------------------------

PROVIDER_CAPABILITY_INHERITED = "PROVIDER_CAPABILITY_INHERITED"
PROVIDER_CAPABILITY_ATTEMPT = "PROVIDER_CAPABILITY_ATTEMPT"
PROVIDER_BROKER_REACHABLE = "PROVIDER_BROKER_REACHABLE"

FAILURE_VOCABULARY = (
    PROVIDER_CAPABILITY_INHERITED,
    PROVIDER_CAPABILITY_ATTEMPT,
    PROVIDER_BROKER_REACHABLE,
)

# A clean leg that satisfies the predicate reports no reason code at all.
NO_FAILURE = "NONE"

# ---------------------------------------------------------------------------
# Which conjunct DISPROVES which code, and the escalation order.
#
# The order is the contract, not a preference.  Possession outranks attempt:
# if a leg both INHERITED a provider-capable descriptor and later attempted a
# fresh network call, the finding is INHERITED, because the inherited endpoint
# is the stronger fact -- the capability was already in hand before the leg ran,
# which is precisely what the counterfactual must deny.
# ---------------------------------------------------------------------------

REASON_ESCALATION = (
    # 1. Possession of a provider-capable descriptor (D3-B).
    PROVIDER_CAPABILITY_INHERITED,
    # 2. Reachability of a broker endpoint that would translate leg bytes into a
    #    provider request (D3-E).  Also possession, but of an INDIRECT channel.
    PROVIDER_BROKER_REACHABLE,
    # 3. An actual attempted use that the kernel denied (D3-C, D3-D).
    PROVIDER_CAPABILITY_ATTEMPT,
)

# Maps each reason code to the conjuncts whose falsity proves it.
REASON_DISPROVED_BY = {
    PROVIDER_CAPABILITY_INHERITED: (
        "NO_PROVIDER_CAPABLE_DESCRIPTOR_INHERITED",
        "LEG_DESCRIPTOR_SET_MEASURED",
        "LEG_DESCRIPTOR_ALLOWLIST_PRECOMMITTED",
    ),
    PROVIDER_BROKER_REACHABLE: (
        "NO_PROVIDER_CAPABLE_BROKER_ENDPOINT_INHERITED",
    ),
    PROVIDER_CAPABILITY_ATTEMPT: (
        "NETWORK_CREATION_DENIED_AFTER_LEG_ENTRY",
        "PROCESS_CREATION_DENIED_AFTER_LEG_ENTRY",
        "EXEC_DENIED_AFTER_LEG_ENTRY",
    ),
}

# ---------------------------------------------------------------------------
# Arm expectations.  Every arm states, per control, the required semantic
# outcome and the required control outcome.  The harness asserts the OBSERVED
# pair equals this table; a mismatch is a RED control, not a nuance.
# ---------------------------------------------------------------------------

ARM_A = "D3-A"
ARM_B = "D3-B"
ARM_C = "D3-C"
ARM_D = "D3-D"
ARM_E = "D3-E"

ARM_ORDER = (ARM_A, ARM_B, ARM_C, ARM_D, ARM_E)

ARM_DESCRIPTIONS = {
    ARM_A: "CLEAN CLOSED LEGS: exact allowlisted descriptors, kernel policy "
           "active, all three legs consume the sealed response and complete "
           "normally, D1 provider delta = 0 -> semantic PASS",
    ARM_B: "INHERITED PROVIDER CHANNEL: one leg is handed an already-connected "
           "gate/provider socket whose branch is NEVER used; runtime provider "
           "delta stays 0; the binary may contain zero provider markers and the "
           "arm must still FAIL. This is the deliberate falsifier against D2-E.",
    ARM_C: "DIRECT NETWORK ATTEMPT: no provider descriptor inherited; the leg "
           "attempts generic socket/connect after entry; the kernel denies it "
           "with EACCES -> semantic FAIL PROVIDER_CAPABILITY_ATTEMPT",
    ARM_D: "CHILD/EXEC ESCAPE: the leg attempts to create a child and exec a "
           "provider-capable helper after entry; the kernel denies both -> "
           "semantic FAIL PROVIDER_CAPABILITY_ATTEMPT",
    ARM_E: "PROVIDER BROKER: the leg receives an otherwise innocent pipe/"
           "socketpair whose peer process would translate leg bytes into a "
           "provider request; the branch is NEVER exercised -> semantic FAIL "
           "PROVIDER_BROKER_REACHABLE",
}

# Expected (semantic_ok, primary_reason) per arm.
ARM_EXPECTATION = {
    ARM_A: (True, NO_FAILURE),
    ARM_B: (False, PROVIDER_CAPABILITY_INHERITED),
    ARM_C: (False, PROVIDER_CAPABILITY_ATTEMPT),
    ARM_D: (False, PROVIDER_CAPABILITY_ATTEMPT),
    ARM_E: (False, PROVIDER_BROKER_REACHABLE),
}

# Which arms are REQUIRED to fail while D1 still reports zero provider delta.
# This is the D2-E falsifier requirement, encoded so it cannot be quietly
# relaxed: these arms must show zero_extra_provider_opportunity == True AND
# semantic_ok == False.  An arm that "fails" only because it managed a second
# provider call does not demonstrate capability possession and is rejected.
FALSIFIER_ARMS_REQUIRE_ZERO_PROVIDER_DELTA = (ARM_B, ARM_E)

# ---------------------------------------------------------------------------
# The mandated in-leg sequencing, with the release point last.
#
# This ordering is load-bearing and was explicitly refined by contract.  The
# forbidden sequence (measure clean FDs -> release leg -> install seccomp) opens
# a capability window in which the leg runs UNFILTERED between measurement and
# policy activation.  D3 therefore requires the policy installed BEFORE the leg
# reaches its entry barrier, and requires the descriptor measurement, the
# activation evidence, and the allowlist reconciliation all to happen while the
# leg is still blocked at that barrier.
# ---------------------------------------------------------------------------

SEQUENCE_STEPS = (
    "LEG_PROCESS_START",
    "DENIAL_POLICY_INSTALLED",
    "ENTRY_BARRIER_REACHED",
    "DESCRIPTOR_SET_MEASURED_EXTERNALLY",
    "POLICY_ACTIVATION_EVIDENCED",
    "DESCRIPTOR_ALLOWLIST_RECONCILED",
    "BUSINESS_LOGIC_RELEASED",
)

# Prefix semantics implied by the frozen conjunct names: everything before the
# release point is what "AFTER_LEG_ENTRY" can be claimed for, and the two
# "_AT_POINT_OF_USE" / "_PRECOMMITTED" conjuncts pin the policy to the right side
# of the barrier.
FORBIDDEN_SEQUENCE = (
    "LEG_PROCESS_START",
    "DESCRIPTOR_SET_MEASURED_EXTERNALLY",   # measured clean ...
    "BUSINESS_LOGIC_RELEASED",              # ... then released ...
    "DENIAL_POLICY_INSTALLED",              # ... then filtered  <-- capability window
)


# ---------------------------------------------------------------------------
# Predicate evaluation
# ---------------------------------------------------------------------------

def evaluate_predicate(conjuncts: dict) -> dict:
    """Compute the frozen predicate from a conjunct dict.

    Every conjunct must be present and exactly True for the predicate to hold.
    A missing conjunct is a structural defect, not a False: it means the raw
    evidence for that clause was never produced, which is a different failure
    from the clause being false.  Both make the predicate false, but the
    missing case is reported separately so it cannot hide as a legitimate
    negative.
    """
    missing = [name for name in CONJUNCTS if name not in conjuncts]
    values = {name: bool(conjuncts.get(name)) for name in CONJUNCTS}
    falsified = [name for name in CONJUNCTS if not values[name]]
    return {
        "predicate": PREDICATE_NAME,
        "predicate_text": COUNTERFACTUAL_PROVIDER_CAPABILITY_DENIED_TEXT,
        "conjuncts": values,
        "conjunct_order": list(CONJUNCTS),
        "missing_conjuncts": missing,
        "structural_defect": bool(missing),
        "falsified_conjuncts": falsified,
        "falsified_count": len(falsified),
        "value": not missing and not falsified,
    }


def map_reason(conjuncts: dict, extra_signals: dict | None = None) -> dict:
    """Return exactly one reason code, by contract escalation order.

    Precedence, highest first:
      1. structural defect (a required conjunct was never measured)
      2. INHERITED  -- a provider-capable descriptor was held
      3. BROKER     -- a broker endpoint that converts leg bytes was reachable
      4. ATTEMPT    -- a use was attempted and the kernel denied it

    `extra_signals` carries the specific measurements the reason is bound to
    (which fd, which peer, which syscall) so the code is always accompanied by
    the raw fact that produced it.  A reason code without a binding is not
    reportable evidence.
    """
    extra_signals = extra_signals or {}
    predicate = evaluate_predicate(conjuncts)

    if predicate["structural_defect"]:
        return {
            "reason": NO_FAILURE,
            "reason_kind": "STRUCTURAL_DEFECT",
            "bound_signals": {"missing_conjuncts":
                              predicate["missing_conjuncts"]},
            "note": "required raw evidence absent; this is not a semantic "
                    "result",
        }

    if not conjuncts.get("NO_PROVIDER_CAPABLE_DESCRIPTOR_INHERITED", False) or \
            not conjuncts.get("LEG_DESCRIPTOR_SET_MEASURED", False):
        return {
            "reason": PROVIDER_CAPABILITY_INHERITED,
            "reason_kind": "POSSESSION",
            "bound_signals": extra_signals.get(
                "provider_capable_descriptors", {}),
        }

    if not conjuncts.get("NO_PROVIDER_CAPABLE_BROKER_ENDPOINT_INHERITED",
                         False):
        return {
            "reason": PROVIDER_BROKER_REACHABLE,
            "reason_kind": "POSSESSION_INDIRECT",
            "bound_signals": extra_signals.get("broker_endpoints", {}),
        }

    denied = {
        "NETWORK_CREATION_DENIED_AFTER_LEG_ENTRY":
            extra_signals.get("network_denials", {}),
        "PROCESS_CREATION_DENIED_AFTER_LEG_ENTRY":
            extra_signals.get("process_denials", {}),
        "EXEC_DENIED_AFTER_LEG_ENTRY":
            extra_signals.get("exec_denials", {}),
    }
    if any(not conjuncts.get(name, False) for name in denied):
        return {
            "reason": PROVIDER_CAPABILITY_ATTEMPT,
            "reason_kind": "ATTEMPTED_USE_DENIED",
            "bound_signals": denied,
        }

    return {
        "reason": NO_FAILURE,
        "reason_kind": "CLEAN",
        "bound_signals": {},
    }


def check_arm_expectation(arm: str, semantic_ok: bool,
                          primary_reason: str) -> dict:
    """Compare an arm's observed outcome against its required outcome."""
    expected = ARM_EXPECTATION.get(arm)
    if expected is None:
        return {"arm": arm, "known_arm": False, "control_ok": False,
                "expected": None, "observed": [semantic_ok, primary_reason]}
    expected_ok, expected_reason = expected
    return {
        "arm": arm,
        "known_arm": True,
        "expected_semantic_ok": expected_ok,
        "expected_reason": expected_reason,
        "observed_semantic_ok": semantic_ok,
        "observed_reason": primary_reason,
        "control_ok": (semantic_ok == expected_ok
                       and primary_reason == expected_reason),
    }


def falsifier_requirement_satisfied(arm: str, semantic_ok: bool,
                                    zero_provider_delta: bool) -> dict:
    """For D3-B and D3-E: must fail WITH zero extra provider opportunity.

    This is the conjunct that makes D3 strictly stronger than D2.  A failing arm
    that actually performed a second provider call proves only that the leg used
    a channel; it does NOT prove the leg possessed a capability that counted
    zero.  The requirement is therefore a conjunction of "failed" AND "no
    provider delta", and it is checked explicitly rather than assumed.
    """
    required = arm in FALSIFIER_ARMS_REQUIRE_ZERO_PROVIDER_DELTA
    return {
        "arm": arm,
        "falsifier_arm": required,
        "observed_semantic_ok": semantic_ok,
        "observed_zero_provider_delta": zero_provider_delta,
        "satisfied": (not required) or ((not semantic_ok)
                                        and bool(zero_provider_delta)),
        "requirement": ("must FAIL while D1 reports ZERO provider opportunity "
                        "delta" if required else "not a falsifier arm"),
    }


def summary_line(arm: str, semantic_ok: bool, reason: str) -> str:
    return "%s semantic=%s reason=%s" % (
        arm, "PASS" if semantic_ok else "FAIL", reason)


if __name__ == "__main__":
    all_true = {name: True for name in CONJUNCTS}
    predicate = evaluate_predicate(all_true)
    print(json.dumps({
        "predicate_text": COUNTERFACTUAL_PROVIDER_CAPABILITY_DENIED_TEXT,
        "conjunct_count": len(CONJUNCTS),
        "predicate_holds_when_all_true": predicate["value"],
        "failure_vocabulary": list(FAILURE_VOCABULARY),
        "reason_escalation": list(REASON_ESCALATION),
        "arms": {arm: {"expectation": list(ARM_EXPECTATION[arm]),
                       "description": ARM_DESCRIPTIONS[arm]}
                 for arm in ARM_ORDER},
        "sequence_steps": list(SEQUENCE_STEPS),
        "forbidden_sequence": list(FORBIDDEN_SEQUENCE),
        "falsifier_arms": list(FALSIFIER_ARMS_REQUIRE_ZERO_PROVIDER_DELTA),
    }, indent=2, sort_keys=True))
