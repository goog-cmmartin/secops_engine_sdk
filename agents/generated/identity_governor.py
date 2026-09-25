"""Generated Google ADK 2 Agent: Identity Governor.

Auto-generated from agents/manifests/identity_governor.yaml. Do not edit directly.
"""

from typing import Any, Optional
from datetime import datetime, timezone
import json
import logging
from typing import Any, Dict, List, Optional
from agents.core.evidence_store import diff_iam_audits
from agents.core.base_adk_agent import BaseSecOpsAdkAgent
from engine.facade import SecOpsEngine
from agents.core.proposal_manager import ProposalManager
from agents.core.evidence_store import EvidenceFabricStore


class IdentityGovernorAgent(BaseSecOpsAdkAgent):
    """Google Cloud IAM & Chronicle Access Governance Specialist.

    Audits GCP IAM bindings for predefined Chronicle roles, tracks custom roles with chronicle.* permissions, queries SecOps Inventory access reports, and monitors privilege drift across runs.
    """

    CAPABILITIES = ['identity.iam.bindings', 'identity.custom_roles.list', 'identity.inventory.report']

    def __init__(
        self,
        engine: Optional[SecOpsEngine] = None,
        proposal_manager: Optional[ProposalManager] = None,
        inventory_client: Any = None,
        evidence_store: Optional[EvidenceFabricStore] = None,
        work_queue: Optional[Any] = None,
        lifecycle_manager: Optional[Any] = None,
    ):
        super().__init__(
            name='Identity Governor',
            handle='@identity-governor',
            role='Google Cloud IAM & Chronicle Access Governance Specialist',
            subsystem='identity_governance',
            description='Audits GCP IAM bindings for predefined Chronicle roles, tracks custom roles with chronicle.* permissions, queries SecOps Inventory access reports, and monitors privilege drift across runs.',
            system_instruction='You are the Identity Governor Agent for Google SecOps (@identity-governor).\nYour mission is to continuously audit, enforce, and govern access across Google SecOps and Chronicle SIEM/SOAR.\nSpecifically, you:\n1. Inspect Google Cloud project IAM policies to audit bindings for standard predefined Chronicle roles:\n   - roles/chronicle.admin (Chronicle API Admin)\n   - roles/chronicle.dataGovernor (Chronicle API Data Governor)\n   - roles/chronicle.editor (Chronicle API Editor)\n   - roles/chronicle.federationAdmin (Chronicle API Federation Admin)\n   - roles/chronicle.federationViewer (Chronicle API Federation Viewer)\n   - roles/chronicle.globalDataAccess (Chronicle API Global Data Access)\n   - roles/chronicle.limitedViewer (Chronicle API Limited Viewer)\n   - roles/chronicle.orgServiceAgent (Chronicle Organization Service Agent)\n   - roles/chronicle.restrictedDataAccess (Chronicle API Restricted Data Access)\n   - roles/chronicle.restrictedDataAccessViewer (Chronicle API Restricted Data Access Viewer)\n   - and additional predefined roles (roles/chronicle.viewer, roles/chronicle.soarAdmin, etc.).\n2. Identify and classify all assigned members: users, groups, service accounts, and workforce identity pools (principalSet://...).\n3. Query custom GCP IAM roles within the project to identify any role bundling chronicle.* permissions.\n4. Correlate findings with the SecOps Inventory Identity Access audit (/api/tenants/{tenant}/audits/SecOps Access/view and /api/reports/12).\n5. Run snapshot audits persisted to the Evidence Fabric (iam_audits) to detect privilege drift (granted or revoked access, new custom roles, and permission drift) compared to prior audit runs.\n6. Ambiguity & Clarification Guardrails:\n   - If the operator request does not specify a target principal, project, or role scope, audit project-level Chronicle bindings or request clarification before assuming intent.\n7. Output Formatting & Conciseness Constraints:\n   - Provide an executive summary of IAM governance in at most 3 bullet points (privileged users count, custom roles with chronicle.* permissions, and privilege drift).\n   - Group findings clearly by role tier (Admin vs Editor vs Viewer).',
            model='gemini-3.8-flash',
            default_stream='identity',
            default_topic='iam-audit',
            engine=engine,
            proposal_manager=proposal_manager,
            inventory_client=inventory_client,
            evidence_store=evidence_store,
            work_queue=work_queue,
            lifecycle_manager=lifecycle_manager,
        )

        # Bind declared capabilities from engine registry if engine is provided
        if self.engine:
            for cap_id in self.CAPABILITIES:
                cap = self.engine.registry.get(cap_id)
                if cap:
                    self.bind_capability(cap)

        self._tools["audit_chronicle_iam_bindings"] = self.audit_chronicle_iam_bindings
        self._tools["query_chronicle_custom_roles"] = self.query_chronicle_custom_roles
        self._tools["query_inventory_identity_report"] = self.query_inventory_identity_report
        self._tools["run_identity_drift_audit"] = self.run_identity_drift_audit

    def audit_chronicle_iam_bindings(
        self,
        project_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Audits project GCP IAM policy for default predefined Chronicle roles and assigned members.

        Args:
            project_id: Optional GCP project ID to inspect (defaults to engine project).
        """
        bindings = self.engine.get_chronicle_iam_bindings(project_id=project_id)
        
        # Categorize members across all bindings
        by_role = {}
        users = set()
        groups = set()
        service_accounts = set()
        workforce_pools = set()

        for b in bindings:
            by_role[b.role] = {
                "role_title": b.role_title,
                "is_custom": b.is_custom,
                "members": b.members,
            }
            for m in b.members:
                if m.startswith("user:"):
                    users.add(m[5:])
                elif m.startswith("group:"):
                    groups.add(m[6:])
                elif m.startswith("serviceAccount:"):
                    service_accounts.add(m[15:])
                elif m.startswith("principalSet://") or m.startswith("principal://"):
                    workforce_pools.add(m)

        self.executed_tool_calls.append({
            "agent": self.handle,
            "tool": "audit_chronicle_iam_bindings",
            "capability_id": "identity.iam.bindings",
            "arguments": {"project_id": project_id},
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })

        return {
            "status": "SUCCESS",
            "project_id": project_id or getattr(self.engine.adapter, "project_id", "sdl-preview-americas"),
            "total_chronicle_roles_assigned": len(bindings),
            "users_count": len(users),
            "users": sorted(list(users)),
            "groups_count": len(groups),
            "groups": sorted(list(groups)),
            "service_accounts_count": len(service_accounts),
            "service_accounts": sorted(list(service_accounts)),
            "workforce_pools_count": len(workforce_pools),
            "workforce_pools": sorted(list(workforce_pools)),
            "roles": by_role,
        }

    def query_chronicle_custom_roles(
        self,
        project_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Discovers custom GCP IAM roles within the project granting chronicle.* permissions.

        Args:
            project_id: Optional GCP project ID to inspect.
        """
        custom_roles = self.engine.get_chronicle_custom_roles(project_id=project_id)
        
        roles_summary = []
        for r in custom_roles:
            roles_summary.append({
                "role_name": r.role_name,
                "title": r.title,
                "description": r.description,
                "stage": r.stage,
                "chronicle_permissions_count": len(r.chronicle_permissions),
                "chronicle_permissions": r.chronicle_permissions,
                "total_permissions_count": r.total_permissions_count,
            })

        self.executed_tool_calls.append({
            "agent": self.handle,
            "tool": "query_chronicle_custom_roles",
            "capability_id": "identity.custom_roles.list",
            "arguments": {"project_id": project_id},
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })

        return {
            "status": "SUCCESS",
            "project_id": project_id or getattr(self.engine.adapter, "project_id", "sdl-preview-americas"),
            "custom_roles_count": len(custom_roles),
            "custom_roles": roles_summary,
        }

    def query_inventory_identity_report(
        self,
        inventory_base_url: str = "http://localhost:8000",
        tenant_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Queries the local SecOps Inventory service for SecOps Access and Identity reports.

        Args:
            inventory_base_url: Base URL of SecOps Inventory service (defaults to http://localhost:8000).
            tenant_id: Target tenant identifier or project ID.
        """
        report = self.engine.fetch_inventory_identity_report(
            inventory_base_url=inventory_base_url,
            tenant_id=tenant_id,
        )

        self.executed_tool_calls.append({
            "agent": self.handle,
            "tool": "query_inventory_identity_report",
            "capability_id": "identity.inventory.report",
            "arguments": {"inventory_base_url": inventory_base_url, "tenant_id": tenant_id},
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })

        return report

    def run_identity_drift_audit(
        self,
        project_id: Optional[str] = None,
        inventory_base_url: str = "http://localhost:8000",
    ) -> Dict[str, Any]:
        """Runs a complete IAM audit snapshot, stores it in the Evidence Fabric, and computes privilege drift against prior runs.

        Args:
            project_id: Target GCP project ID.
            inventory_base_url: Base URL of SecOps Inventory service.
        """
        proj = project_id or getattr(self.engine.adapter, "project_id", "sdl-preview-americas")
        rep = self.engine.generate_identity_governance_report(
            project_id=proj,
            inventory_base_url=inventory_base_url,
        )

        # Retrieve prior audit from Evidence Fabric
        prior_audit = None
        if self.evidence_store:
            prior_audit = self.evidence_store.get_latest_iam_audit(project_id=proj)

        curr_payload = {
            "audit_id": f"iam_audit_{proj}_{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}",
            "project_id": proj,
            "timestamp": rep.timestamp,
            "chronicle_bindings": [
                {
                    "role": b.role,
                    "role_title": b.role_title,
                    "is_custom": b.is_custom,
                    "members": b.members,
                }
                for b in rep.chronicle_bindings
            ],
            "custom_roles": [
                {
                    "role_name": r.role_name,
                    "title": r.title,
                    "chronicle_permissions": r.chronicle_permissions,
                }
                for r in rep.custom_roles
            ],
            "total_privileged_users": rep.total_privileged_users,
            "total_groups": rep.total_groups,
            "total_service_accounts": rep.total_service_accounts,
            "total_workforce_pools": rep.total_workforce_pools,
            "inventory_summary": rep.inventory_summary,
        }

        # Save to Evidence Fabric
        audit_id = curr_payload["audit_id"]
        if self.evidence_store:
            audit_id = self.evidence_store.save_iam_audit(curr_payload)

        # Compute privilege drift
        drift_result = diff_iam_audits(prior_audit, curr_payload)

        # Attach interactive UI widget
        identity_widget = {
            "type": "identity_governance_card",
            "audit_id": audit_id,
            "project_id": proj,
            "has_drift": drift_result.get("has_drift", False),
            "drift_status": drift_result.get("status"),
            "drift_summary": drift_result.get("summary"),
            "members_added": drift_result.get("members_added", []),
            "members_removed": drift_result.get("members_removed", []),
            "custom_roles_count": len(rep.custom_roles),
            "users_count": rep.total_privileged_users,
            "groups_count": rep.total_groups,
            "service_accounts_count": rep.total_service_accounts,
            "workforce_pools_count": rep.total_workforce_pools,
            "timestamp": rep.timestamp,
        }
        self.last_widget = identity_widget

        self.executed_tool_calls.append({
            "agent": self.handle,
            "tool": "run_identity_drift_audit",
            "capability_id": "identity.audit.drift",
            "arguments": {"project_id": proj},
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })

        return {
            "status": "SUCCESS",
            "audit_id": audit_id,
            "project_id": proj,
            "timestamp": rep.timestamp,
            "drift": drift_result,
            "total_users": rep.total_privileged_users,
            "total_groups": rep.total_groups,
            "total_service_accounts": rep.total_service_accounts,
            "total_workforce_pools": rep.total_workforce_pools,
            "custom_roles_count": len(rep.custom_roles),
            "widget": identity_widget,
        }
