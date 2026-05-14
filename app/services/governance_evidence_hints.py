"""Canonical evidence checklists per control.

These are framework-version-stable suggestions an auditor would typically
ask for. They are intentionally generic enough to apply to most orgs but
specific enough to be actionable.

Keyed by `(framework_urn, ref_id)` → `list[str]`.

NB: only entries for the CURRENT seed framework versions are kept here.
If a framework is later imported via the JSON endpoint, callers may
supply their own `typical_evidence` field per requirement.
"""

# ---------------------------------------------------------------------------
# ISO/IEC 27001:2022 Annex A — implementation guidance drawn from ISO 27002:2022
# ---------------------------------------------------------------------------

ISO_27001_2022_EVIDENCE: dict[str, list[str]] = {
    # A.5 Organizational controls --------------------------------------------
    "A.5.1": [
        "Approved Information Security Policy (PDF/Confluence) with version, date, approver",
        "Topic-specific policies (access control, acceptable use, cryptography, BCP, …) and their changelog",
        "Annual policy review record with stakeholder sign-off",
        "Communication evidence (training register, all-hands deck, intranet announcement)",
    ],
    "A.5.2": [
        "RACI matrix mapping security responsibilities to job roles or teams",
        "Job descriptions for CISO / security manager / control owners",
        "Org chart showing reporting lines for security function",
    ],
    "A.5.3": [
        "List of incompatible duties and how they are separated (e.g. dev vs prod deploy)",
        "Access control matrix showing compensating controls where SoD is not possible",
        "Periodic SoD conflict review report",
    ],
    "A.5.4": [
        "Management approval records for the ISMS (e.g. ISMS committee minutes)",
        "Management Review minutes covering security KPIs, incidents, risks",
    ],
    "A.5.5": [
        "Contact list with regulators, CERT/CSIRT, law-enforcement liaison",
        "Procedure for engaging authorities during an incident",
    ],
    "A.5.6": [
        "Memberships in security ISACs / industry forums (FIRST, ISACA, OWASP, vendor-specific)",
        "Threat-intel feed subscriptions",
    ],
    "A.5.7": [
        "Threat intelligence subscription / platform configuration (e.g. MISP, ThreatConnect)",
        "Periodic threat-intel briefing report",
        "Documented intel-to-control feedback loop",
    ],
    "A.5.8": [
        "Project intake form requiring a security risk question",
        "Sample project plan showing security checkpoints / gates",
    ],
    "A.5.9": [
        "Asset inventory export (CMDB / spreadsheet) with owner, classification, location",
        "Inventory review record (quarterly reconciliation)",
    ],
    "A.5.10": [
        "Acceptable Use Policy signed by users",
        "Onboarding training completion records",
    ],
    "A.5.11": [
        "Offboarding checklist with asset-return step",
        "Sample completed offboarding tickets",
    ],
    "A.5.12": [
        "Data classification scheme (Public / Internal / Confidential / Restricted)",
        "Mapping of data types to classification levels with examples",
    ],
    "A.5.13": [
        "Labelling standard (header/footer templates, file-name conventions, document watermarks)",
        "Sample classified documents showing labels in use",
    ],
    "A.5.14": [
        "Secure-transfer procedure (SFTP, encrypted email, MFT) with approved channels",
        "Logs / configs of MFT or DLP showing enforcement",
    ],
    "A.5.15": [
        "Access Control Policy",
        "Role-to-permission matrix per critical system",
        "Joiner/Mover/Leaver workflow evidence (tickets, screenshots)",
    ],
    "A.5.16": [
        "Identity lifecycle SOP",
        "Unique-ID enforcement evidence (no shared accounts, or compensating controls)",
        "Periodic stale-account audit",
    ],
    "A.5.17": [
        "Password / secret policy (length, complexity, rotation, vault usage)",
        "Secrets manager configuration (Vault, AWS SM, 1Password Business) screenshots",
    ],
    "A.5.18": [
        "Privileged-access provisioning workflow with approval",
        "Quarterly access recertification report",
        "Sample termination ticket showing same-day revocation",
    ],
    "A.5.19": [
        "Supplier security policy",
        "Vendor inventory with risk tiering",
    ],
    "A.5.20": [
        "Template DPA / security addendum for vendor contracts",
        "Sample executed contracts containing security clauses",
    ],
    "A.5.21": [
        "Supply-chain security requirements doc (SBOM, code-signing, secure delivery)",
        "Vendor SBOM (CycloneDX/SPDX) for a critical product",
    ],
    "A.5.22": [
        "Vendor performance / security review report (annual or per-renewal)",
        "Change-management evidence when a key supplier changes substantially",
    ],
    "A.5.23": [
        "Cloud-usage register (CSPs, services, owners, criticality)",
        "Shared-responsibility matrix per CSP",
        "Cloud security baselines (CIS / vendor benchmarks) and conformance scan",
    ],
    "A.5.24": [
        "Incident Response Plan (IRP) with severity matrix and roles",
        "Communication tree and on-call rota",
    ],
    "A.5.25": [
        "Triage SOP and severity decision tree",
        "Sample event records showing severity classification",
    ],
    "A.5.26": [
        "Sample incident post-mortems (last 12 months) with timeline and actions",
        "After-action review meeting minutes",
    ],
    "A.5.27": [
        "Lessons-learned register with action owners and status",
        "Detection-rule / process changes traceable to past incidents",
    ],
    "A.5.28": [
        "Forensic evidence-handling SOP (chain of custody, hashing)",
        "Sample evidence custody form",
    ],
    "A.5.29": [
        "Business continuity plan covering security responsibilities during disruption",
        "BCP test report",
    ],
    "A.5.30": [
        "ICT continuity strategy (RTO/RPO per system)",
        "DR test report with restore evidence",
    ],
    "A.5.31": [
        "Register of applicable laws / regulations / contracts (GDPR, HIPAA, NIS2, SOC 2, customer contracts)",
        "Mapping of each requirement to controls or policies",
    ],
    "A.5.32": [
        "IP policy (open-source usage, code-licence scanning)",
        "OSS scanner output (e.g. FOSSA, Black Duck) for production builds",
    ],
    "A.5.33": [
        "Record-retention schedule",
        "Backup configuration and tested-restore evidence for records-of-record",
    ],
    "A.5.34": [
        "Privacy notice / DPIA template",
        "Records of Processing Activities (RoPA, Article 30 GDPR)",
    ],
    "A.5.35": [
        "Last independent security audit / pentest report and remediation plan",
        "Internal-audit programme schedule covering security",
    ],
    "A.5.36": [
        "Compliance monitoring dashboard (control owners, last-checked dates)",
        "Exception register with approved expiry dates",
    ],
    "A.5.37": [
        "Operational runbooks for critical security functions (patching, backup, IR)",
        "Runbook version control / approval evidence",
    ],

    # A.6 People controls -----------------------------------------------------
    "A.6.1": [
        "Background-check procedure",
        "Sample completed BG check (redacted) for a recent hire",
    ],
    "A.6.2": [
        "Employment contract template with confidentiality + security duties clauses",
        "Sample signed contract (redacted)",
    ],
    "A.6.3": [
        "Annual security-awareness training completion report",
        "Sample phishing simulation results",
        "Role-specific training records (devs, admins, finance)",
    ],
    "A.6.4": [
        "Disciplinary procedure for policy violations",
        "Anonymised log of past disciplinary actions tied to security",
    ],
    "A.6.5": [
        "Offboarding SOP detailing post-termination security duties",
        "NDA template surviving employment",
    ],
    "A.6.6": [
        "NDA / confidentiality template for staff and contractors",
        "Tracking system showing NDA-on-file per employee",
    ],
    "A.6.7": [
        "Remote-work policy (device security, network, family environment)",
        "MDM / VPN configuration for remote endpoints",
    ],
    "A.6.8": [
        "Internal reporting channel (ticket queue, email, hotline) advertised to staff",
        "Sample submitted event reports and triage outcomes",
    ],

    # A.7 Physical controls --------------------------------------------------
    "A.7.1": [
        "Site plan showing physical security perimeters",
        "Fence/wall/door specifications for high-security zones",
    ],
    "A.7.2": [
        "Access-card / biometric system configuration",
        "Visitor log sample (anonymised)",
    ],
    "A.7.3": [
        "Locked-zone listing (server rooms, comms rooms) and access list",
        "CCTV coverage diagram",
    ],
    "A.7.4": [
        "CCTV retention policy and sample footage retrieval log",
        "Intrusion-detection system status report",
    ],
    "A.7.5": [
        "Environmental risk assessment (fire, flood, earthquake)",
        "Fire-suppression certification, last test report",
    ],
    "A.7.6": [
        "Secure-area work procedure (escorts, photo restriction, sign-in)",
        "Sample work permits / sign-in logs",
    ],
    "A.7.7": [
        "Clear-desk/clear-screen policy",
        "Walk-around audit report (sampling)",
    ],
    "A.7.8": [
        "Server-room layout with rack siting, UPS, HVAC placement",
        "Last inspection / commissioning report",
    ],
    "A.7.9": [
        "Off-premises asset register (laptops, mobile, leased gear)",
        "Insurance certificate covering off-site assets",
    ],
    "A.7.10": [
        "Removable-media policy + DLP/EDR controls blocking USB write",
        "Media inventory and disposal records",
    ],
    "A.7.11": [
        "UPS specifications, last test report",
        "Power/cooling redundancy diagram",
    ],
    "A.7.12": [
        "Cable management standard (segregation of power/data, labelling)",
        "Walk-through photos of cable rooms",
    ],
    "A.7.13": [
        "Hardware maintenance contracts and SLA",
        "Maintenance work order samples",
    ],
    "A.7.14": [
        "Secure disposal SOP (data sanitisation, certificate-of-destruction)",
        "Last disposal vendor certificates",
    ],

    # A.8 Technological controls ---------------------------------------------
    "A.8.1": [
        "Endpoint protection policy (EDR, disk encryption, host firewall)",
        "MDM/EDR console screenshot showing fleet coverage",
        "Compliance report (% endpoints patched, encrypted, EDR-active)",
    ],
    "A.8.2": [
        "PAM tool configuration (CyberArk, BeyondTrust, AWS IAM admin roles)",
        "Privileged-session recording sample",
        "Just-in-time elevation workflow evidence",
    ],
    "A.8.3": [
        "Need-to-know matrix per data classification",
        "Access-review reports per quarter",
    ],
    "A.8.4": [
        "Source-control access policy (branch protection, code-owner files)",
        "Audit log showing repo access limited to project members",
    ],
    "A.8.5": [
        "MFA enforcement report (IdP screenshot showing 100% MFA coverage)",
        "Authentication policy (passwordless, FIDO2, SSO scope)",
    ],
    "A.8.6": [
        "Capacity monitoring dashboard (CPU, memory, storage, network)",
        "Capacity forecast report",
    ],
    "A.8.7": [
        "EDR / AV deployment report (% coverage, signature freshness)",
        "Sample EDR alert + response evidence",
    ],
    "A.8.8": [
        "Vulnerability scanner config (Nessus, Qualys, Wiz, Snyk)",
        "Last full-fleet scan report with severities",
        "Patch-management SLA and compliance metrics",
    ],
    "A.8.9": [
        "Hardening standards (CIS Benchmarks, vendor STIGs) by OS / platform",
        "Configuration baseline scanner output (e.g. CIS-CAT, AWS Config rules)",
    ],
    "A.8.10": [
        "Data-deletion SOP per data type",
        "Sample deletion certificates / audit trail",
    ],
    "A.8.11": [
        "Data-masking policy and tooling (Liquibase, Delphix, in-DB masking)",
        "Sample masked dataset used in lower environments",
    ],
    "A.8.12": [
        "DLP policy + console configuration (Microsoft Purview, Forcepoint, Netskope)",
        "DLP incident report sample",
    ],
    "A.8.13": [
        "Backup policy (frequency, retention, encryption, offsite)",
        "Latest backup verification / restore test evidence",
    ],
    "A.8.14": [
        "High-availability architecture diagrams",
        "Failover test evidence (chaos drill, region-failover)",
    ],
    "A.8.15": [
        "Logging standard (which sources, which retention, format)",
        "SIEM / log-platform dashboard showing live ingestion",
    ],
    "A.8.16": [
        "Detection-engineering catalogue (sigma/KQL rules with owners)",
        "Mean-Time-to-Detect metric over last 90 days",
    ],
    "A.8.17": [
        "NTP / PTP configuration on critical hosts",
        "Drift-monitoring alert configuration",
    ],
    "A.8.18": [
        "List of privileged utilities (e.g. sudo, registry editor) and access controls",
        "Audit logs of utility usage",
    ],
    "A.8.19": [
        "Software-installation policy (allow-listed apps, package signing)",
        "Endpoint allow-list configuration (AppLocker, WDAC, jamf)",
    ],
    "A.8.20": [
        "Network security architecture diagrams",
        "Firewall ruleset export with last review date",
    ],
    "A.8.21": [
        "SLAs with network-service providers",
        "Monitoring of provider service availability",
    ],
    "A.8.22": [
        "Network segmentation diagram (zones, micro-segmentation, VLANs)",
        "Firewall rule audit showing inter-zone restrictions",
    ],
    "A.8.23": [
        "Web-filter / Secure-Web-Gateway configuration (category blocks, SSL inspection)",
        "Filter bypass / exception register",
    ],
    "A.8.24": [
        "Cryptography policy (approved algorithms, key lengths, deprecations)",
        "KMS / HSM configuration evidence",
        "Certificate inventory and rotation schedule",
    ],
    "A.8.25": [
        "Secure SDLC policy and gate definitions (threat-model, SAST, DAST, pentest)",
        "SDLC gate evidence from a recent release",
    ],
    "A.8.26": [
        "Application security requirements doc per app",
        "Threat-model artefact (e.g. STRIDE) for a critical app",
    ],
    "A.8.27": [
        "Architecture review board records",
        "Reference architecture / engineering principles doc",
    ],
    "A.8.28": [
        "Secure coding standard (per language)",
        "SAST scan report from CI for a recent build",
    ],
    "A.8.29": [
        "Test plan including security tests (auth, authz, injection, secrets)",
        "Acceptance criteria sign-off including security",
    ],
    "A.8.30": [
        "Outsourcing security requirements (clauses, on-prem audit rights)",
        "Vendor SDLC questionnaire response",
    ],
    "A.8.31": [
        "Environment-separation architecture (network, IAM, data)",
        "Promotion process / change-control records",
    ],
    "A.8.32": [
        "Change-management policy + tool screenshots (ServiceNow / Jira CR)",
        "Sample emergency-change ticket with retroactive approval",
    ],
    "A.8.33": [
        "Test-data policy (no production data; or anonymised pull procedure)",
        "Sample anonymisation/synth-data pipeline output",
    ],
    "A.8.34": [
        "Audit testing scope-and-rules-of-engagement doc",
        "Backup taken before destructive audit testing",
    ],
}


