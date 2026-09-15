# Security Policy

## Reporting a vulnerability

Please report suspected vulnerabilities **privately**, using GitHub's
[private vulnerability reporting](https://docs.github.com/en/code-security/security-advisories/guidance-on-reporting-and-writing-information-about-vulnerabilities/privately-reporting-a-security-vulnerability)
form on the **Security** tab of this repository.

If that form is not available to you, open a public issue that contains **no
details** — only a request for a private channel — and a maintainer will
follow up.

Please include:

- what the issue is, and where (path, and the commit or lock revision if known);
- the smallest reproduction you can manage;
- the impact you believe it has;
- whether you intend to disclose it publicly, and on what timeline.

## Scope

This repository is a benchmark harness for capability evaluation. The harness
executes benchmark arms inside a Docker sandbox (`harness/dockersandbox.py`)
and pins an execution lock (`benchmarks/fam-c/EXECUTION-LOCK.json`) that
freezes the harness manifest, the arm configuration, and the recorded
evidence.

**In scope**

- escapes from the sandbox/containment boundary, or denials that can be
  bypassed (path bans, mount and volume restrictions, network policy);
- disclosure of credentials, tokens, or host paths through harness code,
  generated reports, or the secret-scan step in CI;
- tampering with the execution lock, the frozen manifest, or the recorded
  evidence without the lock re-mint path (`harness/mint_execution_lock.py`)
  noticing;
- benchmark results that can be forged, replayed, or selectively reported by
  a malicious arm.

**Out of scope**

- findings in the **data** under `benchmarks/**/runs/` — those are recorded
  artifacts of past executions, kept verbatim as evidence, not executable
  code;
- the behaviour of the models or arms under test, including output that is
  wrong, offensive, or unsafe — that is a measurement result, not a
  vulnerability in this repository;
- missing hardening that requires the sandbox to be given additional
  privileges in the first place.

## What to expect

This project is maintained on a best-effort basis; there is no formal
response SLA. Reports that include a reproduction are far easier to act on
quickly. We will credit reporters in the resulting advisory unless you ask us
not to.

## Secrets

No credentials belong in this repository. CI runs a pattern-based secret scan
on every branch as a lint, not a guarantee — if you find a credential that the
scan missed, treat it as a vulnerability and report it privately rather than
opening an issue.
