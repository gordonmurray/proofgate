# Security policy

## Reporting a vulnerability

Please report suspected vulnerabilities privately using GitHub's
[private vulnerability reporting](https://docs.github.com/en/code-security/security-advisories/guidance-on-reporting-and-writing-information-about-vulnerabilities/privately-reporting-a-security-vulnerability)
on this repository, rather than opening a public issue.

Include enough detail to reproduce: affected component, steps, and impact. You can
expect an initial acknowledgement within a few days.

## Scope

This is a reference deployment. It ships infrastructure-as-code that you are expected to
review and adapt before running in your own account — in particular the IAM policies,
the OIDC trust relationship, and the ALB/TLS configuration. The committed defaults aim
for least privilege, but you own the risk in your environment.

No secrets are committed to this repository. Runtime configuration comes from the
environment; deploy credentials come from short-lived OIDC-assumed roles, never from
long-lived keys stored in CI.
