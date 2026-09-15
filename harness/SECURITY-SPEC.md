# SECURITY SPECIFICATION - claim-grade execution containment

Status: BINDING (GPT Ruling 3, N1 backend-boundary hardening).
Owner: harness (`harness/containment.py` is the machine-readable half of this
document; the two are checked against each other at run time).
Scope: every execution whose result may be cited as a **claim** (a Fam-C
cell verdict, an N1 isolation result, an A13 causal receipt, a promotion
decision). Executions that are explicitly labelled dev/test are out of
scope for the *claim*, never for the *labelling*.

---

## 1. Why this document exists

The N1 adversarial run showed that the two-jail **shim** cannot carry the
isolation guarantee: the shim runs the candidate as a host process, so
/proc seen from inside it is the HOST /proc. That is a disclosed
instrument limit, not a defect in the harness - but it means the N1 result
is only as strong as the **backend** that produced it. The guarantee is
carried by the CONTAINER, not by the adapter shape. Claim-grade execution
therefore has a hard, named backend requirement, and a run that cannot
meet it must refuse rather than quietly degrade.

A control that is only written down is not a control. Every requirement
below has a machine check in `harness/containment.py` and a literal
observation in the unit that hardened it.

---

## 2. Claim-grade containment backend registry

<!-- CONTAINMENT-BACKEND-REGISTRY v1 - machine-read by
     containment.security_spec_backends(); one marker line per backend,
     exact spelling, do not reformat without re-running the unit. -->

CLAIM-GRADE-BACKEND: DockerSandbox

**`DockerSandbox` is explicitly the claim-grade containment backend.**
It is the only backend named above, and the only backend permitted to
carry a claim. Its implementation is `harness/dockersandbox.py`, and its
enforcement is the container configuration actually in force per
invocation (pinned by digest, recorded in every run manifest):

| enforcement | value |
| --- | --- |
| network namespace | `--network none` (no interface, no route, no DNS) |
| mounts | exactly `<assigned_workdir>:/work:rw` and `<visible_root>:/task:ro` |
| image | `python:3.12-slim@sha256:78387bc3881b8273120a12ebe6c1ab22b018ccc2c9adf565ae1ac9b536e184ea` |
| user / fs | `--user <invoking-uid>`, `--read-only`, `--tmpfs /tmp:rw,noexec,nosuid,size=64m` |
| capabilities | `--cap-drop=ALL` |
| limits | `--pids-limit 64`, `--memory 1g` |
| env | constructed allowlist only; host env and all secrets never enter |

The backend identity is established **structurally**, never by a
caller-supplied string:

* exact Python class identity with the production
  `dockersandbox.DockerSandbox` object (a subclass is NOT the production
  class and is NOT claim-grade);
* at least one container id written by the **Docker daemon** itself
  through `--cidfile` (64 lowercase hex; the harness only ever reads that
  file, so the id is daemon-authored evidence that a container really ran);
* the pinned image digest above;
* the containment flags above present in the container launch base.

---

## 3. Test doubles - formal classification

Any containment-shaped object that is not the exact production
`DockerSandbox` class is **a non-security-bearing test double**. This is a
definition, not an opinion, and it is enforced in code:
`containment.classify()` returns `security_bearing = False` and a
classification of "test-double (non-security-bearing)" for every such
object.

Known test doubles in this tree, each annotated at its definition:

| double | defined in | role |
| --- | --- | --- |
| `ShimJail` | `harness/tests/smoke_h23_d1.py` | host-process jail for H23 isolation cases |
| `CandidateJail` / `LocalJail` | `harness/tests/smoke_h19_a12c.py` | host-process two-jail fixture |
| `_ShimJail` | `harness/tests/smoke_h35_a13.py` | host-process jail for A13 smoke legs |
| `_EngineShim` | `harness/tests/smoke_h34_d13.py` | host-process engine double |
| `ShimSandbox` | `harness/tests/smoke_h34_d13.py` | dockerless sandbox stand-in mirroring the `manifest()` keys |
| `_Jail` | `harness/tests/smoke_h34_d13.py` | bare host-process jail double |
| `_BrokenJail` | `harness/tests/smoke_h23_d1.py` | always-refusing jail double (denial-path fixture) |

