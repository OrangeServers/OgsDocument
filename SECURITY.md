# Security Policy

## Reporting a vulnerability

Do not report suspected vulnerabilities in a public issue, discussion, pull
request, screenshot, or chat transcript.

Use the repository's **Security → Report a vulnerability** flow to open a
private GitHub Security Advisory:

<https://github.com/OrangeServers/OrangeServer/security/advisories/new>

Include:

- affected version or commit;
- deployment model;
- prerequisites and impact;
- minimal reproduction steps;
- a proposed mitigation, if known.

Do not include real API keys, SSH credentials, cookies, private keys, database
dumps, internal host addresses, or personal information. Use synthetic values
and attach only the minimum evidence needed.

Maintainers will acknowledge the report through the private advisory, assess
severity, coordinate a fix, and publish remediation information when users can
upgrade safely. No fixed response SLA is promised by this community project.

## Supported versions

Security fixes target the current default branch and the latest published
release when practical. Older commits and private forks are not guaranteed to
receive backports. Deployers should follow the
[upgrade guide](docs/operations/UPGRADE.md) and verify the current changelog.

## Deployment security baseline

OrangeServer is security-sensitive software. Production operators are
responsible for:

- changing the initial administrator password immediately;
- using HTTPS and a correct CSRF origin allowlist;
- using dedicated, least-privilege MySQL, Redis, and SSH identities;
- protecting and rotating Flask, Fernet, database, Redis, and Provider secrets;
- restricting application, database, Redis, SSH, and Provider network paths;
- choosing a strict SSH host-key policy appropriate for the environment;
- backing up encrypted data together with the required Fernet key history;
- reviewing command, login, and operation audit logs;
- testing upgrades and rollback outside production.

Enabling `OGS_AI_ALLOW_PRIVATE_PROVIDER=1` relaxes one SSRF protection and must
only be done for a controlled internal model gateway with independent network
controls.

See [architecture and trust boundaries](docs/architecture/TRUST_BOUNDARIES.md)
for the current AI and execution model.

## Scope reminders

The current AI assistant cannot be trusted as an authorization or audit source.
Only server-side permission checks, action snapshots, execution results, and
audit records are authoritative.

The project does not authorize testing against infrastructure you do not own or
have explicit permission to assess.
