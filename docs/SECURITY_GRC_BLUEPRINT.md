# Security & GRC Blueprint

This maps concrete backend controls to NIST 800-53 Rev 5 control families, SOC 2 Trust Service Criteria (TSC), and ISO/IEC 27001:2022 Annex A, so the mapping can drop directly into a GRC tracker (e.g., Vanta/Drata/Secureframe) or an internal risk register.

A note on framing: HIPAA itself does not certify a platform — there is no "HIPAA certification." What you build here is a **HIPAA-compliant architecture and program**, evidenced through a signed BAA chain, a completed Security Risk Assessment (45 CFR §164.308(a)(1)), and the technical/administrative/physical safeguards below. SOC 2 and ISO 27001 are complementary attestations that give clinical partners and churches independent assurance.

## 1. Identity, Authentication & Access Control

| Control | Implementation | NIST 800-53 | SOC 2 TSC | ISO 27001 Annex A |
|---|---|---|---|---|
| Unique user identity, no shared logins | `users.id` uuid per person, role enum, no generic service logins for humans | IA-2, IA-4 | CC6.1 | A.5.16, A.8.5 |
| MFA required for all coach/provider/admin roles; strongly encouraged for clients | TOTP via `mfa_secret` 🔒, enforced in login flow before session issuance | IA-2(1) | CC6.1 | A.8.5 |
| Role-based access control (RBAC) | FastAPI dependency injection (`require_role()`) on every route; role checked server-side, never trusted from client | AC-2, AC-3, AC-6 | CC6.1, CC6.3 | A.5.15, A.8.3 |
| Row-level ownership enforcement | Postgres RLS policies as defense-in-depth under app-layer checks (e.g., coach can only `SELECT` clients where `coach_id = current_setting('app.current_coach_id')`) | AC-3, AC-4 | CC6.1 | A.8.3 |
| Least privilege on clinical notes | `session_notes.note_type = 'clinical'` readable only by the assigned provider + the client themself — church/coach roles excluded at the query layer, not just the UI | AC-3, AC-6 | CC6.1, P6.1 (privacy) | A.8.2, A.8.3 |
| Session management | Short-lived JWT access tokens (≤15 min) + rotating refresh tokens, revocation list in Redis, idle timeout | AC-11, AC-12, IA-5 | CC6.1 | A.8.5 |
| Password policy | NIST 800-63B aligned: length over complexity, breach-list check (e.g., HaveIBeenPwned k-anonymity API), no forced rotation | IA-5(1) | CC6.1 | A.5.17 |

## 2. Data Protection

