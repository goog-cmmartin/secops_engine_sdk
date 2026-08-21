import json
from typing import Any, Dict, List, Optional

from engine.domain import (
    IntegrationBatch,
    IntegrationDetail,
    IntegrationInstance,
    IntegrationSearchQuery,
    IntegrationSummary,
    IntegrationType,
    RemoteAgent,
)



def _parse_integration_type(raw_type: str) -> IntegrationType:
    try:
        return IntegrationType(raw_type.upper())
    except Exception:
        return IntegrationType.UNKNOWN


def _parse_environments_list(raw_envs: Any) -> List[str]:
    if isinstance(raw_envs, list):
        return [str(e) for e in raw_envs]
    if isinstance(raw_envs, str):
        raw_envs = raw_envs.strip()
        if raw_envs.startswith("[") and raw_envs.endswith("]"):
            try:
                parsed = json.loads(raw_envs)
                if isinstance(parsed, list):
                    return [str(e) for e in parsed]
            except Exception:
                pass
        if raw_envs:
            return [raw_envs]
    return []


class SearchIntegrationsWorkflow:
    """Executes search and multi-facet filtering across SOAR integrations."""

    def __init__(self, adapter: Any):
        self.adapter = adapter

    def execute(self, query: Optional[IntegrationSearchQuery] = None) -> IntegrationBatch:
        q = query or IntegrationSearchQuery()

        # 1. Fetch live base integrations
        raw_integrations = self.adapter.list_integrations(page_size=1000)

        # 2. Fetch live instances to build instance count and environment index
        raw_instances = self.adapter.list_integration_instances(page_size=1000)

        instance_count_by_integration: Dict[str, int] = {}
        configured_by_integration: Dict[str, bool] = {}
        envs_by_integration: Dict[str, set] = {}

        for inst in raw_instances:
            int_id = inst.get("integrationIdentifier") or inst.get("name", "").split("/")[7] if "/integrations/" in inst.get("name", "") else ""
            if not int_id:
                continue
            instance_count_by_integration[int_id] = instance_count_by_integration.get(int_id, 0) + 1
            if inst.get("configured", False):
                configured_by_integration[int_id] = True
            env = inst.get("environment", "*")
            if int_id not in envs_by_integration:
                envs_by_integration[int_id] = set()
            envs_by_integration[int_id].add(env)

        # 3. Map into IntegrationSummary and filter
        filtered_summaries: List[IntegrationSummary] = []

        for raw_int in raw_integrations:
            ident = raw_int.get("identifier") or raw_int.get("name", "").split("/")[-1]
            display_name = raw_int.get("displayName") or ident
            desc = raw_int.get("description", "")
            version = str(raw_int.get("version") or raw_int.get("latestVersion") or "")
            custom = bool(raw_int.get("custom", False))
            certified = bool(raw_int.get("certified", False))
            staging = bool(raw_int.get("staging", False))
            py_ver = raw_int.get("pythonVersion", "V3_11")
            int_type = _parse_integration_type(raw_int.get("type", "RESPONSE"))
            inst_count = instance_count_by_integration.get(ident, 0)
            is_conf = configured_by_integration.get(ident, False)
            int_envs = envs_by_integration.get(ident, set())

            # Keyword filter
            if q.query:
                term = q.query.lower().strip()
                if term not in ident.lower() and term not in display_name.lower() and term not in desc.lower():
                    continue

            # Certified filter
            if q.is_certified is not None:
                if certified != q.is_certified:
                    continue

            # Configured filter
            if q.is_configured is not None:
                if is_conf != q.is_configured:
                    continue

            # Environment filter
            if q.environment:
                # Matches if specific env is present, or if global '*' is present
                if q.environment not in int_envs and "*" not in int_envs:
                    continue

            summary = IntegrationSummary(
                identifier=ident,
                display_name=display_name,
                description=desc,
                version=version,
                custom=custom,
                certified=certified,
                staging=staging,
                python_version=py_ver,
                integration_type=int_type,
                instances_count=inst_count,
                raw=raw_int,
            )
            filtered_summaries.append(summary)

        # Sort: Configured / high-instance integrations first, then alphabetical
        filtered_summaries.sort(key=lambda s: (-s.instances_count, s.display_name.lower()))

        total_count = len(filtered_summaries)
        limited_results = filtered_summaries[: q.limit]

        return IntegrationBatch(
            results=limited_results,
            total_count=total_count,
        )


