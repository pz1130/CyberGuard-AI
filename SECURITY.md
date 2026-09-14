# Security Policy

## Supported versions

Security fixes are provided for the most recent tagged release candidate or
stable release only.

## Reporting a vulnerability

Do not open a public issue containing exploit details, credentials, personal
data, or affected deployment information.

The designated channel for this repository is GitHub Private Vulnerability
Reporting:

https://github.com/pz1130/CyberGuard-AI/security/advisories/new

Include the affected version, reproduction steps, impact, and any suggested
mitigation. Do not attach live credentials or customer data.

The Security owner must enable Private vulnerability reporting in the GitHub
repository settings before public release (Settings → Code security). Until
that toggle is on, reports go to the Security owner named in
`docs/delivery/RC_EVIDENCE.md` by a private out-of-band channel the workgroup
already uses. Do not invent a personal mailbox in this file.

## Deployment responsibility

This repository is a reference implementation. Operators remain responsible
for network controls, TLS termination, identity configuration, secret custody,
provider approval, logging, retention, patching, and local security assessment.
