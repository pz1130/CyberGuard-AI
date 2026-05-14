"""Built-in framework seeds.

Each framework is a plain dict so it can also be exported / re-imported
via the /governance/frameworks/import endpoint.

Sources (titles only — not the full normative text):
  - ISO/IEC 27001:2022, Annex A (93 controls in 4 themes)
  - NIST Cybersecurity Framework 2.0 (NIST CSWP 29)
"""
from typing import TypedDict


class SeedRequirement(TypedDict, total=False):
    ref_id: str
    name: str
    description: str
    parent_ref_id: str | None
    is_assessable: bool


class SeedFramework(TypedDict):
    urn: str
    name: str
    version: str
    description: str
    ref_url: str
    requirements: list[SeedRequirement]


# ---------------------------------------------------------------------------
# ISO/IEC 27001:2022 Annex A — 4 themes + 93 controls
# ---------------------------------------------------------------------------

ISO_27001_2022: SeedFramework = {
    "urn": "urn:cyberguard:framework:iso-27001-2022",
    "name": "ISO/IEC 27001:2022 Annex A",
    "version": "2022",
    "description": "Information security controls (Annex A), 93 controls organized into 4 themes.",
    "ref_url": "https://www.iso.org/standard/27001",
    "requirements": [
        # A.5 Organizational controls (37 controls)
        {"ref_id": "A.5", "name": "Organizational controls", "is_assessable": False},
        {"ref_id": "A.5.1", "name": "Policies for information security", "parent_ref_id": "A.5"},
        {"ref_id": "A.5.2", "name": "Information security roles and responsibilities", "parent_ref_id": "A.5"},
        {"ref_id": "A.5.3", "name": "Segregation of duties", "parent_ref_id": "A.5"},
        {"ref_id": "A.5.4", "name": "Management responsibilities", "parent_ref_id": "A.5"},
        {"ref_id": "A.5.5", "name": "Contact with authorities", "parent_ref_id": "A.5"},
        {"ref_id": "A.5.6", "name": "Contact with special interest groups", "parent_ref_id": "A.5"},
        {"ref_id": "A.5.7", "name": "Threat intelligence", "parent_ref_id": "A.5"},
        {"ref_id": "A.5.8", "name": "Information security in project management", "parent_ref_id": "A.5"},
        {"ref_id": "A.5.9", "name": "Inventory of information and other associated assets", "parent_ref_id": "A.5"},
        {"ref_id": "A.5.10", "name": "Acceptable use of information and other associated assets", "parent_ref_id": "A.5"},
        {"ref_id": "A.5.11", "name": "Return of assets", "parent_ref_id": "A.5"},
        {"ref_id": "A.5.12", "name": "Classification of information", "parent_ref_id": "A.5"},
        {"ref_id": "A.5.13", "name": "Labelling of information", "parent_ref_id": "A.5"},
        {"ref_id": "A.5.14", "name": "Information transfer", "parent_ref_id": "A.5"},
        {"ref_id": "A.5.15", "name": "Access control", "parent_ref_id": "A.5"},
        {"ref_id": "A.5.16", "name": "Identity management", "parent_ref_id": "A.5"},
        {"ref_id": "A.5.17", "name": "Authentication information", "parent_ref_id": "A.5"},
        {"ref_id": "A.5.18", "name": "Access rights", "parent_ref_id": "A.5"},
        {"ref_id": "A.5.19", "name": "Information security in supplier relationships", "parent_ref_id": "A.5"},
        {"ref_id": "A.5.20", "name": "Addressing information security within supplier agreements", "parent_ref_id": "A.5"},
        {"ref_id": "A.5.21", "name": "Managing information security in the ICT supply chain", "parent_ref_id": "A.5"},
        {"ref_id": "A.5.22", "name": "Monitoring, review and change management of supplier services", "parent_ref_id": "A.5"},
        {"ref_id": "A.5.23", "name": "Information security for use of cloud services", "parent_ref_id": "A.5"},
        {"ref_id": "A.5.24", "name": "Information security incident management planning and preparation", "parent_ref_id": "A.5"},
        {"ref_id": "A.5.25", "name": "Assessment and decision on information security events", "parent_ref_id": "A.5"},
        {"ref_id": "A.5.26", "name": "Response to information security incidents", "parent_ref_id": "A.5"},
        {"ref_id": "A.5.27", "name": "Learning from information security incidents", "parent_ref_id": "A.5"},
        {"ref_id": "A.5.28", "name": "Collection of evidence", "parent_ref_id": "A.5"},
        {"ref_id": "A.5.29", "name": "Information security during disruption", "parent_ref_id": "A.5"},
        {"ref_id": "A.5.30", "name": "ICT readiness for business continuity", "parent_ref_id": "A.5"},
        {"ref_id": "A.5.31", "name": "Legal, statutory, regulatory and contractual requirements", "parent_ref_id": "A.5"},
        {"ref_id": "A.5.32", "name": "Intellectual property rights", "parent_ref_id": "A.5"},
        {"ref_id": "A.5.33", "name": "Protection of records", "parent_ref_id": "A.5"},
        {"ref_id": "A.5.34", "name": "Privacy and protection of PII", "parent_ref_id": "A.5"},
        {"ref_id": "A.5.35", "name": "Independent review of information security", "parent_ref_id": "A.5"},
        {"ref_id": "A.5.36", "name": "Compliance with policies, rules and standards for information security", "parent_ref_id": "A.5"},
        {"ref_id": "A.5.37", "name": "Documented operating procedures", "parent_ref_id": "A.5"},

        # A.6 People controls (8 controls)
        {"ref_id": "A.6", "name": "People controls", "is_assessable": False},
        {"ref_id": "A.6.1", "name": "Screening", "parent_ref_id": "A.6"},
        {"ref_id": "A.6.2", "name": "Terms and conditions of employment", "parent_ref_id": "A.6"},
        {"ref_id": "A.6.3", "name": "Information security awareness, education and training", "parent_ref_id": "A.6"},
        {"ref_id": "A.6.4", "name": "Disciplinary process", "parent_ref_id": "A.6"},
        {"ref_id": "A.6.5", "name": "Responsibilities after termination or change of employment", "parent_ref_id": "A.6"},
        {"ref_id": "A.6.6", "name": "Confidentiality or non-disclosure agreements", "parent_ref_id": "A.6"},
        {"ref_id": "A.6.7", "name": "Remote working", "parent_ref_id": "A.6"},
        {"ref_id": "A.6.8", "name": "Information security event reporting", "parent_ref_id": "A.6"},

        # A.7 Physical controls (14 controls)
        {"ref_id": "A.7", "name": "Physical controls", "is_assessable": False},
        {"ref_id": "A.7.1", "name": "Physical security perimeters", "parent_ref_id": "A.7"},
        {"ref_id": "A.7.2", "name": "Physical entry", "parent_ref_id": "A.7"},
        {"ref_id": "A.7.3", "name": "Securing offices, rooms and facilities", "parent_ref_id": "A.7"},
        {"ref_id": "A.7.4", "name": "Physical security monitoring", "parent_ref_id": "A.7"},
        {"ref_id": "A.7.5", "name": "Protecting against physical and environmental threats", "parent_ref_id": "A.7"},
        {"ref_id": "A.7.6", "name": "Working in secure areas", "parent_ref_id": "A.7"},
        {"ref_id": "A.7.7", "name": "Clear desk and clear screen", "parent_ref_id": "A.7"},
        {"ref_id": "A.7.8", "name": "Equipment siting and protection", "parent_ref_id": "A.7"},
        {"ref_id": "A.7.9", "name": "Security of assets off-premises", "parent_ref_id": "A.7"},
        {"ref_id": "A.7.10", "name": "Storage media", "parent_ref_id": "A.7"},
        {"ref_id": "A.7.11", "name": "Supporting utilities", "parent_ref_id": "A.7"},
        {"ref_id": "A.7.12", "name": "Cabling security", "parent_ref_id": "A.7"},
        {"ref_id": "A.7.13", "name": "Equipment maintenance", "parent_ref_id": "A.7"},
        {"ref_id": "A.7.14", "name": "Secure disposal or re-use of equipment", "parent_ref_id": "A.7"},

        # A.8 Technological controls (34 controls)
        {"ref_id": "A.8", "name": "Technological controls", "is_assessable": False},
        {"ref_id": "A.8.1", "name": "User endpoint devices", "parent_ref_id": "A.8"},
        {"ref_id": "A.8.2", "name": "Privileged access rights", "parent_ref_id": "A.8"},
        {"ref_id": "A.8.3", "name": "Information access restriction", "parent_ref_id": "A.8"},
        {"ref_id": "A.8.4", "name": "Access to source code", "parent_ref_id": "A.8"},
        {"ref_id": "A.8.5", "name": "Secure authentication", "parent_ref_id": "A.8"},
        {"ref_id": "A.8.6", "name": "Capacity management", "parent_ref_id": "A.8"},
        {"ref_id": "A.8.7", "name": "Protection against malware", "parent_ref_id": "A.8"},
        {"ref_id": "A.8.8", "name": "Management of technical vulnerabilities", "parent_ref_id": "A.8"},
        {"ref_id": "A.8.9", "name": "Configuration management", "parent_ref_id": "A.8"},
        {"ref_id": "A.8.10", "name": "Information deletion", "parent_ref_id": "A.8"},
        {"ref_id": "A.8.11", "name": "Data masking", "parent_ref_id": "A.8"},
        {"ref_id": "A.8.12", "name": "Data leakage prevention", "parent_ref_id": "A.8"},
        {"ref_id": "A.8.13", "name": "Information backup", "parent_ref_id": "A.8"},
        {"ref_id": "A.8.14", "name": "Redundancy of information processing facilities", "parent_ref_id": "A.8"},
        {"ref_id": "A.8.15", "name": "Logging", "parent_ref_id": "A.8"},
        {"ref_id": "A.8.16", "name": "Monitoring activities", "parent_ref_id": "A.8"},
        {"ref_id": "A.8.17", "name": "Clock synchronization", "parent_ref_id": "A.8"},
        {"ref_id": "A.8.18", "name": "Use of privileged utility programs", "parent_ref_id": "A.8"},
        {"ref_id": "A.8.19", "name": "Installation of software on operational systems", "parent_ref_id": "A.8"},
        {"ref_id": "A.8.20", "name": "Networks security", "parent_ref_id": "A.8"},
        {"ref_id": "A.8.21", "name": "Security of network services", "parent_ref_id": "A.8"},
        {"ref_id": "A.8.22", "name": "Segregation of networks", "parent_ref_id": "A.8"},
        {"ref_id": "A.8.23", "name": "Web filtering", "parent_ref_id": "A.8"},
        {"ref_id": "A.8.24", "name": "Use of cryptography", "parent_ref_id": "A.8"},
        {"ref_id": "A.8.25", "name": "Secure development life cycle", "parent_ref_id": "A.8"},
        {"ref_id": "A.8.26", "name": "Application security requirements", "parent_ref_id": "A.8"},
        {"ref_id": "A.8.27", "name": "Secure system architecture and engineering principles", "parent_ref_id": "A.8"},
        {"ref_id": "A.8.28", "name": "Secure coding", "parent_ref_id": "A.8"},
        {"ref_id": "A.8.29", "name": "Security testing in development and acceptance", "parent_ref_id": "A.8"},
        {"ref_id": "A.8.30", "name": "Outsourced development", "parent_ref_id": "A.8"},
        {"ref_id": "A.8.31", "name": "Separation of development, test and production environments", "parent_ref_id": "A.8"},
        {"ref_id": "A.8.32", "name": "Change management", "parent_ref_id": "A.8"},
        {"ref_id": "A.8.33", "name": "Test information", "parent_ref_id": "A.8"},
        {"ref_id": "A.8.34", "name": "Protection of information systems during audit testing", "parent_ref_id": "A.8"},
    ],
}