class GetIntegrationDetailWorkflow:
    """Retrieves full details for a specific integration with instances and documentation."""

    def __init__(self, adapter: Any):
        self.adapter = adapter

    def execute(self, identifier: str) -> IntegrationDetail:
        ident_clean = identifier.strip()

        # 1. Fetch base integration
        raw_integrations = self.adapter.list_integrations(page_size=1000)
        raw_int = next((i for i in raw_integrations if (i.get("identifier") or i.get("name", "").split("/")[-1]).lower() == ident_clean.lower()), None)
        if not raw_int:
            # Fallback direct query or construct
            raw_int = {
                "identifier": ident_clean,
                "displayName": ident_clean,
                "description": "",
                "version": "",
                "custom": False,
                "certified": False,
                "staging": False,
                "pythonVersion": "V3_11",
                "type": "RESPONSE",
            }

        canonical_ident = raw_int.get("identifier") or ident_clean
        display_name = raw_int.get("displayName") or canonical_ident
        desc = raw_int.get("description", "")
        version = str(raw_int.get("version") or raw_int.get("latestVersion") or "")
        custom = bool(raw_int.get("custom", False))
        certified = bool(raw_int.get("certified", False))
        staging = bool(raw_int.get("staging", False))
        py_ver = raw_int.get("pythonVersion", "V3_11")
        int_type = _parse_integration_type(raw_int.get("type", "RESPONSE"))

        # 2. Fetch instances for this integration
        raw_instances = self.adapter.list_integration_instances(integration_id=canonical_ident)
        instances: List[IntegrationInstance] = []
        for inst in raw_instances:
            inst_ident = inst.get("identifier") or inst.get("name", "").split("/")[-1]
            instances.append(
                IntegrationInstance(
                    identifier=inst_ident,
                    integration_identifier=canonical_ident,
                    display_name=inst.get("displayName") or inst_ident,
                    environment=inst.get("environment", "*"),
                    is_configured=bool(inst.get("configured", False)),
                    is_remote=bool(inst.get("remote", False)),
                    is_system_default=bool(inst.get("systemDefault", False)),
                    name=inst.get("name", ""),
                    raw=inst,
                )
            )

        # 3. Fetch marketplace documentation and categories
        doc_uri = None
        categories: List[str] = []
        try:
            mp_data = self.adapter.get_marketplace_integration(canonical_ident)
            if mp_data:
                doc_uri = mp_data.get("documentationUri")
                categories = mp_data.get("categories", [])
                if not desc and mp_data.get("description"):
                    desc = mp_data.get("description")
                if not version and mp_data.get("version"):
                    version = mp_data.get("version")
        except Exception:
            pass

        # 4. Correlate remote agents supporting the environments of these instances
        remote_agents: List[RemoteAgent] = []
        try:
            raw_agents = self.adapter.list_remote_agents()
            inst_envs = set(inst.environment for inst in instances)
            for a in raw_agents:
                agent_id = a.get("name", "").split("/")[-1]
                agent_ident = a.get("identifier") or agent_id
                agent_envs = _parse_environments_list(a.get("environments"))
                # If agent supports any environment of this integration's instances
                if "*" in inst_envs or any(env in inst_envs for env in agent_envs):
                    remote_agents.append(
                        RemoteAgent(
                            id=agent_id,
                            identifier=agent_ident,
                            display_name=a.get("displayName") or agent_ident,
                            agent_state=a.get("agentState", "ACTIVE"),
                            environments=agent_envs,
                            logging_level=a.get("loggingLevel", "ERROR"),
                            installer_link=a.get("installerLink"),
                            raw=a,
                        )
                    )
        except Exception:
            pass

        return IntegrationDetail(
            identifier=canonical_ident,
            display_name=display_name,
            description=desc,
            version=version,
            custom=custom,
            certified=certified,
            staging=staging,
            python_version=py_ver,
            integration_type=int_type,
            documentation_uri=doc_uri,
            categories=categories,
            instances=instances,
            remote_agents=remote_agents,
            raw=raw_int,
        )


class ListIntegrationInstancesWorkflow:
    """Lists configured integration instances with optional integration/environment filtering."""

    def __init__(self, adapter: Any):
        self.adapter = adapter

    def execute(
        self,
        integration_id: Optional[str] = None,
        environment: Optional[str] = None,
    ) -> List[IntegrationInstance]:
        raw_instances = self.adapter.list_integration_instances(
            integration_id=integration_id,
            environment=environment,
        )
        instances: List[IntegrationInstance] = []
        for inst in raw_instances:
            inst_ident = inst.get("identifier") or inst.get("name", "").split("/")[-1]
            int_id = inst.get("integrationIdentifier") or inst.get("name", "").split("/")[7] if "/integrations/" in inst.get("name", "") else (integration_id or "")
            instances.append(
                IntegrationInstance(
                    identifier=inst_ident,
                    integration_identifier=int_id,
                    display_name=inst.get("displayName") or inst_ident,
                    environment=inst.get("environment", "*"),
                    is_configured=bool(inst.get("configured", False)),
                    is_remote=bool(inst.get("remote", False)),
                    is_system_default=bool(inst.get("systemDefault", False)),
                    name=inst.get("name", ""),
                    raw=inst,
                )
            )
        return instances


class ListRemoteAgentsWorkflow:
    """Lists remote proxy execution agents."""

    def __init__(self, adapter: Any):
        self.adapter = adapter

    def execute(self, state_filter: Optional[str] = None) -> List[RemoteAgent]:
        raw_res = self.adapter.list_remote_agents(state_filter=state_filter)
        raw_agents = raw_res.get("remoteAgents", []) if isinstance(raw_res, dict) else raw_res
        agents: List[RemoteAgent] = []
        for a in raw_agents:
            agent_id = a.get("name", "").split("/")[-1]
            agent_ident = a.get("identifier") or agent_id
            agent_envs = _parse_environments_list(a.get("environments"))
            agents.append(
                RemoteAgent(
                    id=agent_id,
                    identifier=agent_ident,
                    display_name=a.get("displayName") or agent_ident,
                    agent_state=a.get("agentState", "ACTIVE"),
                    environments=agent_envs,
                    logging_level=a.get("loggingLevel", "ERROR"),
                    installer_link=a.get("installerLink"),
                    raw=a,
                )
            )
        return agents