A test double may be used freely to test *harness logic* (staging, order,
denial paths, chain wiring). It may never be used to produce, or to
corroborate, a **claim**. Its results are structurally incapable of
satisfying `CLAIM_GRADE_CONTAINMENT_VALID` (section 5), because the
predicate reads the exact class identity and the daemon-authored
container ids, neither of which a shim can present.

---

## 4. Fail-closed rule

Claim-grade execution **must fail closed if Docker is unavailable**:

1. There is **no silent shim fallback**. No code path substitutes a test
   double for the production backend. Substitution would require editing
   code that raises; it cannot be reached by configuration, environment,
   or a defaulted flag.
2. Construction of a containment jail on a host whose Docker daemon is
   unreachable **raises** `containment.ContainmentRefusal` with the named
   reason `CONTAINMENT-BACKEND-UNAVAILABLE`. It does not warn, does not
   log-and-continue, does not return a defaulted object, and does not
   start a host-process fallback.
3. A claim-grade run whose manifest containment binding does not satisfy
   `CLAIM_GRADE_CONTAINMENT_VALID` **raises**
   `CLAIM-GRADE-CONTAINMENT-REFUSED` naming the failed clauses, and emits no
   verdict.

Refusal is a real control-flow refusal on the path that produces the
claim. It is never a comment, a warning, a log line, a defaulted boolean,
or a swallowed exception.

---

## 5. The predicate

Verbatim from GPT Ruling 3 (question 4):

    CLAIM_GRADE_CONTAINMENT_VALID :=
          backend == DockerSandbox
      AND backend_named_in_security_spec
      AND shim_classified_non_security_bearing
      AND no_silent_shim_fallback
      AND docker_unavailable_fails_closed
      AND manifest_binds_containment_backend
      AND shim_cannot_satisfy_N1

Implemented as `containment.claim_grade_containment_valid(binding)`, which
returns `(bool, {clause: bool})` and evaluates each clause from recorded raw
values plus the on-disk bytes of this document - never from a
caller-supplied verdict. One clause is deliberately **stricter** than
the literal text, so PASS is strictly harder to obtain: `backend` also
requires the pinned image and the containment flags.

`shim_cannot_satisfy_N1` is evaluated **structurally** from exact class
identity, so a test double can never satisfy it. The daemon-written
container-id observation is recorded in the binding
(`container_id_evidence`, `daemon_container_id_count`) and reported, but it
is deliberately **not** a pass gate: the run manifest binds the containment
backend *before* the arrival jail first launches, so a gate there would
refuse legitimate claim-grade runs while proving nothing a shim could not
fake. A shim fails this clause on class identity alone.

---

## 6. Residual limits (disclosed, not waived)

* **In-process forgery is outside the TCB.** The predicate defends
  against *accidental and structural* substitution by a test double - a
  different class, a subclass, or a hand-built dict. Code that
  deliberately forges a `DockerSandbox` instance inside the harness process
  is outside the trust boundary, exactly as it is for every other
  launcher property in `harness/dockersandbox.py` (see its "trust boundary
  is correct" note).
* **The shim /proc observation remains a host /proc observation.** This
  document does not repair that; it removes the shim ability to carry a
  claim in the first place.
* **Two clauses are about this SPEC and about the MANIFEST, not about
  the backend.** `backend_named_in_security_spec` reads this document, so
  it is true for every binding - that is its purpose: the spec names
  `DockerSandbox` unconditionally, which is what makes a non-Docker
  backend refusable. `manifest_binds_containment_backend` reads only that
  a schema-valid `containment` record is PRESENT in the run manifest. On
  their own neither clause discriminates a shim-bound manifest from a
  `DockerSandbox`-bound one. The discriminating clauses are `backend`,
  `shim_classified_non_security_bearing` and `shim_cannot_satisfy_N1`, and
  the predicate is the conjunction: one false clause refuses. This was
  observed literally in the negative control - a shim-bound manifest scored
  `backend_named_in_security_spec = true` and
  `manifest_binds_containment_backend = true`, and was still refused on the
  other five clauses with `CLAIM-GRADE-CONTAINMENT-REFUSED`.
* **Container ids are verified as daemon-authored, not re-inspected.**
  `docker run --rm` removes the container at exit, so the id cannot be
  re-inspected afterwards; the evidence is the daemon-written cidfile
  read by the launcher.