# ---------------------------------------------------------------------------
# NIST CSF 2.0 — 6 functions, 22 categories, ~106 subcategories
# ---------------------------------------------------------------------------

NIST_CSF_2_0: SeedFramework = {
    "urn": "urn:cyberguard:framework:nist-csf-2.0",
    "name": "NIST Cybersecurity Framework 2.0",
    "version": "2.0",
    "description": "NIST CSF 2.0 — Govern, Identify, Protect, Detect, Respond, Recover.",
    "ref_url": "https://www.nist.gov/cyberframework",
    "requirements": [
        # GV – Govern
        {"ref_id": "GV", "name": "Govern", "is_assessable": False},
        {"ref_id": "GV.OC", "name": "Organizational Context", "parent_ref_id": "GV", "is_assessable": False},
        {"ref_id": "GV.OC-01", "name": "Organizational mission is understood and informs cybersecurity risk management", "parent_ref_id": "GV.OC"},
        {"ref_id": "GV.OC-02", "name": "Internal and external stakeholders are understood, and their needs and expectations are considered", "parent_ref_id": "GV.OC"},
        {"ref_id": "GV.OC-03", "name": "Legal, regulatory, and contractual requirements are understood and managed", "parent_ref_id": "GV.OC"},
        {"ref_id": "GV.OC-04", "name": "Critical objectives, capabilities, and services that stakeholders depend on or expect are understood", "parent_ref_id": "GV.OC"},
        {"ref_id": "GV.OC-05", "name": "Outcomes, capabilities, and services that the organization depends on are understood", "parent_ref_id": "GV.OC"},

        {"ref_id": "GV.RM", "name": "Risk Management Strategy", "parent_ref_id": "GV", "is_assessable": False},
        {"ref_id": "GV.RM-01", "name": "Risk management objectives are established and agreed to by stakeholders", "parent_ref_id": "GV.RM"},
        {"ref_id": "GV.RM-02", "name": "Risk appetite and risk tolerance statements are established", "parent_ref_id": "GV.RM"},
        {"ref_id": "GV.RM-03", "name": "Cybersecurity risk management activities and outcomes are included in ERM processes", "parent_ref_id": "GV.RM"},
        {"ref_id": "GV.RM-04", "name": "Strategic direction describes appropriate risk response options", "parent_ref_id": "GV.RM"},
        {"ref_id": "GV.RM-05", "name": "Lines of communication for cybersecurity risks are established", "parent_ref_id": "GV.RM"},
        {"ref_id": "GV.RM-06", "name": "A standardized method for calculating, documenting, categorizing, and prioritizing cybersecurity risks is established", "parent_ref_id": "GV.RM"},
        {"ref_id": "GV.RM-07", "name": "Strategic opportunities are characterized and included in cybersecurity risk discussions", "parent_ref_id": "GV.RM"},

        {"ref_id": "GV.RR", "name": "Roles, Responsibilities, and Authorities", "parent_ref_id": "GV", "is_assessable": False},
        {"ref_id": "GV.RR-01", "name": "Organizational leadership is responsible and accountable for cybersecurity risk", "parent_ref_id": "GV.RR"},
        {"ref_id": "GV.RR-02", "name": "Roles, responsibilities, and authorities for cybersecurity are established", "parent_ref_id": "GV.RR"},
        {"ref_id": "GV.RR-03", "name": "Adequate resources are allocated commensurate with cybersecurity risk strategy", "parent_ref_id": "GV.RR"},
        {"ref_id": "GV.RR-04", "name": "Cybersecurity is included in HR practices", "parent_ref_id": "GV.RR"},

        {"ref_id": "GV.PO", "name": "Policy", "parent_ref_id": "GV", "is_assessable": False},
        {"ref_id": "GV.PO-01", "name": "Policy for managing cybersecurity risks is established, communicated, and enforced", "parent_ref_id": "GV.PO"},
        {"ref_id": "GV.PO-02", "name": "Policy is reviewed, updated, and communicated to reflect changes in requirements, threats, technology, and mission", "parent_ref_id": "GV.PO"},

        {"ref_id": "GV.OV", "name": "Oversight", "parent_ref_id": "GV", "is_assessable": False},
        {"ref_id": "GV.OV-01", "name": "Cybersecurity risk management strategy outcomes are reviewed to inform adjustments", "parent_ref_id": "GV.OV"},
        {"ref_id": "GV.OV-02", "name": "The cybersecurity risk management strategy is reviewed to ensure it covers organizational requirements and risks", "parent_ref_id": "GV.OV"},
        {"ref_id": "GV.OV-03", "name": "Cybersecurity risk management performance is evaluated and reviewed for adjustments", "parent_ref_id": "GV.OV"},

        {"ref_id": "GV.SC", "name": "Cybersecurity Supply Chain Risk Management", "parent_ref_id": "GV", "is_assessable": False},
        {"ref_id": "GV.SC-01", "name": "A cybersecurity supply chain risk management program is established", "parent_ref_id": "GV.SC"},
        {"ref_id": "GV.SC-02", "name": "Cybersecurity roles and responsibilities for suppliers and partners are established", "parent_ref_id": "GV.SC"},
        {"ref_id": "GV.SC-03", "name": "Cybersecurity supply chain risk management is integrated into cybersecurity and ERM", "parent_ref_id": "GV.SC"},
        {"ref_id": "GV.SC-04", "name": "Suppliers are known and prioritized by criticality", "parent_ref_id": "GV.SC"},
        {"ref_id": "GV.SC-05", "name": "Requirements to address cybersecurity risks in supply chains are established, prioritized, and integrated into contracts and other agreements", "parent_ref_id": "GV.SC"},
        {"ref_id": "GV.SC-06", "name": "Planning and due diligence are performed to reduce risks before entering into formal supplier or third-party relationships", "parent_ref_id": "GV.SC"},
        {"ref_id": "GV.SC-07", "name": "Risks posed by suppliers, products, and services are understood and prioritized throughout the relationship", "parent_ref_id": "GV.SC"},
        {"ref_id": "GV.SC-08", "name": "Relevant suppliers and other third parties are included in incident planning, response, and recovery", "parent_ref_id": "GV.SC"},
        {"ref_id": "GV.SC-09", "name": "Supply chain security practices are integrated into cybersecurity and ERM, and their performance is monitored", "parent_ref_id": "GV.SC"},
        {"ref_id": "GV.SC-10", "name": "Cybersecurity supply chain risk management plans include provisions for activities after the conclusion of a partnership or service agreement", "parent_ref_id": "GV.SC"},

        # ID – Identify
        {"ref_id": "ID", "name": "Identify", "is_assessable": False},
        {"ref_id": "ID.AM", "name": "Asset Management", "parent_ref_id": "ID", "is_assessable": False},
        {"ref_id": "ID.AM-01", "name": "Inventories of hardware managed by the organization are maintained", "parent_ref_id": "ID.AM"},
        {"ref_id": "ID.AM-02", "name": "Inventories of software, services, and systems managed by the organization are maintained", "parent_ref_id": "ID.AM"},
        {"ref_id": "ID.AM-03", "name": "Representations of the organization's authorized network communication and internal/external network data flows are maintained", "parent_ref_id": "ID.AM"},
        {"ref_id": "ID.AM-04", "name": "Inventories of services provided by suppliers are maintained", "parent_ref_id": "ID.AM"},
        {"ref_id": "ID.AM-05", "name": "Assets are prioritized based on classification, criticality, resources, and impact on the mission", "parent_ref_id": "ID.AM"},
        {"ref_id": "ID.AM-07", "name": "Inventories of data and corresponding metadata for designated data types are maintained", "parent_ref_id": "ID.AM"},
        {"ref_id": "ID.AM-08", "name": "Systems, hardware, software, services, and data are managed throughout their life cycles", "parent_ref_id": "ID.AM"},

        {"ref_id": "ID.RA", "name": "Risk Assessment", "parent_ref_id": "ID", "is_assessable": False},
        {"ref_id": "ID.RA-01", "name": "Vulnerabilities in assets are identified, validated, and recorded", "parent_ref_id": "ID.RA"},
        {"ref_id": "ID.RA-02", "name": "Cyber threat intelligence is received from information sharing forums and sources", "parent_ref_id": "ID.RA"},
        {"ref_id": "ID.RA-03", "name": "Internal and external threats to the organization are identified and recorded", "parent_ref_id": "ID.RA"},
        {"ref_id": "ID.RA-04", "name": "Potential impacts and likelihoods of threats exploiting vulnerabilities are identified and recorded", "parent_ref_id": "ID.RA"},
        {"ref_id": "ID.RA-05", "name": "Threats, vulnerabilities, likelihoods, and impacts are used to understand inherent risk and inform risk response prioritization", "parent_ref_id": "ID.RA"},
        {"ref_id": "ID.RA-06", "name": "Risk responses are chosen, prioritized, planned, tracked, and communicated", "parent_ref_id": "ID.RA"},
        {"ref_id": "ID.RA-07", "name": "Changes and exceptions are managed, assessed for risk impact, recorded, and tracked", "parent_ref_id": "ID.RA"},
        {"ref_id": "ID.RA-08", "name": "Processes for receiving, analyzing, and responding to vulnerability disclosures are established", "parent_ref_id": "ID.RA"},
        {"ref_id": "ID.RA-09", "name": "The authenticity and integrity of hardware and software are assessed prior to acquisition and use", "parent_ref_id": "ID.RA"},
        {"ref_id": "ID.RA-10", "name": "Critical suppliers are assessed prior to acquisition", "parent_ref_id": "ID.RA"},

        {"ref_id": "ID.IM", "name": "Improvement", "parent_ref_id": "ID", "is_assessable": False},
        {"ref_id": "ID.IM-01", "name": "Improvements are identified from evaluations", "parent_ref_id": "ID.IM"},
        {"ref_id": "ID.IM-02", "name": "Improvements are identified from security tests and exercises, including those done in coordination with suppliers and relevant third parties", "parent_ref_id": "ID.IM"},
        {"ref_id": "ID.IM-03", "name": "Improvements are identified from execution of operational processes, procedures, and activities", "parent_ref_id": "ID.IM"},
        {"ref_id": "ID.IM-04", "name": "Incident response plans and other cybersecurity plans that affect operations are established, communicated, maintained, and improved", "parent_ref_id": "ID.IM"},

        # PR – Protect
        {"ref_id": "PR", "name": "Protect", "is_assessable": False},
        {"ref_id": "PR.AA", "name": "Identity Management, Authentication, and Access Control", "parent_ref_id": "PR", "is_assessable": False},
        {"ref_id": "PR.AA-01", "name": "Identities and credentials for authorized users, services, and hardware are managed by the organization", "parent_ref_id": "PR.AA"},
        {"ref_id": "PR.AA-02", "name": "Identities are proofed and bound to credentials based on the context of interactions", "parent_ref_id": "PR.AA"},
        {"ref_id": "PR.AA-03", "name": "Users, services, and hardware are authenticated", "parent_ref_id": "PR.AA"},
        {"ref_id": "PR.AA-04", "name": "Identity assertions are protected, conveyed, and verified", "parent_ref_id": "PR.AA"},
        {"ref_id": "PR.AA-05", "name": "Access permissions, entitlements, and authorizations are defined and managed", "parent_ref_id": "PR.AA"},
        {"ref_id": "PR.AA-06", "name": "Physical access to assets is managed, monitored, and enforced commensurate with risk", "parent_ref_id": "PR.AA"},

        {"ref_id": "PR.AT", "name": "Awareness and Training", "parent_ref_id": "PR", "is_assessable": False},
        {"ref_id": "PR.AT-01", "name": "Personnel are provided with awareness and training so they possess the knowledge and skills to perform general tasks with cybersecurity risks in mind", "parent_ref_id": "PR.AT"},
        {"ref_id": "PR.AT-02", "name": "Individuals in specialized roles are provided with awareness and training so they possess the knowledge and skills to perform relevant tasks with cybersecurity risks in mind", "parent_ref_id": "PR.AT"},

        {"ref_id": "PR.DS", "name": "Data Security", "parent_ref_id": "PR", "is_assessable": False},
        {"ref_id": "PR.DS-01", "name": "The confidentiality, integrity, and availability of data-at-rest are protected", "parent_ref_id": "PR.DS"},
        {"ref_id": "PR.DS-02", "name": "The confidentiality, integrity, and availability of data-in-transit are protected", "parent_ref_id": "PR.DS"},
        {"ref_id": "PR.DS-10", "name": "The confidentiality, integrity, and availability of data-in-use are protected", "parent_ref_id": "PR.DS"},
        {"ref_id": "PR.DS-11", "name": "Backups of data are created, protected, maintained, and tested", "parent_ref_id": "PR.DS"},

        {"ref_id": "PR.PS", "name": "Platform Security", "parent_ref_id": "PR", "is_assessable": False},
        {"ref_id": "PR.PS-01", "name": "Configuration management practices are established and applied", "parent_ref_id": "PR.PS"},
        {"ref_id": "PR.PS-02", "name": "Software is maintained, replaced, and removed commensurate with risk", "parent_ref_id": "PR.PS"},
        {"ref_id": "PR.PS-03", "name": "Hardware is maintained, replaced, and removed commensurate with risk", "parent_ref_id": "PR.PS"},
        {"ref_id": "PR.PS-04", "name": "Log records are generated and made available for continuous monitoring", "parent_ref_id": "PR.PS"},
        {"ref_id": "PR.PS-05", "name": "Installation and execution of unauthorized software are prevented", "parent_ref_id": "PR.PS"},
        {"ref_id": "PR.PS-06", "name": "Secure software development practices are integrated, and their performance is monitored throughout the SDLC", "parent_ref_id": "PR.PS"},

        {"ref_id": "PR.IR", "name": "Technology Infrastructure Resilience", "parent_ref_id": "PR", "is_assessable": False},
        {"ref_id": "PR.IR-01", "name": "Networks and environments are protected from unauthorized logical access and usage", "parent_ref_id": "PR.IR"},
        {"ref_id": "PR.IR-02", "name": "The organization's technology assets are protected from environmental threats", "parent_ref_id": "PR.IR"},
        {"ref_id": "PR.IR-03", "name": "Mechanisms are implemented to achieve resilience requirements in normal and adverse situations", "parent_ref_id": "PR.IR"},
        {"ref_id": "PR.IR-04", "name": "Adequate resource capacity to ensure availability is maintained", "parent_ref_id": "PR.IR"},

        # DE – Detect
        {"ref_id": "DE", "name": "Detect", "is_assessable": False},
        {"ref_id": "DE.CM", "name": "Continuous Monitoring", "parent_ref_id": "DE", "is_assessable": False},
        {"ref_id": "DE.CM-01", "name": "Networks and network services are monitored to find potentially adverse events", "parent_ref_id": "DE.CM"},
        {"ref_id": "DE.CM-02", "name": "The physical environment is monitored to find potentially adverse events", "parent_ref_id": "DE.CM"},
        {"ref_id": "DE.CM-03", "name": "Personnel activity and technology usage are monitored to find potentially adverse events", "parent_ref_id": "DE.CM"},
        {"ref_id": "DE.CM-06", "name": "External service provider activities and services are monitored to find potentially adverse events", "parent_ref_id": "DE.CM"},
        {"ref_id": "DE.CM-09", "name": "Computing hardware and software, runtime environments, and their data are monitored to find potentially adverse events", "parent_ref_id": "DE.CM"},

        {"ref_id": "DE.AE", "name": "Adverse Event Analysis", "parent_ref_id": "DE", "is_assessable": False},
        {"ref_id": "DE.AE-02", "name": "Potentially adverse events are analyzed to better understand associated activities", "parent_ref_id": "DE.AE"},
        {"ref_id": "DE.AE-03", "name": "Information is correlated from multiple sources", "parent_ref_id": "DE.AE"},
        {"ref_id": "DE.AE-04", "name": "The estimated impact and scope of adverse events are understood", "parent_ref_id": "DE.AE"},
        {"ref_id": "DE.AE-06", "name": "Information on adverse events is provided to authorized staff and tools", "parent_ref_id": "DE.AE"},
        {"ref_id": "DE.AE-07", "name": "Cyber threat intelligence and other contextual information are integrated into the analysis", "parent_ref_id": "DE.AE"},
        {"ref_id": "DE.AE-08", "name": "Incidents are declared when adverse events meet the defined incident criteria", "parent_ref_id": "DE.AE"},

        # RS – Respond
        {"ref_id": "RS", "name": "Respond", "is_assessable": False},
        {"ref_id": "RS.MA", "name": "Incident Management", "parent_ref_id": "RS", "is_assessable": False},
        {"ref_id": "RS.MA-01", "name": "The incident response plan is executed in coordination with relevant third parties once an incident is declared", "parent_ref_id": "RS.MA"},
        {"ref_id": "RS.MA-02", "name": "Incident reports are triaged and validated", "parent_ref_id": "RS.MA"},
        {"ref_id": "RS.MA-03", "name": "Incidents are categorized and prioritized", "parent_ref_id": "RS.MA"},
        {"ref_id": "RS.MA-04", "name": "Incidents are escalated or elevated as needed", "parent_ref_id": "RS.MA"},
        {"ref_id": "RS.MA-05", "name": "The criteria for initiating incident recovery are applied", "parent_ref_id": "RS.MA"},

        {"ref_id": "RS.AN", "name": "Incident Analysis", "parent_ref_id": "RS", "is_assessable": False},
        {"ref_id": "RS.AN-03", "name": "Analysis is performed to establish what has taken place during an incident and the root cause", "parent_ref_id": "RS.AN"},
        {"ref_id": "RS.AN-06", "name": "Actions performed during an investigation are recorded and the records' integrity and provenance are preserved", "parent_ref_id": "RS.AN"},
        {"ref_id": "RS.AN-07", "name": "Incident data and metadata are collected and their integrity and provenance are preserved", "parent_ref_id": "RS.AN"},
        {"ref_id": "RS.AN-08", "name": "An incident's magnitude is estimated and validated", "parent_ref_id": "RS.AN"},

        {"ref_id": "RS.CO", "name": "Incident Response Reporting and Communication", "parent_ref_id": "RS", "is_assessable": False},
        {"ref_id": "RS.CO-02", "name": "Internal and external stakeholders are notified of incidents", "parent_ref_id": "RS.CO"},
        {"ref_id": "RS.CO-03", "name": "Information is shared with designated internal and external stakeholders", "parent_ref_id": "RS.CO"},

        {"ref_id": "RS.MI", "name": "Incident Mitigation", "parent_ref_id": "RS", "is_assessable": False},
        {"ref_id": "RS.MI-01", "name": "Incidents are contained", "parent_ref_id": "RS.MI"},
        {"ref_id": "RS.MI-02", "name": "Incidents are eradicated", "parent_ref_id": "RS.MI"},

        # RC – Recover
        {"ref_id": "RC", "name": "Recover", "is_assessable": False},
        {"ref_id": "RC.RP", "name": "Incident Recovery Plan Execution", "parent_ref_id": "RC", "is_assessable": False},
        {"ref_id": "RC.RP-01", "name": "The recovery portion of the incident response plan is executed once initiated from the incident response process", "parent_ref_id": "RC.RP"},
        {"ref_id": "RC.RP-02", "name": "Recovery actions are selected, scoped, prioritized, and performed", "parent_ref_id": "RC.RP"},
        {"ref_id": "RC.RP-03", "name": "The integrity of backups and other restoration assets is verified before using them for restoration", "parent_ref_id": "RC.RP"},
        {"ref_id": "RC.RP-04", "name": "Critical mission functions and cybersecurity risk management are considered to establish post-incident operational norms", "parent_ref_id": "RC.RP"},
        {"ref_id": "RC.RP-05", "name": "The integrity of restored assets is verified, systems and services are restored, and normal operating status is confirmed", "parent_ref_id": "RC.RP"},
        {"ref_id": "RC.RP-06", "name": "The end of incident recovery is declared based on criteria, and incident-related documentation is completed", "parent_ref_id": "RC.RP"},

        {"ref_id": "RC.CO", "name": "Incident Recovery Communication", "parent_ref_id": "RC", "is_assessable": False},
        {"ref_id": "RC.CO-03", "name": "Recovery activities and progress are communicated to designated internal and external stakeholders", "parent_ref_id": "RC.CO"},
        {"ref_id": "RC.CO-04", "name": "Public updates on incident recovery are shared using approved methods and messaging", "parent_ref_id": "RC.CO"},
    ],
}


BUILT_IN_FRAMEWORKS: list[SeedFramework] = [ISO_27001_2022, NIST_CSF_2_0]