# ---------------------------------------------------------------------------
# NIST CSF 2.0 — informative-reference style hints
# ---------------------------------------------------------------------------

NIST_CSF_2_0_EVIDENCE: dict[str, list[str]] = {
    # GV.OC ----
    "GV.OC-01": [
        "Mission/vision statement explicitly tying business objectives to cybersecurity outcomes",
        "Business-strategy doc with cybersecurity considerations called out",
    ],
    "GV.OC-02": [
        "Stakeholder map (customers, regulators, partners, employees) with security expectations",
        "Customer-facing security statements (trust center page, SOC 2 letter)",
    ],
    "GV.OC-03": [
        "Register of applicable laws/regulations/contracts and their owners",
        "Compliance attestation evidence (SOC 2 report, ISO certificate, …)",
    ],
    "GV.OC-04": [
        "Mission-essential capabilities list with dependency map",
        "BIA (business impact analysis) covering critical services",
    ],
    "GV.OC-05": [
        "Third-party dependency inventory (cloud, SaaS, payroll, identity)",
        "Critical-supplier criticality tiering",
    ],
    # GV.RM ----
    "GV.RM-01": [
        "Risk management objectives doc approved by leadership",
        "Risk committee charter",
    ],
    "GV.RM-02": [
        "Risk appetite statement signed by board / exec",
        "Quantitative tolerances (e.g. max $X loss, max Y hours downtime)",
    ],
    "GV.RM-03": [
        "ERM framework showing cyber-risk integration",
        "Joint cyber + ERM risk register sample",
    ],
    "GV.RM-04": [
        "Risk response taxonomy (accept/transfer/mitigate/avoid) policy",
        "Sample risk-treatment plans",
    ],
    "GV.RM-05": [
        "Risk reporting cadence to leadership / board (minutes, slides)",
        "Defined escalation thresholds",
    ],
    "GV.RM-06": [
        "Risk scoring methodology (e.g. FAIR, NIST 800-30) doc",
        "Risk register showing consistent scoring across entries",
    ],
    "GV.RM-07": [
        "Risk-vs-opportunity analysis sample (new product / market)",
    ],
    # GV.RR ----
    "GV.RR-01": [
        "Board-level cybersecurity accountability statement",
        "Exec performance objectives mentioning cyber outcomes",
    ],
    "GV.RR-02": [
        "RACI for security responsibilities",
        "Job descriptions for security roles",
    ],
    "GV.RR-03": [
        "Approved security budget for current year",
        "Headcount plan for security function",
    ],
    "GV.RR-04": [
        "HR policies referencing security (BG checks, training, disciplinary, offboarding)",
        "HR-security joint process docs",
    ],
    # GV.PO ----
    "GV.PO-01": [
        "Approved enterprise cybersecurity policy with sign-off",
        "Policy distribution / acknowledgement records",
    ],
    "GV.PO-02": [
        "Policy review log (annual at minimum)",
        "Diff between policy versions tied to threat / regulatory changes",
    ],
    # GV.OV ----
    "GV.OV-01": [
        "Cyber KPI/KRI report (e.g. patch SLA, MTTD/MTTR, training rates)",
        "Management Review minutes addressing outcomes",
    ],
    "GV.OV-02": [
        "Strategy review report covering coverage gaps vs threat landscape",
    ],
    "GV.OV-03": [
        "Performance review of risk management activities (audit findings, KPI trends)",
        "Improvement actions tracked to closure",
    ],
    # GV.SC ----
    "GV.SC-01": [
        "Cyber supply-chain risk management programme document",
        "C-SCRM responsibility / RACI",
    ],
    "GV.SC-02": [
        "Supplier security contractual roles defined",
        "Joint security-responsibility matrix",
    ],
    "GV.SC-03": [
        "Joint cyber + ERM risk register including supplier risks",
        "ERM committee minutes covering supplier risk",
    ],
    "GV.SC-04": [
        "Supplier inventory ranked by criticality",
        "Criteria used to determine criticality",
    ],
    "GV.SC-05": [
        "Standard security clauses for supplier contracts",
        "Vendor security questionnaire template",
    ],
    "GV.SC-06": [
        "Vendor onboarding due-diligence checklist (security review, SOC2/ISO certificate review)",
        "Sample completed vendor security review",
    ],
    "GV.SC-07": [
        "Continuous vendor monitoring (SecurityScorecard / BitSight / similar) report",
        "Quarterly supplier risk review minutes",
    ],
    "GV.SC-08": [
        "Vendor IR plan (joint incident contact, escalation)",
        "Tabletop exercise involving a major supplier",
    ],
    "GV.SC-09": [
        "Vendor performance scorecard including security metrics",
        "Trend report over multiple quarters",
    ],
    "GV.SC-10": [
        "Exit / termination procedure for supplier engagements",
        "Last data-return / data-destruction certificate from a terminated vendor",
    ],

    # ID.AM ----
    "ID.AM-01": [
        "Hardware CMDB export with owner, location, serial",
        "Reconciliation between MDM / network scan / CMDB",
    ],
    "ID.AM-02": [
        "Software inventory (per-host SBOM or asset agent)",
        "Service catalogue with owners",
    ],
    "ID.AM-03": [
        "Network data-flow diagrams (internal + external)",
        "Approved data-flow register",
    ],
    "ID.AM-04": [
        "Supplier inventory cross-referenced to ID.AM-01/02",
        "Subprocessor list (relevant for SaaS)",
    ],
    "ID.AM-05": [
        "Asset criticality matrix mapping assets → business impact",
        "Asset prioritisation review log",
    ],
    "ID.AM-07": [
        "Data inventory / data map (by data type, location, owner, retention)",
        "Privacy register (RoPA)",
    ],
    "ID.AM-08": [
        "Asset lifecycle SOP (acquire → operate → decommission)",
        "Decommissioning records",
    ],
    # ID.RA ----
    "ID.RA-01": [
        "Latest vulnerability scan report",
        "Patch / mitigation tracking ticket queue",
    ],
    "ID.RA-02": [
        "Threat-intel platform feed subscriptions",
        "Periodic intel briefings",
    ],
    "ID.RA-03": [
        "Threat-modelling artefacts for critical systems",
        "Threat register with internal + external categories",
    ],
    "ID.RA-04": [
        "Risk assessment showing likelihood × impact per scenario",
        "Methodology doc (e.g. FAIR, NIST 800-30)",
    ],
    "ID.RA-05": [
        "Inherent-vs-residual risk register",
        "Risk-response prioritisation rationale",
    ],
    "ID.RA-06": [
        "Risk treatment plans with owners and target dates",
        "Status report on open treatments",
    ],
    "ID.RA-07": [
        "Change-management tickets including risk impact field",
        "Exception register with expiry and compensating controls",
    ],
    "ID.RA-08": [
        "Vulnerability disclosure policy (security.txt, bug-bounty page)",
        "Sample handled vulnerability submission",
    ],
    "ID.RA-09": [
        "Hardware/software acquisition checklist (authenticity verification)",
        "Code-signing / hash-verification SOP for downloads",
    ],
    "ID.RA-10": [
        "Vendor security questionnaire results (pre-contract)",
        "Independent attestations (SOC 2, ISO 27001 certificate) collected",
    ],
    # ID.IM ----
    "ID.IM-01": [
        "Improvement log following internal/external assessments",
        "Audit-findings remediation tracker",
    ],
    "ID.IM-02": [
        "Tabletop / red-team / DR exercise reports",
        "Action items closed-loop tracking",
    ],
    "ID.IM-03": [
        "Operations retro / postmortem records (security and non-security)",
        "Process change history tied to retros",
    ],
    "ID.IM-04": [
        "Incident response plan and recovery / continuity plans (versioned)",
        "Plan review evidence (annual + post-incident)",
    ],

    # PR.AA ----
    "PR.AA-01": [
        "IAM lifecycle SOP (joiner/mover/leaver)",
        "Identity store inventory (AD, Okta, Azure AD, AWS IAM, …)",
    ],
    "PR.AA-02": [
        "Identity proofing procedure (e.g. IAL2 for high-risk roles)",
        "Sample onboarding identity-verification artefacts",
    ],
    "PR.AA-03": [
        "MFA enforcement report (100% for admin, % for user)",
        "Service-account authentication evidence (workload identity / mTLS)",
    ],
    "PR.AA-04": [
        "SAML/OIDC signing certificate inventory + rotation log",
        "Token-lifetime / refresh-policy configuration",
    ],
    "PR.AA-05": [
        "Role-to-permission matrix per system",
        "Access-recertification report",
    ],
    "PR.AA-06": [
        "Physical access control system (badge / biometric) configuration",
        "Visitor log + escort SOP",
    ],
    # PR.AT ----
    "PR.AT-01": [
        "Annual awareness training completion rate report",
        "Phishing simulation campaign results",
    ],
    "PR.AT-02": [
        "Role-based training for devs, admins, finance (e.g. secure coding, AWS security)",
        "Training attendance / certification records",
    ],
    # PR.DS ----
    "PR.DS-01": [
        "Encryption-at-rest evidence (disk, database, S3 SSE-KMS) — config screenshots",
        "Key-management system audit log sample",
    ],
    "PR.DS-02": [
        "TLS enforcement evidence (config, scanner output e.g. SSL Labs A+)",
        "Internal-traffic encryption (service-mesh mTLS) config",
    ],
    "PR.DS-10": [
        "Enclave / confidential-compute usage evidence (e.g. SGX, Nitro Enclaves)",
        "Memory-protection / tokenisation evidence for sensitive processing",
    ],
    "PR.DS-11": [
        "Backup policy + last successful restore test report",
        "Backup encryption configuration",
    ],
    # PR.PS ----
    "PR.PS-01": [
        "Configuration baselines (CIS, vendor-STIG) by platform",
        "Compliance scanner output (e.g. CIS-CAT, AWS Config)",
    ],
    "PR.PS-02": [
        "Patch-management SLA + compliance dashboard",
        "EOL software register and replacement plan",
    ],
    "PR.PS-03": [
        "Hardware refresh schedule",
        "Decommissioning records with secure-disposal certs",
    ],
    "PR.PS-04": [
        "Logging standard + SIEM source coverage",
        "SIEM ingestion dashboard / retention configuration",
    ],
    "PR.PS-05": [
        "Application allow-list config (AppLocker / WDAC / jamf)",
        "Detection rule for unauthorised binary execution",
    ],
    "PR.PS-06": [
        "Secure SDLC policy + CI security-gate evidence",
        "SAST / SCA / IaC-scan reports for recent build",
    ],
    # PR.IR ----
    "PR.IR-01": [
        "Network segmentation diagram + firewall ruleset",
        "Zero-trust / micro-segmentation configuration evidence",
    ],
    "PR.IR-02": [
        "Environmental controls (UPS, HVAC, fire-suppression) inspection reports",
        "Site risk assessment",
    ],
    "PR.IR-03": [
        "High-availability architecture diagrams (multi-AZ, DR site)",
        "Recent failover / chaos exercise report",
    ],
    "PR.IR-04": [
        "Capacity planning report",
        "Auto-scaling policies (cloud) screenshots",
    ],

    # DE.CM ----
    "DE.CM-01": [
        "Network IDS / NDR configuration",
        "Sample detection alerts and response logs",
    ],
    "DE.CM-02": [
        "Physical security monitoring (CCTV, intrusion, badge anomaly) configs",
        "Sample physical alert investigations",
    ],
    "DE.CM-03": [
        "UEBA / user-monitoring configuration",
        "Privileged-session recording sample",
    ],
    "DE.CM-06": [
        "Third-party / SaaS log ingestion into SIEM (e.g. Okta, GitHub, Salesforce)",
        "Vendor activity alerts",
    ],
    "DE.CM-09": [
        "EDR / cloud workload protection (CWPP) coverage report",
        "Sample alert + investigation",
    ],
    # DE.AE ----
    "DE.AE-02": [
        "Analyst playbooks per alert type",
        "Sample triaged alerts with notes",
    ],
    "DE.AE-03": [
        "SIEM correlation rules / aggregation views",
        "Sample multi-source correlated incident",
    ],
    "DE.AE-04": [
        "Incident scoring rubric (e.g. severity matrix)",
        "Sample scored incidents and rationale",
    ],
    "DE.AE-06": [
        "SOC distribution lists / paging integrations",
        "Sample case notifications to stakeholders",
    ],
    "DE.AE-07": [
        "Threat-intel enrichment in SIEM/SOAR",
        "Sample enriched alert with TI context",
    ],
    "DE.AE-08": [
        "Incident declaration criteria doc",
        "Sample declared incident with timestamp + decision rationale",
    ],

    # RS.MA ----
    "RS.MA-01": [
        "Incident response plan",
        "Sample exec record of plan execution during a real incident",
    ],
    "RS.MA-02": [
        "Triage SOP + queue evidence",
        "Sample false-positive vs true-positive reclassification",
    ],
    "RS.MA-03": [
        "Incident categorisation taxonomy (e.g. malware, account compromise, data leak)",
        "Sample categorised cases",
    ],
    "RS.MA-04": [
        "Escalation matrix with named contacts and SLAs",
        "Sample escalated case",
    ],
    "RS.MA-05": [
        "Recovery-initiation criteria doc",
        "Sample case showing recovery decision recorded",
    ],
    # RS.AN ----
    "RS.AN-03": [
        "Forensic timeline doc from a recent incident",
        "Root-cause analysis (5-whys / fishbone)",
    ],
    "RS.AN-06": [
        "Chain-of-custody form sample",
        "Forensic workstation imaging SOP",
    ],
    "RS.AN-07": [
        "Evidence-collection SOP (logs, memory, disk)",
        "Hash-verification log",
    ],
    "RS.AN-08": [
        "Impact-assessment template",
        "Sample completed assessment with affected-data counts",
    ],
    # RS.CO ----
    "RS.CO-02": [
        "Notification matrix (regulators, customers, partners) with timeframes",
        "Sample notification record",
    ],
    "RS.CO-03": [
        "Information-sharing SOP (with ISAC, CERT)",
        "Sample shared indicator / report",
    ],
    # RS.MI ----
    "RS.MI-01": [
        "Containment playbooks per incident type",
        "Sample case showing containment actions and timestamps",
    ],
    "RS.MI-02": [
        "Eradication SOP (remediation, rebuild, credential reset)",
        "Sample eradication confirmation log",
    ],

    # RC.RP ----
    "RC.RP-01": [
        "Recovery plan integrated into IRP",
        "Sample case showing recovery phase initiation",
    ],
    "RC.RP-02": [
        "Recovery prioritisation matrix",
        "Sample recovery action list with owners",
    ],
    "RC.RP-03": [
        "Backup integrity verification log",
        "Restore test reports",
    ],
    "RC.RP-04": [
        "Post-incident operating norms doc",
        "Sample updated runbook after an incident",
    ],
    "RC.RP-05": [
        "Restoration verification checklist + sign-off",
        "Service-restoration evidence (monitoring graphs)",
    ],
    "RC.RP-06": [
        "Incident closure criteria doc",
        "Sample incident closure record + final report",
    ],
    # RC.CO ----
    "RC.CO-03": [
        "Recovery-status communication templates",
        "Sample stakeholder updates during recovery",
    ],
    "RC.CO-04": [
        "Public-statement template + legal/PR approval workflow",
        "Sample statement from a past incident",
    ],
}


# ---------------------------------------------------------------------------
# Public lookup
# ---------------------------------------------------------------------------

BUILT_IN_EVIDENCE_HINTS: dict[str, dict[str, list[str]]] = {
    "urn:cyberguard:framework:iso-27001-2022": ISO_27001_2022_EVIDENCE,
    "urn:cyberguard:framework:nist-csf-2.0": NIST_CSF_2_0_EVIDENCE,
}
