---
id: concept.workforce_identity_federation
title: Workforce Identity Pools & SecOps Role Governance
type: concept
applies_to:
- gcp
- secops_siem
- secops_soar
related_features:
- feature.gcp.workforce_identity
- feature.siem.data_rbac
tags:
- iam
- federation
- access_governance
status: stable
description: Workforce Identity Pools & SecOps Role Governance (concept reference
  in Google SecOps).
generated:
  by: process:secops-sdk-v1
  at: '2026-09-20T00:00:00Z'
verified:
- by: human:secops-architect
  at: '2026-09-21T12:00:00Z'
stale_after: '2027-01-01T00:00:00Z'
sources:
- id: google-secops-docs
  resource: https://cloud.google.com/chronicle/docs
  title: Google SecOps Official Documentation
---

# Workforce Identity Pools & SecOps Role Governance

## 1. Overview & Mental Model
Google SecOps supports external identity provider (IdP) federation via **GCP Workforce Identity Pools** (e.g., Okta, Azure AD / Entra ID, PingIdentity). Rather than syncing individual user credentials into Google Cloud, external SAML/OIDC tokens are exchanged for short-lived Google OAuth tokens via Security Token Service (STS).

## 2. Role Mapping & Privilege Hierarchy
Federated users inherit SecOps access through IAM role bindings attached to workforce pool attributes (e.g., `principalSet://iam.googleapis.com/locations/global/workforcePools/na-sdl-pool/group/secops-admins`):
- **Chronicle Admin (`roles/chronicle.admin`):** Full administrative control over YARA-L rules, feeds, parsers, and global settings.
- **Federation Admin (`roles/chronicle.federationAdmin`):** Authority to configure and manage identity pool mappings and group synchronizations.
- **SOAR Admin (`roles/chronicle.soarAdmin`):** Full authority across SOAR environments, integrations, playbooks, and case configurations.
- **Data RBAC Scopes:** Restricts federated users to specific log types, namespaces, or customer compartments via UDM data labels.

## 3. Operational Guarantees & Constraints
- External session durations are constrained by STS token lifetimes (typically 1 to 12 hours).
- Inactive accounts or revoked IdP group memberships immediately lose access upon token refresh.