| Control | Implementation | NIST 800-53 | SOC 2 TSC | ISO 27001 |
|---|---|---|---|---|
| Encryption at rest | RDS/S3 encrypted with KMS-managed keys; additional field-level envelope encryption (🔒 fields in schema — DOB, license numbers, PHQ-9/GAD-7 scores, raw intake responses, clinical notes, prayer request text) so a raw DB dump is not directly readable | SC-28, SC-28(1) | CC6.1, CC6.7 | A.8.24 |
| Encryption in transit | TLS 1.2+ enforced at ALB/CloudFront, HSTS, internal service-to-service traffic inside VPC also over TLS | SC-8, SC-13 | CC6.7 | A.8.24 |
| Key management | KMS with automatic rotation, key access restricted to the application's execution role only, no human has standing access to raw data keys | SC-12, SC-28 | CC6.1 | A.8.24 |
| Data minimization | Pydantic response models explicitly allowlist fields per role (e.g., church-facing invoice schema physically cannot serialize a diagnosis field — it doesn't exist on that model) | SI-10, PT-3 | P3.1 (privacy) | A.5.34 |
| Secrets management | AWS Secrets Manager / env injected at container start, never committed, rotated on a schedule | SC-12, CM-6 | CC6.1 | A.8.9 |
| Backup & recovery | Automated encrypted backups, PITR, periodic restore drills | CP-9, CP-10 | A1.2 | A.8.13 |
| Data retention & disposal | Retention schedule per data class (clinical notes retained per state licensure requirements, typically 6-7 yrs; crypto-shredding on account deletion by destroying the client's data-encryption key) | MP-6, SI-12 | C1.2 (confidentiality) | A.8.10 |

## 3. Audit, Monitoring & Incident Response

| Control | Implementation | NIST 800-53 | SOC 2 TSC | ISO 27001 |
|---|---|---|---|---|
| Immutable audit trail | `audit_logs` table, INSERT-only DB grant, every PHI read/write recorded with actor, action, resource, timestamp | AU-2, AU-3, AU-9 | CC7.2 | A.8.15 |
| Centralized log monitoring | Infra logs (CloudTrail, ALB, RDS) shipped to SIEM/log sink separate from the app DB; alerting on anomalous access patterns (e.g., bulk PHI export, off-hours admin access) | AU-6, SI-4 | CC7.1, CC7.2 | A.8.16 |
| Incident response plan | Documented IR runbook: detection → containment → eradication → notification (HIPAA Breach Notification Rule, 60-day clock) → post-incident review | IR-1 through IR-8 | CC7.3, CC7.4 | A.5.24–A.5.28 |
| Vulnerability management | Dependency scanning (pip-audit/npm audit) in CI, scheduled infra vulnerability scans, patch SLAs by severity | RA-5, SI-2 | CC7.1 | A.8.8 |
| Penetration testing | Annual third-party pentest + after major architecture changes, before onboarding first real clinical partner | CA-8 | CC4.1 | A.5.36 |

## 4. Third-Party / Business Associate Management

| Control | Implementation | NIST 800-53 | SOC 2 TSC | ISO 27001 |
|---|---|---|---|---|
| Business Associate Agreements | Signed BAA with cloud provider, any SMS/email vendor touching PHI (e.g., Twilio, SendGrid — both offer BAAs), payment processor scope limited to non-PHI billing data only | PS-7, SA-9 | CC9.2 | A.5.19–A.5.21 |
| Provider vetting (clinical partners) | `clinical_providers.vetting_status` workflow: license verification against state licensing board APIs/manual check, NPI validation, malpractice insurance confirmation, background check, before `accepting_referrals=True` is ever possible | SA-9, PS-3 | CC9.2 | A.5.20 |
| Vendor risk register | Every subprocessor touching PHI (hosting, SMS, email, payments, error-tracking/APM) tracked with BAA status, data flow, and residual risk | SA-9 | CC9.2 | A.5.19 |

## 5. Consent & Privacy-Specific Controls (the "Refer" and "Sponsorship" modules)

| Control | Implementation | Why it matters here |
|---|---|---|
| Release of Information (ROI) as a hard dependency | `referrals` requires a valid, unexpired `roi_consents.id` — enforced by FK + service-layer check, not just a UI checkbox | Prevents a coach or platform from transmitting intake data to a clinical partner without documented, scoped, revocable client authorization — the digital equivalent of a signed paper ROI |
| Scoped disclosure | `roi_consents.scope` (JSONB) defines exactly what may be shared (e.g., "clinical summary" vs. "contact info only") — the referral service filters the payload sent to the provider against this scope | Supports the "minimum necessary" standard under HIPAA |
| Structural church/clinical firewall | Church-facing schemas/queries have no code path that joins to `intake_assessments`, `risk_events`, or clinical `session_notes` — this is a data-model guarantee, not an access-control promise that could be misconfigured later | Directly satisfies the stated requirement that churches see billing, never clinical content |
| Consent revocation | `roi_consents.revoked_at` immediately invalidates future referrals; existing shared data handling documented in the retention policy | Supports client's ongoing right to control disclosure |
| Right of access / accounting of disclosures | Every disclosure event (referral creation, ROI creation) is itself an audited action, so a client's "who has seen my information" request is answerable from `audit_logs` + `referrals` | HIPAA §164.528 accounting of disclosures |

## 6. Governance Cadence (the "G" in GRC, not just technical controls)

- **Risk assessment:** Formal Security Risk Assessment before go-live and at least annually thereafter (45 CFR §164.308(a)(1)(ii)(A)), plus after any material architecture change.
- **Policies:** Written, board/leadership-approved policies for Access Control, Incident Response, Data Retention/Disposal, Acceptable Use, Vendor Management, and a Sanctions Policy for workforce violations — SOC 2 auditors and ISO 27001 certification bodies will request these as evidence, not just the technical controls.
- **Workforce training:** Annual HIPAA/security awareness training for all workforce members with PHI access (coaches, admins, engineers with prod access) — tracked with completion records.
- **Access review:** Quarterly access recertification — confirm every coach/provider/admin account still needs the access it has.
- **Change management:** All schema/infra changes touching PHI-bearing tables go through a documented review (this is exactly the kind of task `operations:change-request` in your toolset is built for once you're past MVP).

## 7. Suggested Immediate Priorities for an MVP Team

1. Get the BAA chain signed (cloud provider, SMS/email vendor) *before* any real client data — not after.
2. Implement audit logging and RBAC in the same sprint as auth — retrofitting audit trails later leaves a gap that's hard to explain to an auditor.
3. Treat the risk engine's hard-stop logic (next section) as safety-critical code: unit-test every branch, code-review by a second engineer, and have a licensed clinical advisor sign off on the actual thresholds/screener items used — the architecture in this doc gives you the routing scaffold, not the clinical judgment calls.
