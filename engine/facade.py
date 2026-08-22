from typing import Any, Callable, Dict, List, Optional, Union

from engine.domain import (
    AlertInvestigation,
    CaseCommentRecord,
    CaseInvestigation,
    CaseSearchBatch,
    CaseSearchQuery,
    CaseSearchResultItem,
    CaseStatus,
    ContentPackBatch,
    ContentPackDetail,
    ContentPackSearchQuery,
    ContentPackSummary,
    CuratedDetectionMetrics,
    CuratedRuleDetail,
    CuratedRuleSearchQuery,
    CuratedRuleSetBatch,
    CuratedRuleSetDetail,
    CuratedRuleSetSummary,
    CuratedRuleSummary,
    DashboardBatch,
    DashboardChart,
    DashboardDetail,
    DashboardQuery,
    DashboardQueryResult,
    DashboardSearchQuery,
    DashboardSummary,
    EntityType,
    EventInvestigation,
    EventReference,
    FeedBatch,
    FeedDetail,
    FeedLogTypeBatch,
    FeedLogTypeSchema,
    FeedSearchQuery,
    FeedSourceTypeBatch,
    FeedSourceTypeSchema,
    FeedSummary,
    FieldFilter,
    FilterOperator,
    IntegrationBatch,
    IntegrationDetail,
    IntegrationInstance,
    IntegrationSearchQuery,
    IntegrationSummary,
    IntegrationType,
    JobBatch,
    JobDetail,
    JobExecutionLog,
    JobExecutionStatus,
    JobInstance,
    JobSearchQuery,
    JobSummary,
    LogProcessingPipelineBatch,
    LogProcessingPipelineDetail,
    LogProcessingPipelineSummary,
    LogTypeBatch,
    LogTypeSetting,
    LogTypeSummary,
    ManagedDomain,
    ManagedDomainSettings,
    MarketplaceAffectedItems,
    MarketplaceCommercialDiff,
    MarketplaceIntegrationBatch,
    MarketplaceIntegrationDetail,
    MarketplaceIntegrationReleaseNote,
    MarketplaceIntegrationSearchQuery,
    MarketplaceIntegrationSummary,
    ParserBatch,
    ParserDetail,
    ParserExtensionBatch,
    ParserExtensionDetail,
    ParserExtensionSummary,
    ParserSummary,
    PlaybookBatch,
    PlaybookCategory,
    PlaybookDetail,
    PlaybookSearchQuery,
    PlaybookSummary,
    PlaybookType,
    PreviewFeatureBatch,
    PreviewFeatureSummary,
    DataAccessScopeBatch,
    DataAccessScopeDetail,
    DataAccessScopeSummary,
    DataAccessLabelBatch,
    DataAccessLabelDetail,
    DataAccessLabelSummary,
    EnvironmentScopeBatch,
    EnvironmentScopeSummary,
    EnrichmentCombinationBatch,
    EnrichmentCombinationRecord,
    EnrichmentControlBatch,
    EnrichmentControlDetail,
    EnrichmentControlSummary,
    GeminiAgentSettings,
    EntityRiskConfig,
    TenantInstanceDetails,
    SoarUserSummary,
    SoarUserDetail,
    SoarUserBatch,
    SocRoleSummary,
    SocRoleBatch,
    CompanySettingProperty,
    CompanySettingsBatch,
    CaseTagDefinitionSummary,
    CaseTagDefinitionBatch,
    CaseStageDefinitionSummary,
    CaseStageDefinitionBatch,
    CaseCloseDefinitionSummary,
    CaseCloseDefinitionBatch,
    CaseCloseDynamicParameterSummary,
    CaseCloseDynamicParameterBatch,
    CaseTitleSettingProperty,
    CaseTitleSettingsBatch,
    CaseViewSummary,
    CaseViewDetail,
    CaseViewBatch,
    CustomFieldSummary,
    CustomFieldDetail,
    CustomFieldBatch,
    CalculatedFieldSummary,
    CalculatedFieldDetail,
    CalculatedFieldBatch,
    AlertGroupingCategoryDetail,
    AlertGroupingRuleSummary,
    AlertGroupingRuleDetail,
    AlertGroupingRuleBatch,
    AlertGroupingSettingProperty,
    AlertGroupingSettingsBatch,
    DataRetentionSettingProperty,
    DataRetentionSettingsBatch,
    EmailSettingProperty,
    EmailSettingsBatch,
    EnvironmentBatch,
    EnvironmentDetail,
    EnvironmentGroupBatch,
    EnvironmentGroupSummary,
    EnvironmentSummary,
    RemoteAgent,
    RemoteAgentBatch,
    RemoteAgentDetail,
    RemoteAgentSummary,
    SearchBatchResult,
    SearchRequest,
    SearchSession,
    SupportSettingProperty,
    SupportSettingsBatch,
    SoarNetworkSummary,
    SoarNetworkDetail,
    SoarNetworkBatch,
    SoarDomainSummary,
    SoarDomainDetail,
    SoarDomainBatch,
    SoarCustomListSummary,
    SoarCustomListDetail,
    SoarCustomListBatch,
    EmailTemplateSummary,
    EmailTemplateDetail,
    EmailTemplateBatch,
    EntitiesBlocklistSummary,
    EntitiesBlocklistDetail,
    EntitiesBlocklistBatch,
    SlaDefinitionSummary,
    SlaDefinitionDetail,
    SlaDefinitionBatch,
    RequestTemplateFieldDefinition,
    RequestTemplateSummary,
    RequestTemplateDetail,
    RequestTemplateBatch,
    SoarIngestionConnectorSummary,
    SoarIngestionConnectorDetail,
    SoarIngestionConnectorBatch,
    SoarWebhookSummary,
    SoarWebhookDetail,
    SoarWebhookBatch,
    ValidationResult,
)
from engine.registry import WorkflowCapability, WorkflowRegistry, registry
from engine.workflows.alert_investigation import InvestigateAlertWorkflow
from engine.workflows.case_investigation import (
    AddCaseCommentWorkflow,
    InvestigateCaseWorkflow,
)
from engine.workflows.case_search import SearchCasesWorkflow
from engine.workflows.content_pack import (
    GetContentPackDetailWorkflow,
    ListContentPackCategoriesWorkflow,
    SearchContentPacksWorkflow,
)
from engine.workflows.curated_detections import (
    GetCuratedDetectionMetricsWorkflow,
    GetCuratedRuleDetailWorkflow,
    GetCuratedRuleSetDetailWorkflow,
    SearchCuratedRuleSetsWorkflow,
)
from engine.workflows.dashboards import (
    ExecuteDashboardQueryWorkflow,
    GetDashboardDetailWorkflow,
    SearchDashboardsWorkflow,
    ValidateDashboardQueryWorkflow,
)
from engine.workflows.data_rbac import (
    GetDataAccessLabelWorkflow,
    GetDataAccessScopeWorkflow,
    SearchDataAccessLabelsWorkflow,
    SearchDataAccessScopesWorkflow,
    SearchEnvironmentScopesWorkflow,
)
from engine.workflows.enrichment import (
    GetEnrichmentControlWorkflow,
    ListEnrichmentCombinationsWorkflow,
    SearchEnrichmentControlsWorkflow,
)
from engine.workflows.feed import (
    GetFeedDetailWorkflow,
    ListFeedLogTypeSchemasWorkflow,
    ListFeedSourceTypeSchemasWorkflow,
    SearchFeedsWorkflow,
)
from engine.workflows.integration import (
    GetIntegrationDetailWorkflow,
    ListIntegrationInstancesWorkflow,
    ListRemoteAgentsWorkflow,
    SearchIntegrationsWorkflow,
)
from engine.workflows.investigate_event import InvestigateEventWorkflow
from engine.workflows.job import (
    GetJobDetailWorkflow,
    GetJobInstanceLogsWorkflow,
    ListJobInstancesWorkflow,
    SearchJobsWorkflow,
)
from engine.workflows.marketplace_integrations import (
    GetMarketplaceIntegrationAffectedItemsWorkflow,
    GetMarketplaceIntegrationDetailWorkflow,
    GetMarketplaceIntegrationDiffWorkflow,
    SearchMarketplaceIntegrationsWorkflow,
)
from engine.workflows.parser import (
    GetLogTypeSettingWorkflow,
    GetParserDetailWorkflow,
    GetParserExtensionDetailWorkflow,
    ListLogTypesWorkflow,
    SearchParserExtensionsWorkflow,
    SearchParsersWorkflow,
)
from engine.workflows.playbook import (
    GetPlaybookWorkflow,
    ListPlaybookCategoriesWorkflow,
    SearchPlaybooksWorkflow,
)
from engine.workflows.preview_feature import (
    GetPreviewFeatureWorkflow,
    ListPreviewFeaturesWorkflow,
)
from engine.workflows.refine_search import (
    RefineSearchWorkflow,
    SearchFromEntityWorkflow,
)
from engine.workflows.search_udm import SearchUDMWorkflow
from engine.workflows.siem_settings import (
    GetAgentSettingsWorkflow,
    GetEntityRiskConfigWorkflow,
    GetLogProcessingPipelineDetailWorkflow,
    GetManagedDomainSettingsWorkflow,
    GetTenantInstanceWorkflow,
    SearchLogProcessingPipelinesWorkflow,
)
from engine.workflows.soar_settings import (
    GetCompanySettingsWorkflow,
    GetDataRetentionSettingsWorkflow,
    GetEmailSettingsWorkflow,
    GetEnvironmentWorkflow,
    GetRemoteAgentWorkflow,
    GetSoarUserWorkflow,
    GetSupportSettingsWorkflow,
    ListSocRolesWorkflow,
    SearchEnvironmentGroupsWorkflow,
    SearchEnvironmentsWorkflow,
    SearchRemoteAgentsWorkflow,
    SearchSoarUsersWorkflow,
    SearchSoarNetworksWorkflow,
    GetSoarNetworkWorkflow,
    SearchSoarDomainsWorkflow,
    GetSoarDomainWorkflow,
    SearchSoarCustomListsWorkflow,
    GetSoarCustomListWorkflow,
    SearchEmailTemplatesWorkflow,
    GetEmailTemplateWorkflow,
    SearchEntitiesBlocklistsWorkflow,
    GetEntitiesBlocklistWorkflow,
    SearchSlaDefinitionsWorkflow,
    GetSlaDefinitionWorkflow,
    SearchRequestTemplatesWorkflow,
    GetRequestTemplateWorkflow,
    SearchSoarIngestionConnectorsWorkflow,
    GetSoarIngestionConnectorWorkflow,
    SearchSoarWebhooksWorkflow,
    GetSoarWebhookWorkflow,
)
from engine.workflows.case_config import (
    GetAlertGroupingRuleWorkflow,
    GetAlertGroupingSettingsWorkflow,
    GetCalculatedFieldWorkflow,
    GetCaseTitleSettingsWorkflow,
    GetCaseViewWorkflow,
    GetCustomFieldWorkflow,
    ListCaseCloseDefinitionsWorkflow,
    ListCaseCloseDynamicParametersWorkflow,
    ListCaseStageDefinitionsWorkflow,
    SearchAlertGroupingRulesWorkflow,
    SearchCalculatedFieldsWorkflow,
    SearchCaseTagDefinitionsWorkflow,
    SearchCaseViewsWorkflow,
    SearchCustomFieldsWorkflow,
)



class SecOpsEngine:
    """The central workflow engine exposing high-level SecOps domain capabilities."""

    def __init__(
        self,
        adapter: Optional[Any] = None,
        custom_registry: Optional[WorkflowRegistry] = None,
    ):
        if adapter is None:
            from adapters.google_secops import GoogleSecOpsAdapter
            adapter = GoogleSecOpsAdapter()
        self.adapter = adapter
        self.registry = custom_registry or registry
        self._wf_cache: Dict[str, Any] = {}

        # Register default capabilities
        self._register_default_capabilities()

    _WORKFLOW_MAP = {
        "_search_udm_wf": lambda e: SearchUDMWorkflow(e.adapter),
        "_investigate_event_wf": lambda e: InvestigateEventWorkflow(e.adapter),
        "_refine_search_wf": lambda e: RefineSearchWorkflow(e._search_udm_wf),
        "_search_from_entity_wf": lambda e: SearchFromEntityWorkflow(e._search_udm_wf),
        "_investigate_case_wf": lambda e: InvestigateCaseWorkflow(e.adapter),
        "_add_case_comment_wf": lambda e: AddCaseCommentWorkflow(e.adapter),
        "_investigate_alert_wf": lambda e: InvestigateAlertWorkflow(e.adapter),
        "_search_cases_wf": lambda e: SearchCasesWorkflow(e.adapter),
        "_search_playbooks_wf": lambda e: SearchPlaybooksWorkflow(e.adapter),
        "_get_playbook_wf": lambda e: GetPlaybookWorkflow(e.adapter),
        "_list_playbook_cats_wf": lambda e: ListPlaybookCategoriesWorkflow(e.adapter),
        "_search_integrations_wf": lambda e: SearchIntegrationsWorkflow(e.adapter),
        "_get_integration_wf": lambda e: GetIntegrationDetailWorkflow(e.adapter),
        "_list_integration_instances_wf": lambda e: ListIntegrationInstancesWorkflow(e.adapter),
        "_list_remote_agents_wf": lambda e: ListRemoteAgentsWorkflow(e.adapter),
        "_search_jobs_wf": lambda e: SearchJobsWorkflow(e.adapter),
        "_get_job_wf": lambda e: GetJobDetailWorkflow(e.adapter),
        "_list_job_instances_wf": lambda e: ListJobInstancesWorkflow(e.adapter),
        "_get_job_instance_logs_wf": lambda e: GetJobInstanceLogsWorkflow(e.adapter),
        "_search_content_packs_wf": lambda e: SearchContentPacksWorkflow(e.adapter),
        "_get_content_pack_wf": lambda e: GetContentPackDetailWorkflow(e.adapter),
        "_list_content_pack_cats_wf": lambda e: ListContentPackCategoriesWorkflow(e.adapter),
        "_search_curated_rulesets_wf": lambda e: SearchCuratedRuleSetsWorkflow(e.adapter),
        "_get_curated_ruleset_wf": lambda e: GetCuratedRuleSetDetailWorkflow(e.adapter),
        "_get_curated_rule_wf": lambda e: GetCuratedRuleDetailWorkflow(e.adapter),
        "_get_curated_metrics_wf": lambda e: GetCuratedDetectionMetricsWorkflow(e.adapter),
        "_search_marketplace_integrations_wf": lambda e: SearchMarketplaceIntegrationsWorkflow(e.adapter),
        "_get_marketplace_integration_wf": lambda e: GetMarketplaceIntegrationDetailWorkflow(e.adapter),
        "_get_marketplace_integration_diff_wf": lambda e: GetMarketplaceIntegrationDiffWorkflow(e.adapter),
        "_get_marketplace_affected_items_wf": lambda e: GetMarketplaceIntegrationAffectedItemsWorkflow(e.adapter),
        "_search_dashboards_wf": lambda e: SearchDashboardsWorkflow(e.adapter),
        "_get_dashboard_wf": lambda e: GetDashboardDetailWorkflow(e.adapter),
        "_execute_dashboard_query_wf": lambda e: ExecuteDashboardQueryWorkflow(e.adapter),
        "_validate_dashboard_query_wf": lambda e: ValidateDashboardQueryWorkflow(e.adapter),
        "_get_managed_domains_wf": lambda e: GetManagedDomainSettingsWorkflow(e.adapter),
        "_search_feeds_wf": lambda e: SearchFeedsWorkflow(e.adapter),
        "_get_feed_wf": lambda e: GetFeedDetailWorkflow(e.adapter),
        "_search_pipelines_wf": lambda e: SearchLogProcessingPipelinesWorkflow(e.adapter),
        "_get_pipeline_wf": lambda e: GetLogProcessingPipelineDetailWorkflow(e.adapter),
        "_list_feed_source_types_wf": lambda e: ListFeedSourceTypeSchemasWorkflow(e.adapter),
        "_list_feed_log_types_wf": lambda e: ListFeedLogTypeSchemasWorkflow(e.adapter),
        "_list_log_types_wf": lambda e: ListLogTypesWorkflow(e.adapter),
        "_search_parsers_wf": lambda e: SearchParsersWorkflow(e.adapter),
        "_get_parser_wf": lambda e: GetParserDetailWorkflow(e.adapter),
        "_search_parser_extensions_wf": lambda e: SearchParserExtensionsWorkflow(e.adapter),
        "_get_parser_extension_wf": lambda e: GetParserExtensionDetailWorkflow(e.adapter),
        "_get_log_type_setting_wf": lambda e: GetLogTypeSettingWorkflow(e.adapter),
        "_list_preview_features_wf": lambda e: ListPreviewFeaturesWorkflow(e.adapter),
        "_get_preview_feature_wf": lambda e: GetPreviewFeatureWorkflow(e.adapter),
        "_search_data_access_scopes_wf": lambda e: SearchDataAccessScopesWorkflow(e.adapter),
        "_get_data_access_scope_wf": lambda e: GetDataAccessScopeWorkflow(e.adapter),
        "_search_data_access_labels_wf": lambda e: SearchDataAccessLabelsWorkflow(e.adapter),
        "_get_data_access_label_wf": lambda e: GetDataAccessLabelWorkflow(e.adapter),
        "_search_environment_scopes_wf": lambda e: SearchEnvironmentScopesWorkflow(e.adapter),
        "_list_enrichment_combinations_wf": lambda e: ListEnrichmentCombinationsWorkflow(e.adapter),
        "_search_enrichment_controls_wf": lambda e: SearchEnrichmentControlsWorkflow(e.adapter),
        "_get_enrichment_control_wf": lambda e: GetEnrichmentControlWorkflow(e.adapter),
        "_get_agent_settings_wf": lambda e: GetAgentSettingsWorkflow(e.adapter),
        "_get_entity_risk_config_wf": lambda e: GetEntityRiskConfigWorkflow(e.adapter),
        "_get_tenant_instance_wf": lambda e: GetTenantInstanceWorkflow(e.adapter),
        "_search_soar_users_wf": lambda e: SearchSoarUsersWorkflow(e.adapter),
        "_get_soar_user_wf": lambda e: GetSoarUserWorkflow(e.adapter),
        "_list_soc_roles_wf": lambda e: ListSocRolesWorkflow(e.adapter),
        "_get_company_settings_wf": lambda e: GetCompanySettingsWorkflow(e.adapter),
        "_search_case_tags_wf": lambda e: SearchCaseTagDefinitionsWorkflow(e.adapter),
        "_list_case_stages_wf": lambda e: ListCaseStageDefinitionsWorkflow(e.adapter),
        "_list_case_close_defs_wf": lambda e: ListCaseCloseDefinitionsWorkflow(e.adapter),
        "_list_case_close_params_wf": lambda e: ListCaseCloseDynamicParametersWorkflow(e.adapter),
        "_get_case_title_settings_wf": lambda e: GetCaseTitleSettingsWorkflow(e.adapter),
        "_search_case_views_wf": lambda e: SearchCaseViewsWorkflow(e.adapter),
        "_get_case_view_wf": lambda e: GetCaseViewWorkflow(e.adapter),
        "_search_custom_fields_wf": lambda e: SearchCustomFieldsWorkflow(e.adapter),
        "_get_custom_field_wf": lambda e: GetCustomFieldWorkflow(e.adapter),
        "_search_calculated_fields_wf": lambda e: SearchCalculatedFieldsWorkflow(e.adapter),
        "_get_calculated_field_wf": lambda e: GetCalculatedFieldWorkflow(e.adapter),
        "_search_alert_grouping_rules_wf": lambda e: SearchAlertGroupingRulesWorkflow(e.adapter),
        "_get_alert_grouping_rule_wf": lambda e: GetAlertGroupingRuleWorkflow(e.adapter),
        "_get_alert_grouping_settings_wf": lambda e: GetAlertGroupingSettingsWorkflow(e.adapter),
        "_get_data_retention_settings_wf": lambda e: GetDataRetentionSettingsWorkflow(e.adapter),
        "_search_environments_wf": lambda e: SearchEnvironmentsWorkflow(e.adapter),
        "_get_environment_wf": lambda e: GetEnvironmentWorkflow(e.adapter),
        "_search_environment_groups_wf": lambda e: SearchEnvironmentGroupsWorkflow(e.adapter),
        "_search_remote_agents_wf": lambda e: SearchRemoteAgentsWorkflow(e.adapter),
        "_get_remote_agent_wf": lambda e: GetRemoteAgentWorkflow(e.adapter),
        "_get_email_settings_wf": lambda e: GetEmailSettingsWorkflow(e.adapter),
        "_get_support_settings_wf": lambda e: GetSupportSettingsWorkflow(e.adapter),
        "_search_soar_networks_wf": lambda e: SearchSoarNetworksWorkflow(e.adapter),
        "_get_soar_network_wf": lambda e: GetSoarNetworkWorkflow(e.adapter),
        "_search_soar_domains_wf": lambda e: SearchSoarDomainsWorkflow(e.adapter),
        "_get_soar_domain_wf": lambda e: GetSoarDomainWorkflow(e.adapter),
        "_search_soar_custom_lists_wf": lambda e: SearchSoarCustomListsWorkflow(e.adapter),
        "_get_soar_custom_list_wf": lambda e: GetSoarCustomListWorkflow(e.adapter),
        "_search_email_templates_wf": lambda e: SearchEmailTemplatesWorkflow(e.adapter),
        "_get_email_template_wf": lambda e: GetEmailTemplateWorkflow(e.adapter),
        "_search_entities_blocklists_wf": lambda e: SearchEntitiesBlocklistsWorkflow(e.adapter),
        "_get_entities_blocklist_wf": lambda e: GetEntitiesBlocklistWorkflow(e.adapter),
        "_search_sla_definitions_wf": lambda e: SearchSlaDefinitionsWorkflow(e.adapter),
        "_get_sla_definition_wf": lambda e: GetSlaDefinitionWorkflow(e.adapter),
        "_search_request_templates_wf": lambda e: SearchRequestTemplatesWorkflow(e.adapter),
        "_get_request_template_wf": lambda e: GetRequestTemplateWorkflow(e.adapter),
        "_search_soar_ingestion_connectors_wf": lambda e: SearchSoarIngestionConnectorsWorkflow(e.adapter),
        "_get_soar_ingestion_connector_wf": lambda e: GetSoarIngestionConnectorWorkflow(e.adapter),
        "_search_soar_webhooks_wf": lambda e: SearchSoarWebhooksWorkflow(e.adapter),
        "_get_soar_webhook_wf": lambda e: GetSoarWebhookWorkflow(e.adapter),
    }

    def __getattr__(self, name: str) -> Any:
        if name in self._WORKFLOW_MAP:
            if name not in self._wf_cache:
                self._wf_cache[name] = self._WORKFLOW_MAP[name](self)
            return self._wf_cache[name]
        raise AttributeError(f"'{type(self).__name__}' object has no attribute '{name}'")

    def _register_default_capabilities(self) -> None:
        """Registers canonical workflow capabilities."""
        self.registry.register(
            WorkflowCapability(
                capability_id="search.udm",
                name="UDM Search (End-to-End)",
                description="Validates, initiates, incrementally streams, and manages lifecycle of UDM search queries.",
                category="search",
                handler=self.search_udm,
                mcp_tool_name="search_udm",
                composed=True,
                evidence_path="evidence/search/udm",
            )
        )
        self.registry.register(
            WorkflowCapability(
                capability_id="event.investigate",
                name="Event Deep Investigation",
                description="Retrieves canonical UDM fields and raw log payload with complete provenance.",
                category="event",
                handler=self.investigate_event,
                mcp_tool_name="investigate_event",
                composed=True,
                evidence_path="evidence/event/investigate",
            )
        )
        self.registry.register(
            WorkflowCapability(
                capability_id="search.refine",
                name="Filter-Based Search Refinement",
                description="Refines existing queries by applying structured inclusion/exclusion filters on UDM paths.",
                category="search",
                handler=self.refine_search,
                mcp_tool_name="refine_search",
                composed=True,
                uses=("search.udm",),
                evidence_path="evidence/search/refine",
            )
        )
        self.registry.register(
            WorkflowCapability(
                capability_id="search.from_entity",
                name="Entity Contextual Pivot Search",
                description="Translates high-level entity artifacts into canonical UDM query expressions.",
                category="search",
                handler=self.search_from_entity,
                mcp_tool_name="search_from_entity",
                composed=True,
                uses=("search.udm",),
                evidence_path="evidence/search/from_entity",
            )
        )
        self.registry.register(
            WorkflowCapability(
                capability_id="case.investigate",
                name="SOAR Case Workspace Deep Investigation",
                description="Aggregates case metadata, security alerts, involved entities, and analyst comments.",
                category="case",
                handler=self.investigate_case,
                mcp_tool_name="investigate_case",
                composed=True,
                evidence_path="evidence/case/investigate",
            )
        )
        self.registry.register(
            WorkflowCapability(
                capability_id="case.comment",
                name="Add Case Comment Record",
                description="Adds structured analyst investigation comments to a SOAR case.",
                category="case",
                handler=self.add_case_comment,
                mcp_tool_name="add_case_comment",
                composed=False,
                evidence_path="evidence/case/comment",
            )
        )
        self.registry.register(
            WorkflowCapability(
                capability_id="alert.investigate",
                name="SOAR Security Alert Deep Investigation",
                description="Retrieves security alert details with root-cause entities and raw log attachments.",
                category="alert",
                handler=self.investigate_alert,
                mcp_tool_name="investigate_alert",
                composed=True,
                evidence_path="evidence/alert/investigate",
            )
        )
        self.registry.register(
            WorkflowCapability(
                capability_id="case.search",
                name="SOAR Case Search & Multi-Facet Filtering",
                description="Searches, lists, and filters SOAR cases across time ranges, status, priority, and stages.",
                category="case",
                handler=self.search_cases,
                mcp_tool_name="search_cases",
                composed=False,
                evidence_path="evidence/case/search",
            )
        )
        self.registry.register(
            WorkflowCapability(
                capability_id="playbook.search",
                name="SOAR Playbook Search & Discovery",
                description="Searches, lists, and filters SOAR playbooks across categories, triggers, and environments.",
                category="playbook",
                handler=self.search_playbooks,
                mcp_tool_name="search_playbooks",
                composed=False,
                evidence_path="evidence/playbook/search",
            )
        )
        self.registry.register(
            WorkflowCapability(
                capability_id="playbook.get",
                name="SOAR Playbook Deep Inspection",
                description="Retrieves complete playbook definition, trigger conditions, and step execution DAG.",
                category="playbook",
                handler=self.get_playbook,
                mcp_tool_name="get_playbook",
                composed=False,
                evidence_path="evidence/playbook/get",
            )
        )
        self.registry.register(
            WorkflowCapability(
                capability_id="playbook.categories",
                name="List Playbook Categories",
                description="Lists all SOAR Playbook folder categories.",
                category="playbook",
                handler=self.list_playbook_categories,
                mcp_tool_name="list_playbook_categories",
                composed=False,
                evidence_path="evidence/playbook/categories",
            )
        )
        self.registry.register(
            WorkflowCapability(
                capability_id="integration.search",
                name="SOAR Integration Search & Discovery",
                description="Searches, lists, and filters SOAR integrations across environments, status, and certification.",
                category="integration",
                handler=self.search_integrations,
                mcp_tool_name="search_integrations",
                composed=False,
                evidence_path="evidence/integration/search",
            )
        )
        self.registry.register(
            WorkflowCapability(
                capability_id="integration.get",
                name="SOAR Integration Deep Inspection",
                description="Retrieves complete integration details, instances, remote agents, and documentation.",
                category="integration",
                handler=self.get_integration,
                mcp_tool_name="get_integration",
                composed=False,
                evidence_path="evidence/integration/get",
            )
        )
        self.registry.register(
            WorkflowCapability(
                capability_id="integration.instances",
                name="List Integration Instances",
                description="Lists configured integration instances across environments or specific integrations.",
                category="integration",
                handler=self.list_integration_instances,
                mcp_tool_name="list_integration_instances",
                composed=False,
                evidence_path="evidence/integration/instances",
            )
        )
        self.registry.register(
            WorkflowCapability(
                capability_id="integration.remote_agents",
                name="List Remote Execution Agents",
                description="Lists remote proxy execution agents and their supported environments.",
                category="integration",
                handler=self.list_remote_agents,
                mcp_tool_name="list_remote_agents",
                composed=False,
                evidence_path="evidence/integration/remote_agents",
            )
        )
        self.registry.register(
            WorkflowCapability(
                capability_id="job.search",
                name="SOAR Scheduled Jobs Discovery",
                description="Searches, lists, and filters SOAR scheduled jobs across integrations and execution schedules.",
                category="job",
                handler=self.search_jobs,
                mcp_tool_name="search_jobs",
                composed=False,
                evidence_path="evidence/job/search",
            )
        )
        self.registry.register(
            WorkflowCapability(
                capability_id="job.get",
                name="SOAR Scheduled Job Deep Inspection",
                description="Retrieves complete job details, deployed runtime instances, and recent execution logs.",
                category="job",
                handler=self.get_job,
                mcp_tool_name="get_job",
                composed=False,
                evidence_path="evidence/job/get",
            )
        )
        self.registry.register(
            WorkflowCapability(
                capability_id="job.instances",
                name="List Job Instances",
                description="Lists runtime job instances deployed across environments or specific jobs.",
                category="job",
                handler=self.list_job_instances,
                mcp_tool_name="list_job_instances",
                composed=False,
                evidence_path="evidence/job/instances",
            )
        )
        self.registry.register(
            WorkflowCapability(
                capability_id="job.logs",
                name="Get Job Instance Execution Logs",
                description="Retrieves execution run records and output logs for a job instance.",
                category="job",
                handler=self.get_job_instance_logs,
                mcp_tool_name="get_job_instance_logs",
                composed=False,
                evidence_path="evidence/job/logs",
            )
        )
        self.registry.register(
            WorkflowCapability(
                capability_id="content_pack.search",
                name="Content Hub Content Packs Discovery",
                description="Searches, lists, and filters Content Hub Marketplace Content Packs across categories and pack types.",
                category="content_pack",
                handler=self.search_content_packs,
                mcp_tool_name="search_content_packs",
                composed=False,
                evidence_path="evidence/content_pack/search",
            )
        )
        self.registry.register(
            WorkflowCapability(
                capability_id="content_pack.get",
                name="Content Hub Content Pack Deep Inspection",
                description="Retrieves complete Content Pack details and bundled playbooks, integrations, dashboards, rulesets, and queries.",
                category="content_pack",
                handler=self.get_content_pack,
                mcp_tool_name="get_content_pack",
                composed=False,
                evidence_path="evidence/content_pack/get",
            )
        )
        self.registry.register(
            WorkflowCapability(
                capability_id="content_pack.categories",
                name="Content Hub Categories Taxonomy",
                description="Discovers and aggregates the taxonomy of Content Hub categories with pack counts.",
                category="content_pack",
                handler=self.list_content_pack_categories,
                mcp_tool_name="list_content_pack_categories",
                composed=False,
                evidence_path="evidence/content_pack/categories",
            )
        )
        self.registry.register(
            WorkflowCapability(
                capability_id="curated_detections.search_rulesets",
                name="Search Curated Rule Sets",
                description="Discovers and searches Google SecOps Curated Rule Sets with MITRE ATT&CK mappings and log sources.",
                category="curated_detections",
                handler=self.search_curated_rulesets,
                mcp_tool_name="search_curated_rulesets",
                composed=False,
                evidence_path="evidence/curated_detections/rulesets",
            )
        )
        self.registry.register(
            WorkflowCapability(
                capability_id="curated_detections.get_ruleset",
                name="Curated Rule Set Deep Inspection",
                description="Deep-inspects a Curated Rule Set, its broad/precise deployments, member rules, and detection telemetry.",
                category="curated_detections",
                handler=self.get_curated_ruleset,
                mcp_tool_name="get_curated_ruleset",
                composed=False,
                evidence_path="evidence/curated_detections/ruleset_get",
            )
        )
        self.registry.register(
            WorkflowCapability(
                capability_id="curated_detections.get_rule",
                name="Curated Rule YARA-L Inspection",
                description="Retrieves an individual Curated Rule, its MITRE techniques, false positives, and raw YARA-L logic.",
                category="curated_detections",
                handler=self.get_curated_rule,
                mcp_tool_name="get_curated_rule",
                composed=False,
                evidence_path="evidence/curated_detections/rule_get",
            )
        )
        self.registry.register(
            WorkflowCapability(
                capability_id="curated_detections.metrics",
                name="Curated Detection Metrics & Quotas",
                description="Aggregates detection firing counts and retrieves tenant-wide rule quotas and telemetry.",
                category="curated_detections",
                handler=self.get_curated_detection_metrics,
                mcp_tool_name="get_curated_detection_metrics",
                composed=False,
                evidence_path="evidence/curated_detections/metrics",
            )
        )
        self.registry.register(
            WorkflowCapability(
                capability_id="marketplace_integration.search",
                name="Search Marketplace Response Integrations",
                description="Discovers, searches, and filters Marketplace Response Integrations across categories and update states.",
                category="marketplace_integration",
                handler=self.search_marketplace_integrations,
                mcp_tool_name="search_marketplace_integrations",
                composed=False,
                evidence_path="evidence/marketplace_integration/search",
            )
        )
        self.registry.register(
            WorkflowCapability(
                capability_id="marketplace_integration.get",
                name="Marketplace Response Integration Deep Inspection",
                description="Retrieves complete integration composite, actions, connectors, jobs, managers, and release notes.",
                category="marketplace_integration",
                handler=self.get_marketplace_integration,
                mcp_tool_name="get_marketplace_integration",
                composed=False,
                evidence_path="evidence/marketplace_integration/get",
            )
        )
        self.registry.register(
            WorkflowCapability(
                capability_id="marketplace_integration.diff",
                name="Marketplace Commercial Version Diff",
                description="Compares commercial upgrade differences and overrides between installed and target versions.",
                category="marketplace_integration",
                handler=self.get_marketplace_integration_diff,
                mcp_tool_name="get_marketplace_integration_diff",
                composed=False,
                evidence_path="evidence/marketplace_integration/diff",
            )
        )
        self.registry.register(
            WorkflowCapability(
                capability_id="marketplace_integration.affected_items",
                name="Marketplace Downstream Affected Items",
                description="Resolves affected environment instances and active playbooks before integration modifications.",
                category="marketplace_integration",
                handler=self.get_marketplace_integration_affected_items,
                mcp_tool_name="get_marketplace_integration_affected_items",
                composed=False,
                evidence_path="evidence/marketplace_integration/affected_items",
            )
        )
        self.registry.register(
            WorkflowCapability(
                capability_id="dashboard.search",
                name="Google SecOps Native Dashboards Discovery",
                description="Searches, lists, and filters native dashboards configured in Google SecOps.",
                category="dashboard",
                handler=self.search_dashboards,
                mcp_tool_name="search_dashboards",
                composed=False,
                evidence_path="evidence/dashboard/search",
            )
        )
        self.registry.register(
            WorkflowCapability(
                capability_id="dashboard.get",
                name="Google SecOps Dashboard Deep Inspection",
                description="Retrieves complete composite dashboard graph with layout, batch-resolved charts, and queries.",
                category="dashboard",
                handler=self.get_dashboard,
                mcp_tool_name="get_dashboard",
                composed=True,
                evidence_path="evidence/dashboard/get",
            )
        )
        self.registry.register(
            WorkflowCapability(
                capability_id="dashboard.execute_query",
                name="Google SecOps Dashboard Query Execution",
                description="Executes a dashboard widget query against live telemetry and transforms columnar results into tabular records.",
                category="dashboard",
                handler=self.execute_dashboard_query,
                mcp_tool_name="execute_dashboard_query",
                composed=False,
                evidence_path="evidence/dashboard/execute_query",
            )
        )
        self.registry.register(
            WorkflowCapability(
                capability_id="dashboard.validate_query",
                name="Google SecOps Dashboard Query Validation",
                description="Validates statistical / dashboard widget query syntax against the live Google SecOps query compiler.",
                category="dashboard",
                handler=self.validate_dashboard_query,
                mcp_tool_name="validate_dashboard_query",
                composed=False,
                evidence_path="evidence/dashboard/validate_query",
            )
        )
        self.registry.register(
            WorkflowCapability(
                capability_id="siem.managed_domains.get",
                name="Get Managed Email Domains Settings",
                description="Retrieves approved email domains for report deliveries and alerts.",
                category="siem_settings",
                handler=self.get_managed_domain_settings,
                mcp_tool_name="get_managed_domain_settings",
                composed=False,
                evidence_path="evidence/siem_settings/managed_domains",
            )
        )
        self.registry.register(
            WorkflowCapability(
                capability_id="feed.search",
                name="Search Ingestion Feeds",
                description="Searches, lists, and filters push/pull ingestion feeds across source types and log types.",
                category="feed",
                handler=self.search_feeds,
                mcp_tool_name="search_feeds",
                composed=False,
                evidence_path="evidence/feed/search",
            )
        )
        self.registry.register(
            WorkflowCapability(
                capability_id="feed.get",
                name="Feed Deep Inspection",
                description="Retrieves full configuration details and source parameters for an ingestion feed.",
                category="feed",
                handler=self.get_feed,
                mcp_tool_name="get_feed",
                composed=False,
                evidence_path="evidence/feed/get",
            )
        )
        self.registry.register(
            WorkflowCapability(
                capability_id="pipeline.search",
                name="Search Log Processing Pipelines",
                description="Discovers and lists Data Processing Pipelines with parser transforms and Bindplane SaaS links.",
                category="siem_settings",
                handler=self.search_log_processing_pipelines,
                mcp_tool_name="search_log_processing_pipelines",
                composed=False,
                evidence_path="evidence/siem_settings/pipelines/search",
            )
        )
        self.registry.register(
            WorkflowCapability(
                capability_id="pipeline.get",
                name="Log Processing Pipeline Deep Inspection",
                description="Retrieves full transform statements and stream bindings for a Data Processing Pipeline.",
                category="siem_settings",
                handler=self.get_log_processing_pipeline,
                mcp_tool_name="get_log_processing_pipeline",
                composed=False,
                evidence_path="evidence/siem_settings/pipelines/get",
            )
        )
        self.registry.register(
            WorkflowCapability(
                capability_id="feed_schema.list_sources",
                name="List Feed Source Type Schemas",
                description="Lists all supported feed source types and collection mechanisms.",
                category="feed",
                handler=self.list_feed_source_type_schemas,
                mcp_tool_name="list_feed_source_type_schemas",
                composed=False,
                evidence_path="evidence/feed/schemas/sources",
            )
        )
        self.registry.register(
            WorkflowCapability(
                capability_id="feed_schema.list_log_types",
                name="List Feed Log Type Schemas",
                description="Lists log types supported by a specific feed source with lean payload handling.",
                category="feed",
                handler=self.list_feed_log_type_schemas,
                mcp_tool_name="list_feed_log_type_schemas",
                composed=False,
                evidence_path="evidence/feed/schemas/log_types",
            )
        )
        self.registry.register(
            WorkflowCapability(
                capability_id="parser.log_types.list",
                name="List Supported Log Types",
                description="Discovers and filters supported ingestion log types cataloged in Google SecOps.",
                category="parser",
                handler=self.list_log_types,
                mcp_tool_name="list_log_types",
                composed=False,
                evidence_path="evidence/parser/log_types",
            )
        )
        self.registry.register(
            WorkflowCapability(
                capability_id="parser.search",
                name="Search Ingestion Parsers",
                description="Discovers and filters parsers across log types with creator and state filters.",
                category="parser",
                handler=self.search_parsers,
                mcp_tool_name="search_parsers",
                composed=False,
                evidence_path="evidence/parser/search",
            )
        )
        self.registry.register(
            WorkflowCapability(
                capability_id="parser.get",
                name="Parser Deep Inspection",
                description="Retrieves complete parser metadata and decoded Logstash CBN filter code.",
                category="parser",
                handler=self.get_parser,
                mcp_tool_name="get_parser",
                composed=False,
                evidence_path="evidence/parser/get",
            )
        )
        self.registry.register(
            WorkflowCapability(
                capability_id="parser.extensions.search",
                name="Search Parser Extensions",
                description="Discovers parser extensions and dynamic parsing configurations across log types.",
                category="parser",
                handler=self.search_parser_extensions,
                mcp_tool_name="search_parser_extensions",
                composed=False,
                evidence_path="evidence/parser/extensions/search",
            )
        )
        self.registry.register(
            WorkflowCapability(
                capability_id="parser.extensions.get",
                name="Parser Extension Deep Inspection",
                description="Retrieves full parser extension configuration, decoded snippet, and test log.",
                category="parser",
                handler=self.get_parser_extension,
                mcp_tool_name="get_parser_extension",
                composed=False,
                evidence_path="evidence/parser/extensions/get",
            )
        )
        self.registry.register(
            WorkflowCapability(
                capability_id="parser.log_type_setting.get",
                name="Get Parser Log Type Setting",
                description="Retrieves autonomous parsing settings and extraction type for a specific log type.",
                category="parser",
                handler=self.get_log_type_setting,
                mcp_tool_name="get_log_type_setting",
                composed=False,
                evidence_path="evidence/parser/settings",
            )
        )
        self.registry.register(
            WorkflowCapability(
                capability_id="preview_feature.list",
                name="List Preview Features",
                description="Discovers customer preview feature flags, enablement states, retirement schedules, and docs.",
                category="preview_feature",
                handler=self.list_preview_features,
                mcp_tool_name="list_preview_features",
                composed=False,
                evidence_path="evidence/preview_feature/list",
            )
        )
        self.registry.register(
            WorkflowCapability(
                capability_id="preview_feature.get",
                name="Get Preview Feature Deep Inspection",
                description="Retrieves specific preview feature configuration, documentation, and retirement dates.",
                category="preview_feature",
                handler=self.get_preview_feature,
                mcp_tool_name="get_preview_feature",
                composed=False,
                evidence_path="evidence/preview_feature/get",
            )
        )
        self.registry.register(
            WorkflowCapability(
                capability_id="data_rbac.scope.search",
                name="Search Data Access Scopes",
                description="Discovers and filters Data Access RBAC Scopes and allow/deny label counts.",
                category="data_rbac",
                handler=self.search_data_access_scopes,
                mcp_tool_name="search_data_access_scopes",
                composed=False,
                evidence_path="evidence/data_rbac/scope/search",
            )
        )
        self.registry.register(
            WorkflowCapability(
                capability_id="data_rbac.scope.get",
                name="Data Access Scope Deep Inspection",
                description="Retrieves deep configuration of a Data Access Scope including label attachments.",
                category="data_rbac",
                handler=self.get_data_access_scope,
                mcp_tool_name="get_data_access_scope",
                composed=False,
                evidence_path="evidence/data_rbac/scope/get",
            )
        )
        self.registry.register(
            WorkflowCapability(
                capability_id="data_rbac.label.search",
                name="Search Data Access Labels",
                description="Discovers Data Access Labels and their associated UDM filter query definitions.",
                category="data_rbac",
                handler=self.search_data_access_labels,
                mcp_tool_name="search_data_access_labels",
                composed=False,
                evidence_path="evidence/data_rbac/label/search",
            )
        )
        self.registry.register(
            WorkflowCapability(
                capability_id="data_rbac.label.get",
                name="Data Access Label Deep Inspection",
                description="Retrieves full configuration of a Data Access Label including UDM filter expression.",
                category="data_rbac",
                handler=self.get_data_access_label,
                mcp_tool_name="get_data_access_label",
                composed=False,
                evidence_path="evidence/data_rbac/label/get",
            )
        )
        self.registry.register(
            WorkflowCapability(
                capability_id="data_rbac.environment.search",
                name="Search SOAR Environments and Scopes",
                description="Discovers SOAR multi-tenant environments and inspects their bound Data Access Scopes.",
                category="data_rbac",
                handler=self.search_environment_scopes,
                mcp_tool_name="search_environment_scopes",
                composed=False,
                evidence_path="evidence/data_rbac/environment/search",
            )
        )
        self.registry.register(
            WorkflowCapability(
                capability_id="enrichment.combination.list",
                name="List Enrichment Combinations",
                description="Discovers available enrichment types, target log types, and enrichment sources.",
                category="enrichment",
                handler=self.list_enrichment_combinations,
                mcp_tool_name="list_enrichment_combinations",
                composed=False,
                evidence_path="evidence/enrichment/combination/list",
            )
        )
        self.registry.register(
            WorkflowCapability(
                capability_id="enrichment.control.search",
                name="Search Deployed Enrichment Controls",
                description="Discovers and filters deployed enrichment controls that restrict entity enrichments.",
                category="enrichment",
                handler=self.search_enrichment_controls,
                mcp_tool_name="search_enrichment_controls",
                composed=False,
                evidence_path="evidence/enrichment/control/search",
            )
        )
        self.registry.register(
            WorkflowCapability(
                capability_id="enrichment.control.get",
                name="Enrichment Control Deep Inspection",
                description="Retrieves full configuration and timing rules for a deployed enrichment control.",
                category="enrichment",
                handler=self.get_enrichment_control,
                mcp_tool_name="get_enrichment_control",
                composed=False,
                evidence_path="evidence/enrichment/control/get",
            )
        )
        self.registry.register(
            WorkflowCapability(
                capability_id="siem.agent_settings.get",
                name="Get Gemini Triage & Investigation Agent Settings",
                description="Retrieves tenant configuration for automated triage, investigation filters, delays, and quotas.",
                category="siem_settings",
                handler=self.get_agent_settings,
                mcp_tool_name="get_agent_settings",
                composed=False,
                evidence_path="evidence/siem_settings/agent_settings/get",
            )
        )
        self.registry.register(
            WorkflowCapability(
                capability_id="siem.risk_config.get",
                name="Get Entity Risk Scoring Configuration",
                description="Retrieves UEBA entity risk scoring defaults, detection/alert scores, and weighting coefficients.",
                category="siem_settings",
                handler=self.get_entity_risk_config,
                mcp_tool_name="get_entity_risk_config",
                composed=False,
                evidence_path="evidence/siem_settings/risk_config/get",
            )
        )
        self.registry.register(
            WorkflowCapability(
                capability_id="siem.tenant.get",
                name="Get Tenant Instance Details",
                description="Retrieves root tenant instance details, active URLs, feature flags, and workforce pool providers.",
                category="siem_settings",
                handler=self.get_tenant_instance,
                mcp_tool_name="get_tenant_instance",
                composed=False,
                evidence_path="evidence/siem_settings/tenant/get",
            )
        )
        self.registry.register(
            WorkflowCapability(
                capability_id="soar.user.search",
                name="Search SOAR Users",
                description="Discovers and filters SOAR users and external identity profiles.",
                category="soar_settings",
                handler=self.search_soar_users,
                mcp_tool_name="search_soar_users",
                composed=False,
                evidence_path="evidence/soar_settings/users/search",
            )
        )
        self.registry.register(
            WorkflowCapability(
                capability_id="soar.user.get",
                name="Get SOAR User Details",
                description="Retrieves deep profile details of a single SOAR user including roles, permission groups, and environment access.",
                category="soar_settings",
                handler=self.get_soar_user,
                mcp_tool_name="get_soar_user",
                composed=False,
                evidence_path="evidence/soar_settings/users/get",
            )
        )
        self.registry.register(
            WorkflowCapability(
                capability_id="soar.soc_role.list",
                name="List SOC Roles",
                description="Lists configured SOC roles and workflow assignment access hierarchy.",
                category="soar_settings",
                handler=self.list_soc_roles,
                mcp_tool_name="list_soc_roles",
                composed=False,
                evidence_path="evidence/soar_settings/soc_roles/list",
            )
        )
        self.registry.register(
            WorkflowCapability(
                capability_id="soar.company.get",
                name="Get Company Rebranding Settings",
                description="Retrieves tenant branding, report customizations, and system email settings.",
                category="soar_settings",
                handler=self.get_company_settings,
                mcp_tool_name="get_company_settings",
                composed=False,
                evidence_path="evidence/soar_settings/company/get",
            )
        )
        self.registry.register(
            WorkflowCapability(
                capability_id="case_config.tag.search",
                name="Search Case Tag Definitions",
                description="Discovers and filters case tag classification rules and criteria.",
                category="case_config",
                handler=self.search_case_tag_definitions,
                mcp_tool_name="search_case_tag_definitions",
                composed=False,
                evidence_path="evidence/case_config/tags/search",
            )
        )
        self.registry.register(
            WorkflowCapability(
                capability_id="case_config.stage.list",
                name="List Case Stage Definitions",
                description="Lists ordered SOC case lifecycle pipeline stages.",
                category="case_config",
                handler=self.list_case_stage_definitions,
                mcp_tool_name="list_case_stage_definitions",
                composed=False,
                evidence_path="evidence/case_config/stages/list",
            )
        )
        self.registry.register(
            WorkflowCapability(
                capability_id="case_config.close_definition.list",
                name="List Case Close Definitions",
                description="Catalogs predefined close reasons and root causes for closing cases.",
                category="case_config",
                handler=self.list_case_close_definitions,
                mcp_tool_name="list_case_close_definitions",
                composed=False,
                evidence_path="evidence/case_config/close_definitions/list",
            )
        )
        self.registry.register(
            WorkflowCapability(
                capability_id="case_config.close_parameter.list",
                name="List Case Close Dynamic Parameters",
                description="Discovers dynamic form fields and custom field schemas required when closing cases.",
                category="case_config",
                handler=self.list_case_close_dynamic_parameters,
                mcp_tool_name="list_case_close_dynamic_parameters",
                composed=False,
                evidence_path="evidence/case_config/close_parameters/list",
            )
        )
        self.registry.register(
            WorkflowCapability(
                capability_id="case_config.title_settings.get",
                name="Get Case Title Naming Rules",
                description="Retrieves priority rules for automated SOAR case naming.",
                category="case_config",
                handler=self.get_case_title_settings,
                mcp_tool_name="get_case_title_settings",
                composed=False,
                evidence_path="evidence/case_config/title_settings/get",
            )
        )
        self.registry.register(
            WorkflowCapability(
                capability_id="case_config.view.search",
                name="Search Case and Alert Views",
                description="Discovers and filters layout view templates for Cases, Alerts, and Detections.",
                category="case_config",
                handler=self.search_case_views,
                mcp_tool_name="search_case_views",
                composed=False,
                evidence_path="evidence/case_config/views/search",
            )
        )
        self.registry.register(
            WorkflowCapability(
                capability_id="case_config.view.get",
                name="Case View Deep Inspection",
                description="Retrieves deep inspection of a specific view layout template and widget hierarchy.",
                category="case_config",
                handler=self.get_case_view,
                mcp_tool_name="get_case_view",
                composed=False,
                evidence_path="evidence/case_config/views/get",
            )
        )
        self.registry.register(
            WorkflowCapability(
                capability_id="case_config.custom_field.search",
                name="Search Custom Fields",
                description="Lists and filters custom typed fields across Case and Alert scopes.",
                category="case_config",
                handler=self.search_custom_fields,
                mcp_tool_name="search_custom_fields",
                composed=False,
                evidence_path="evidence/case_config/custom_fields/search",
            )
        )
        self.registry.register(
            WorkflowCapability(
                capability_id="case_config.custom_field.get",
                name="Custom Field Deep Inspection",
                description="Retrieves deep inspection of a single custom field definition and ordered option values.",
                category="case_config",
                handler=self.get_custom_field,
                mcp_tool_name="get_custom_field",
                composed=False,
                evidence_path="evidence/case_config/custom_fields/get",
            )
        )
        self.registry.register(
            WorkflowCapability(
                capability_id="case_config.calculated_field.search",
                name="Search Calculated Fields",
                description="Lists and filters calculated field formula definitions.",
                category="case_config",
                handler=self.search_calculated_fields,
                mcp_tool_name="search_calculated_fields",
                composed=False,
                evidence_path="evidence/case_config/calculated_fields/search",
            )
        )
        self.registry.register(
            WorkflowCapability(
                capability_id="case_config.calculated_field.get",
                name="Calculated Field Deep Inspection",
                description="Retrieves deep inspection of a single calculated field definition.",
                category="case_config",
                handler=self.get_calculated_field,
                mcp_tool_name="get_calculated_field",
                composed=False,
                evidence_path="evidence/case_config/calculated_fields/get",
            )
        )
        self.registry.register(
            WorkflowCapability(
                capability_id="case_config.alert_grouping.rule.search",
                name="Search Alert Grouping Rules",
                description="Discovers and filters SOAR alert grouping rules determining case clustering.",
                category="case_config",
                handler=self.search_alert_grouping_rules,
                mcp_tool_name="search_alert_grouping_rules",
                composed=False,
                evidence_path="evidence/case_config/alert_grouping/rules/search",
            )
        )
        self.registry.register(
            WorkflowCapability(
                capability_id="case_config.alert_grouping.rule.get",
                name="Alert Grouping Rule Deep Inspection",
                description="Retrieves deep inspection of a single alert grouping rule including entity types and category details.",
                category="case_config",
                handler=self.get_alert_grouping_rule,
                mcp_tool_name="get_alert_grouping_rule",
                composed=False,
                evidence_path="evidence/case_config/alert_grouping/rules/get",
            )
        )
        self.registry.register(
            WorkflowCapability(
                capability_id="case_config.alert_grouping.settings.get",
                name="Get Alert Grouping Global Settings",
                description="Retrieves global SOAR alert grouping configuration parameters including timeframes and algorithms.",
                category="case_config",
                handler=self.get_alert_grouping_settings,
                mcp_tool_name="get_alert_grouping_settings",
                composed=False,
                evidence_path="evidence/case_config/alert_grouping/settings/get",
            )
        )
        self.registry.register(
            WorkflowCapability(
                capability_id="soar.data_retention.get",
                name="Get Data Retention Settings",
                description="Retrieves SOAR data retention configuration and per-environment policy settings.",
                category="soar_settings",
                handler=self.get_data_retention_settings,
                mcp_tool_name="get_data_retention_settings",
                composed=False,
                evidence_path="evidence/soar_settings/data_retention/get",
            )
        )
        self.registry.register(
            WorkflowCapability(
                capability_id="soar.environment.search",
                name="Search Multi-Tenancy Environments",
                description="Discovers and filters multi-tenancy environment boundaries within the SOAR tenant.",
                category="soar_settings",
                handler=self.search_environments,
                mcp_tool_name="search_environments",
                composed=False,
                evidence_path="evidence/soar_settings/environments/search",
            )
        )
        self.registry.register(
            WorkflowCapability(
                capability_id="soar.environment.get",
                name="Environment Deep Inspection",
                description="Retrieves deep configuration details of a single multi-tenancy environment.",
                category="soar_settings",
                handler=self.get_environment,
                mcp_tool_name="get_environment",
                composed=False,
                evidence_path="evidence/soar_settings/environments/get",
            )
        )
        self.registry.register(
            WorkflowCapability(
                capability_id="soar.environment_group.search",
                name="Search Environment Groups",
                description="Discovers and lists logical groupings of multi-tenancy environments.",
                category="soar_settings",
                handler=self.search_environment_groups,
                mcp_tool_name="search_environment_groups",
                composed=False,
                evidence_path="evidence/soar_settings/environment_groups/search",
            )
        )
        self.registry.register(
            WorkflowCapability(
                capability_id="soar.remote_agent.search",
                name="Search Remote SOAR Agents",
                description="Discovers and filters remote execution agents, bindings, and active health states.",
                category="soar_settings",
                handler=self.search_remote_agents,
                mcp_tool_name="search_remote_agents",
                composed=False,
                evidence_path="evidence/soar_settings/remote_agents/search",
            )
        )
        self.registry.register(
            WorkflowCapability(
                capability_id="soar.remote_agent.get",
                name="Remote SOAR Agent Deep Inspection",
                description="Retrieves deep configuration of a remote agent including certificates and installer links.",
                category="soar_settings",
                handler=self.get_remote_agent,
                mcp_tool_name="get_remote_agent",
                composed=False,
                evidence_path="evidence/soar_settings/remote_agents/get",
            )
        )
        self.registry.register(
            WorkflowCapability(
                capability_id="soar.email_settings.get",
                name="Get SOAR Email Transport Settings",
                description="Retrieves composite email transport configuration combining custom SMTP and Google defaults.",
                category="soar_settings",
                handler=self.get_email_settings,
                mcp_tool_name="get_email_settings",
                composed=False,
                evidence_path="evidence/soar_settings/email_settings/get",
            )
        )
        self.registry.register(
            WorkflowCapability(
                capability_id="soar.support_settings.get",
                name="Get Google Support Access Settings",
                description="Retrieves Google Support access delegation parameters including roles, environments, and expiry.",
                category="soar_settings",
                handler=self.get_support_settings,
                mcp_tool_name="get_support_settings",
                composed=False,
                evidence_path="evidence/soar_settings/support_settings/get",
            )
        )
        self.registry.register(
            WorkflowCapability(
                capability_id="soar.network.search",
                name="Search SOAR Networks",
                description="Discovers and filters customer-defined CIDR network address ranges and environment mappings.",
                category="soar_settings",
                handler=self.search_soar_networks,
                mcp_tool_name="search_soar_networks",
                composed=False,
                evidence_path="evidence/soar_settings/networks/search",
            )
        )
        self.registry.register(
            WorkflowCapability(
                capability_id="soar.network.get",
                name="SOAR Network Deep Inspection",
                description="Retrieves complete configuration for a single customer-defined CIDR network.",
                category="soar_settings",
                handler=self.get_soar_network,
                mcp_tool_name="get_soar_network",
                composed=False,
                evidence_path="evidence/soar_settings/networks/get",
            )
        )
        self.registry.register(
            WorkflowCapability(
                capability_id="soar.domain.search",
                name="Search SOAR Domains",
                description="Discovers and filters customer-approved domain names and environment mappings.",
                category="soar_settings",
                handler=self.search_soar_domains,
                mcp_tool_name="search_soar_domains",
                composed=False,
                evidence_path="evidence/soar_settings/domains/search",
            )
        )
        self.registry.register(
            WorkflowCapability(
                capability_id="soar.domain.get",
                name="SOAR Domain Deep Inspection",
                description="Retrieves complete configuration for a single approved customer domain.",
                category="soar_settings",
                handler=self.get_soar_domain,
                mcp_tool_name="get_soar_domain",
                composed=False,
                evidence_path="evidence/soar_settings/domains/get",
            )
        )
        self.registry.register(
            WorkflowCapability(
                capability_id="soar.custom_list.search",
                name="Search SOAR Custom Lists",
                description="Discovers and filters SOAR custom key-value style retention lists by query, category, and environment.",
                category="soar_settings",
                handler=self.search_soar_custom_lists,
                mcp_tool_name="search_soar_custom_lists",
                composed=False,
                evidence_path="evidence/soar_settings/custom_lists/search",
            )
        )
        self.registry.register(
            WorkflowCapability(
                capability_id="soar.custom_list.get",
                name="SOAR Custom List Deep Inspection",
                description="Retrieves complete configuration for a single SOAR custom list record.",
                category="soar_settings",
                handler=self.get_soar_custom_list,
                mcp_tool_name="get_soar_custom_list",
                composed=False,
                evidence_path="evidence/soar_settings/custom_lists/get",
            )
        )
        self.registry.register(
            WorkflowCapability(
                capability_id="soar.email_template.search",
                name="Search Email Templates",
                description="Discovers and filters plain text and HTML email templates used in SOAR playbooks.",
                category="soar_settings",
                handler=self.search_email_templates,
                mcp_tool_name="search_email_templates",
                composed=False,
                evidence_path="evidence/soar_settings/email_templates/search",
            )
        )
        self.registry.register(
            WorkflowCapability(
                capability_id="soar.email_template.get",
                name="Email Template Deep Inspection",
                description="Retrieves complete email template definition including markup and body content.",
                category="soar_settings",
                handler=self.get_email_template,
                mcp_tool_name="get_email_template",
                composed=False,
                evidence_path="evidence/soar_settings/email_templates/get",
            )
        )
        self.registry.register(
            WorkflowCapability(
                capability_id="soar.entities_blocklist.search",
                name="Search Entities Blocklist",
                description="Discovers and filters entity extraction noise-reduction blocklists.",
                category="soar_settings",
                handler=self.search_entities_blocklists,
                mcp_tool_name="search_entities_blocklists",
                composed=False,
                evidence_path="evidence/soar_settings/entities_blocklists/search",
            )
        )
        self.registry.register(
            WorkflowCapability(
                capability_id="soar.entities_blocklist.get",
                name="Entities Blocklist Deep Inspection",
                description="Retrieves complete configuration for a single entity blocklist entry.",
                category="soar_settings",
                handler=self.get_entities_blocklist,
                mcp_tool_name="get_entities_blocklist",
                composed=False,
                evidence_path="evidence/soar_settings/entities_blocklists/get",
            )
        )
        self.registry.register(
            WorkflowCapability(
                capability_id="soar.sla_definition.search",
                name="Search SLA Definitions",
                description="Discovers and filters Service Level Agreement definitions across stages and priorities.",
                category="soar_settings",
                handler=self.search_sla_definitions,
                mcp_tool_name="search_sla_definitions",
                composed=False,
                evidence_path="evidence/soar_settings/sla_definitions/search",
            )
        )
        self.registry.register(
            WorkflowCapability(
                capability_id="soar.sla_definition.get",
                name="SLA Definition Deep Inspection",
                description="Retrieves complete SLA parameters for a single SLA rule.",
                category="soar_settings",
                handler=self.get_sla_definition,
                mcp_tool_name="get_sla_definition",
                composed=False,
                evidence_path="evidence/soar_settings/sla_definitions/get",
            )
        )
        self.registry.register(
            WorkflowCapability(
                capability_id="soar.request_template.search",
                name="Search Request Templates",
                description="Discovers and filters SOAR manual case request form templates.",
                category="soar_settings",
                handler=self.search_request_templates,
                mcp_tool_name="search_request_templates",
                composed=False,
                evidence_path="evidence/soar_settings/request_templates/search",
            )
        )
        self.registry.register(
            WorkflowCapability(
                capability_id="soar.request_template.get",
                name="Request Template Deep Inspection",
                description="Retrieves complete form field definitions and options for a single request template.",
                category="soar_settings",
                handler=self.get_request_template,
                mcp_tool_name="get_request_template",
                composed=False,
                evidence_path="evidence/soar_settings/request_templates/get",
            )
        )
        self.registry.register(
            WorkflowCapability(
                capability_id="soar.ingestion_connector.search",
                name="Search Ingestion Connectors",
                description="Discovers and filters configured SOAR ingestion connector instances across integrations.",
                category="soar_settings",
                handler=self.search_soar_ingestion_connectors,
                mcp_tool_name="search_soar_ingestion_connectors",
                composed=False,
                evidence_path="evidence/soar_settings/ingestion_connectors/search",
            )
        )
        self.registry.register(
            WorkflowCapability(
                capability_id="soar.ingestion_connector.get",
                name="Ingestion Connector Deep Inspection",
                description="Retrieves complete configuration for a single SOAR ingestion connector instance.",
                category="soar_settings",
                handler=self.get_soar_ingestion_connector,
                mcp_tool_name="get_soar_ingestion_connector",
                composed=False,
                evidence_path="evidence/soar_settings/ingestion_connectors/get",
            )
        )
        self.registry.register(
            WorkflowCapability(
                capability_id="soar.webhook.search",
                name="Search SOAR Webhooks",
                description="Discovers and filters configured SOAR event ingestion webhooks.",
                category="soar_settings",
                handler=self.search_soar_webhooks,
                mcp_tool_name="search_soar_webhooks",
                composed=False,
                evidence_path="evidence/soar_settings/webhooks/search",
            )
        )
        self.registry.register(
            WorkflowCapability(
                capability_id="soar.webhook.get",
                name="SOAR Webhook Deep Inspection",
                description="Retrieves complete configuration and schema mapping for a single SOAR event ingestion webhook.",
                category="soar_settings",
                handler=self.get_soar_webhook,
                mcp_tool_name="get_soar_webhook",
                composed=False,
                evidence_path="evidence/soar_settings/webhooks/get",
            )
        )





    def search_udm(
        self,
        request: SearchRequest,
        on_batch: Optional[Callable[[SearchBatchResult, SearchSession], None]] = None,
        on_state_change: Optional[Callable[[SearchSession], None]] = None,
        cancel_token: Optional[Callable[[], bool]] = None,
    ) -> SearchSession:
        """Executes the canonical UDM Search workflow."""
        return self._search_udm_wf.execute(
            request=request,
            on_batch=on_batch,
            on_state_change=on_state_change,
            cancel_token=cancel_token,
        )

    def investigate_event(
        self,
        event_ref: Union[EventReference, Dict[str, Any], str],
        eager_load_raw_log: bool = False,
    ) -> EventInvestigation:
        """Executes the Event Investigation workflow."""
        return self._investigate_event_wf.execute(
            event_ref=event_ref,
            eager_load_raw_log=eager_load_raw_log,
        )

    def refine_search(
        self,
        base: Union[str, SearchSession],
        filters: List[FieldFilter],
        start_time: Optional[str] = None,
        end_time: Optional[str] = None,
        receive_limit: int = 10000,
        batch_size: int = 2000,
        parent_event_id: Optional[str] = None,
        on_batch: Optional[Callable[[SearchBatchResult, SearchSession], None]] = None,
        on_state_change: Optional[Callable[[SearchSession], None]] = None,
        cancel_token: Optional[Callable[[], bool]] = None,
    ) -> SearchSession:
        """Executes the Search Refinement workflow."""
        return self._refine_search_wf.execute(
            base=base,
            filters=filters,
            start_time=start_time,
            end_time=end_time,
            receive_limit=receive_limit,
            batch_size=batch_size,
            parent_event_id=parent_event_id,
            on_batch=on_batch,
            on_state_change=on_state_change,
            cancel_token=cancel_token,
        )

    def search_from_entity(
        self,
        entity_type: EntityType,
        entity_value: str,
        start_time: str,
        end_time: str,
        receive_limit: int = 10000,
        batch_size: int = 2000,
        on_batch: Optional[Callable[[SearchBatchResult, SearchSession], None]] = None,
        on_state_change: Optional[Callable[[SearchSession], None]] = None,
        cancel_token: Optional[Callable[[], bool]] = None,
    ) -> SearchSession:
        """Executes a canonical entity pivot search workflow."""
        return self._search_from_entity_wf.execute(
            entity_type=entity_type,
            entity_value=entity_value,
            start_time=start_time,
            end_time=end_time,
            receive_limit=receive_limit,
            batch_size=batch_size,
            on_batch=on_batch,
            on_state_change=on_state_change,
            cancel_token=cancel_token,
        )

    def investigate_case(self, case_id: str) -> CaseInvestigation:
        """Executes the Case Investigation Workspace workflow."""
        return self._investigate_case_wf.execute(case_id=case_id)

    def add_case_comment(self, case_id: str, comment: str) -> CaseCommentRecord:
        """Executes the Add Case Comment workflow."""
        return self._add_case_comment_wf.execute(case_id=case_id, comment=comment)

    def investigate_alert(self, alert_name: str) -> AlertInvestigation:
        """Executes the Alert Deep-Dive Investigation workflow."""
        return self._investigate_alert_wf.execute(alert_name=alert_name)

    def search_cases(
        self,
        query: Union[CaseSearchQuery, str] = "",
        start_time: Optional[Any] = None,
        end_time: Optional[Any] = None,
        tags: Optional[List[str]] = None,
        priorities: Optional[List[str]] = None,
        stages: Optional[List[str]] = None,
        environments: Optional[List[str]] = None,
        assigned_users: Optional[List[str]] = None,
        is_important: Optional[bool] = None,
        page_size: int = 50,
        page_number: int = 0,
    ) -> CaseSearchBatch:
        """Executes the SOAR Case Search workflow."""
        if isinstance(query, CaseSearchQuery):
            return self._search_cases_wf.execute(query)
        q = CaseSearchQuery(
            query_text=query,
            start_time=start_time,
            end_time=end_time,
            tags=tags or [],
            priorities=priorities or [],
            stages=stages or [],
            environments=environments or [],
            assigned_users=assigned_users or [],
            is_important=is_important,
            page_size=page_size,
            page_number=page_number,
        )
        return self._search_cases_wf.execute(q)

    def get_case_filter_values(
        self,
        filter_type: str,
        search_term: str = "",
        limit: int = 20,
    ) -> List[str]:
        """Retrieves facet filter suggestions for cases."""
        return self.adapter.get_case_filter_values(
            filter_type=filter_type,
            search_term=search_term,
            limit=limit,
        )

    def search_playbooks(
        self,
        query: Optional[Union[str, PlaybookSearchQuery]] = None,
        category: Optional[str] = None,
        is_enabled: Optional[bool] = None,
        playbook_type: Optional[PlaybookType] = None,
        environment: Optional[str] = None,
        limit: int = 100,
    ) -> PlaybookBatch:
        """Executes the SOAR Playbook Search & Filter workflow."""
        if isinstance(query, PlaybookSearchQuery):
            return self._search_playbooks_wf.execute(query)
        q = PlaybookSearchQuery(
            query=query,
            category=category,
            is_enabled=is_enabled,
            playbook_type=playbook_type,
            environment=environment,
            limit=limit,
        )
        return self._search_playbooks_wf.execute(q)

    def get_playbook(self, identifier_or_id: str) -> PlaybookDetail:
        """Retrieves full playbook details, triggers, and execution steps."""
        return self._get_playbook_wf.execute(identifier_or_id=identifier_or_id)

    def list_playbook_categories(self) -> List[PlaybookCategory]:
        """Lists all SOAR Playbook categories/folders."""
        return self._list_playbook_cats_wf.execute()

    def search_integrations(
        self,
        query: Optional[Union[str, IntegrationSearchQuery]] = None,
        environment: Optional[str] = None,
        is_configured: Optional[bool] = None,
        is_certified: Optional[bool] = None,
        limit: int = 100,
    ) -> IntegrationBatch:
        """Executes the SOAR Integration Search & Filter workflow."""
        if isinstance(query, IntegrationSearchQuery):
            return self._search_integrations_wf.execute(query)
        q = IntegrationSearchQuery(
            query=query,
            environment=environment,
            is_configured=is_configured,
            is_certified=is_certified,
            limit=limit,
        )
        return self._search_integrations_wf.execute(q)

    def get_integration(self, identifier: str) -> IntegrationDetail:
        """Retrieves complete details for a specific integration with instances and documentation."""
        return self._get_integration_wf.execute(identifier=identifier)

    def list_integration_instances(
        self,
        integration_id: Optional[str] = None,
        environment: Optional[str] = None,
    ) -> List[IntegrationInstance]:
        """Lists configured integration instances across environments or for a specific integration."""
        return self._list_integration_instances_wf.execute(
            integration_id=integration_id,
            environment=environment,
        )

    def list_remote_agents(
        self,
        state_filter: Optional[str] = None,
    ) -> List[RemoteAgent]:
        """Lists remote proxy execution agents."""
        return self._list_remote_agents_wf.execute(state_filter=state_filter)

    def search_jobs(
        self,
        query: Optional[Union[str, JobSearchQuery]] = None,
        integration: Optional[str] = None,
        enabled: Optional[bool] = None,
        limit: int = 100,
    ) -> JobBatch:
        """Executes the SOAR Scheduled Jobs Search & Filter workflow."""
        if isinstance(query, JobSearchQuery):
            return self._search_jobs_wf.execute(query)
        q = JobSearchQuery(
            query=query,
            integration=integration,
            enabled=enabled,
            limit=limit,
        )
        return self._search_jobs_wf.execute(q)

    def get_job(
        self,
        integration: str,
        job_id: str,
    ) -> JobDetail:
        """Retrieves complete details for a specific SOAR job with instances and logs."""
        return self._get_job_wf.execute(
            integration=integration,
            job_id=job_id,
        )

    def list_job_instances(
        self,
        integration: Optional[str] = None,
        job_id: Optional[str] = None,
    ) -> List[JobInstance]:
        """Lists runtime job instances across environments or for a specific job."""
        return self._list_job_instances_wf.execute(
            integration=integration,
            job_id=job_id,
        )

    def get_job_instance_logs(
        self,
        job_instance_id: str,
        limit: int = 20,
        order_by: str = "endTime desc",
    ) -> List[JobExecutionLog]:
        """Retrieves execution run records and text logs for a specific job instance."""
        return self._get_job_instance_logs_wf.execute(
            job_instance_id=job_instance_id,
            limit=limit,
            order_by=order_by,
        )

    def search_content_packs(
        self,
        query: Optional[str] = None,
        category: Optional[str] = None,
        pack_type: Optional[str] = None,
        deployed: Optional[bool] = None,
        limit: int = 100,
    ) -> ContentPackBatch:
        """Searches and filters Content Hub Marketplace Content Packs."""
        q = ContentPackSearchQuery(
            query=query,
            category=category,
            pack_type=pack_type,
            deployed=deployed,
            limit=limit,
        )
        return self._search_content_packs_wf.execute(q)

    def get_content_pack(
        self,
        pack_id_or_title: str,
    ) -> ContentPackDetail:
        """Retrieves a complete Content Pack composite with bundled components."""
        return self._get_content_pack_wf.execute(pack_id_or_title)

    def list_content_pack_categories(self) -> List[Dict[str, Any]]:
        """Discovers and aggregates distinct Content Hub categories with pack counts."""
        return self._list_content_pack_cats_wf.execute()

    def search_curated_rulesets(
        self,
        query: Optional[str] = None,
        category: Optional[str] = None,
        mitre_tactic: Optional[str] = None,
        mitre_technique: Optional[str] = None,
        log_source: Optional[str] = None,
        limit: int = 50,
    ) -> CuratedRuleSetBatch:
        """Discovers and searches Google SecOps Curated Rule Sets."""
        q = CuratedRuleSearchQuery(
            query=query,
            category=category,
            mitre_tactic=mitre_tactic,
            mitre_technique=mitre_technique,
            log_source=log_source,
            limit=limit,
        )
        return self._search_curated_rulesets_wf.execute(q)

    def get_curated_ruleset(
        self,
        ruleset_id_or_title: str,
    ) -> CuratedRuleSetDetail:
        """Deep-inspects a Curated Rule Set, its deployments, member rules, and detection telemetry."""
        return self._get_curated_ruleset_wf.execute(ruleset_id_or_title)

    def get_curated_rule(
        self,
        rule_id_or_title: str,
    ) -> CuratedRuleDetail:
        """Retrieves a Curated Rule, its metadata, and its executable YARA-L logic."""
        return self._get_curated_rule_wf.execute(rule_id_or_title)

    def get_curated_detection_metrics(
        self,
        start_time: Optional[str] = None,
        end_time: Optional[str] = None,
    ) -> CuratedDetectionMetrics:
        """Aggregates detection firing counts and retrieves tenant rule engine quotas."""
        return self._get_curated_metrics_wf.execute(start_time=start_time, end_time=end_time)

    # --- Milestone 5.8: Content Hub Marketplace Response Integrations Methods ---

    def search_marketplace_integrations(
        self,
        query: Optional[str] = None,
        category: Optional[str] = None,
        installed: Optional[bool] = None,
        update_available: Optional[bool] = None,
        certified: Optional[bool] = None,
        limit: int = 50,
    ) -> MarketplaceIntegrationBatch:
        """Discovers, searches, and filters Marketplace Response Integrations."""
        q = MarketplaceIntegrationSearchQuery(
            query=query,
            category=category,
            installed=installed,
            update_available=update_available,
            certified=certified,
            limit=limit,
        )
        return self._search_marketplace_integrations_wf.execute(q)

    def get_marketplace_integration(
        self,
        identifier_or_title: str,
    ) -> MarketplaceIntegrationDetail:
        """Retrieves full details for a Marketplace Response Integration."""
        return self._get_marketplace_integration_wf.execute(identifier_or_title)

    def get_marketplace_integration_diff(
        self,
        identifier_or_title: str,
    ) -> MarketplaceCommercialDiff:
        """Retrieves commercial version diff comparing installed vs latest marketplace version."""
        return self._get_marketplace_integration_diff_wf.execute(identifier_or_title)

    def get_marketplace_integration_affected_items(
        self,
        identifier_or_title: str,
    ) -> MarketplaceAffectedItems:
        """Retrieves downstream environment instances and playbooks affected by an integration."""
        return self._get_marketplace_affected_items_wf.execute(identifier_or_title)

    def search_dashboards(
        self,
        query: Optional[str] = None,
        dashboard_type: Optional[str] = None,
        limit: int = 50,
    ) -> DashboardBatch:
        """Discovers and filters native dashboards."""
        q = DashboardSearchQuery(query=query, dashboard_type=dashboard_type, limit=limit)
        return self._search_dashboards_wf.execute(q)

    def get_dashboard(
        self,
        identifier_or_title: str,
        include_queries: bool = True,
    ) -> DashboardDetail:
        """Retrieves complete composite dashboard graph with charts and queries."""
        return self._get_dashboard_wf.execute(identifier_or_title, include_queries=include_queries)

    def execute_dashboard_query(
        self,
        query_name_or_id: str,
        filters: Optional[List[Dict[str, Any]]] = None,
        use_previous_time_range: bool = False,
        query_source: str = "DASHBOARD",
    ) -> DashboardQueryResult:
        """Executes a dashboard query and normalizes columnar output into tabular rows."""
        return self._execute_dashboard_query_wf.execute(
            query_name_or_id=query_name_or_id,
            filters=filters,
            use_previous_time_range=use_previous_time_range,
            query_source=query_source,
        )

    def validate_dashboard_query(
        self,
        raw_query: str,
        dialect: str = "DIALECT_STATS",
    ) -> ValidationResult:
        """Validates statistical query syntax."""
        return self._validate_dashboard_query_wf.execute(raw_query=raw_query, dialect=dialect)

    def get_managed_domain_settings(self) -> ManagedDomainSettings:
        """Retrieves approved email domains configured for report deliveries and alerts."""
        return self._get_managed_domains_wf.execute()

    def search_feeds(
        self,
        query: Optional[str] = None,
        feed_source_type: Optional[str] = None,
        log_type: Optional[str] = None,
        state: Optional[str] = None,
        limit: int = 50,
    ) -> FeedBatch:
        """Searches, lists, and filters push/pull ingestion feeds."""
        return self._search_feeds_wf.execute(
            query=query,
            feed_source_type=feed_source_type,
            log_type=log_type,
            state=state,
            limit=limit,
        )

    def get_feed(self, identifier_or_title: str) -> FeedDetail:
        """Retrieves complete configuration details for a specific ingestion feed."""
        return self._get_feed_wf.execute(identifier_or_title)

    def search_log_processing_pipelines(
        self,
        query: Optional[str] = None,
        log_type: Optional[str] = None,
        limit: int = 50,
    ) -> LogProcessingPipelineBatch:
        """Discovers and lists Data Processing Pipelines."""
        return self._search_pipelines_wf.execute(
            query=query,
            log_type=log_type,
            limit=limit,
        )

    def get_log_processing_pipeline(self, identifier_or_title: str) -> LogProcessingPipelineDetail:
        """Retrieves full transform statements and Bindplane link for a Data Processing Pipeline."""
        return self._get_pipeline_wf.execute(identifier_or_title)

    def list_feed_source_type_schemas(self, limit: int = 100) -> FeedSourceTypeBatch:
        """Lists all supported feed source types and metadata."""
        return self._list_feed_source_types_wf.execute(limit=limit)

    def list_feed_log_type_schemas(
        self,
        feed_source_type: str,
        limit: int = 100,
        include_field_schemas: bool = False,
    ) -> FeedLogTypeBatch:
        """Lists log type schemas for a feed source type, with lean payload handling."""
        return self._list_feed_log_types_wf.execute(
            feed_source_type=feed_source_type,
            limit=limit,
            include_field_schemas=include_field_schemas,
        )

    # --------------------------------------------------------------------------
    # Milestone 5.11: SIEM Settings - Parsers, Log Types, Extensions & Settings
    # --------------------------------------------------------------------------

    def list_log_types(self, query: str = "", limit: int = 100) -> LogTypeBatch:
        """Discovers and filters supported ingestion log types."""
        return self._list_log_types_wf.execute(query=query, limit=limit)

    def search_parsers(
        self,
        log_type: str = "-",
        creator: str = "ALL",
        state: str = "ALL",
        query: str = "",
        limit: int = 50,
    ) -> ParserBatch:
        """Discovers and filters parsers across log types."""
        return self._search_parsers_wf.execute(
            log_type=log_type,
            creator=creator,
            state=state,
            query=query,
            limit=limit,
        )

    def get_parser(self, log_type: str, parser_id: Optional[str] = None) -> ParserDetail:
        """Retrieves full parser metadata and decodes CBN Logstash filter code."""
        return self._get_parser_wf.execute(log_type=log_type, parser_id=parser_id)

    def search_parser_extensions(
        self,
        log_type: str = "-",
        query: str = "",
        limit: int = 50,
    ) -> ParserExtensionBatch:
        """Discovers parser extensions across log types."""
        return self._search_parser_extensions_wf.execute(
            log_type=log_type,
            query=query,
            limit=limit,
        )

    def get_parser_extension(self, log_type: str, extension_id: str) -> ParserExtensionDetail:
        """Retrieves full parser extension configuration, decoded snippet, and test log."""
        return self._get_parser_extension_wf.execute(log_type=log_type, extension_id=extension_id)

    def get_log_type_setting(self, log_type: str) -> LogTypeSetting:
        """Retrieves autonomous parsing settings for a log type."""
        return self._get_log_type_setting_wf.execute(log_type=log_type)

    # --------------------------------------------------------------------------
    # Milestone 5.12: SIEM Settings - Preview Features & Data RBAC
    # --------------------------------------------------------------------------

    def list_preview_features(
        self,
        enabled_only: bool = False,
        query: str = "",
        limit: int = 100,
    ) -> PreviewFeatureBatch:
        """Discovers and filters customer preview features."""
        return self._list_preview_features_wf.execute(
            enabled_only=enabled_only,
            query=query,
            limit=limit,
        )

    def get_preview_feature(self, feature_id: str) -> PreviewFeatureSummary:
        """Retrieves detailed configuration and status for a preview feature."""
        return self._get_preview_feature_wf.execute(feature_id=feature_id)

    def search_data_access_scopes(
        self,
        query: str = "",
        limit: int = 100,
    ) -> DataAccessScopeBatch:
        """Discovers and filters Data Access Scopes."""
        return self._search_data_access_scopes_wf.execute(query=query, limit=limit)

    def get_data_access_scope(self, scope_id: str) -> DataAccessScopeDetail:
        """Retrieves deep configuration of a Data Access Scope."""
        return self._get_data_access_scope_wf.execute(scope_id=scope_id)

    def search_data_access_labels(
        self,
        query: str = "",
        limit: int = 100,
    ) -> DataAccessLabelBatch:
        """Discovers and filters Data Access Labels."""
        return self._search_data_access_labels_wf.execute(query=query, limit=limit)

    def get_data_access_label(self, label_id: str) -> DataAccessLabelDetail:
        """Retrieves deep configuration of a Data Access Label."""
        return self._get_data_access_label_wf.execute(label_id=label_id)

    def search_environment_scopes(
        self,
        query: str = "",
        limit: int = 100,
    ) -> EnvironmentScopeBatch:
        """Discovers SOAR environments and inspects bound Data Access Scopes."""
        return self._search_environment_scopes_wf.execute(query=query, limit=limit)

    def list_enrichment_combinations(
        self,
        enrichment_type: str = "ALL",
        target_log_type: str = "",
        limit: int = 100,
    ) -> EnrichmentCombinationBatch:
        """Discovers available entity enrichment combinations."""
        return self._list_enrichment_combinations_wf.execute(
            enrichment_type=enrichment_type,
            target_log_type=target_log_type,
            limit=limit,
        )

    def search_enrichment_controls(
        self,
        query: str = "",
        enrichment_type: str = "ALL",
        limit: int = 100,
    ) -> EnrichmentControlBatch:
        """Discovers and filters deployed enrichment controls."""
        return self._search_enrichment_controls_wf.execute(
            query=query,
            enrichment_type=enrichment_type,
            limit=limit,
        )

    def get_enrichment_control(self, control_id: str) -> EnrichmentControlDetail:
        """Retrieves deep configuration of a deployed enrichment control."""
        return self._get_enrichment_control_wf.execute(control_id=control_id)

    def get_agent_settings(self) -> GeminiAgentSettings:
        """Retrieves Gemini Triage & Investigation Agent settings."""
        return self._get_agent_settings_wf.execute()

    def get_entity_risk_config(self) -> EntityRiskConfig:
        """Retrieves UEBA entity risk scoring configuration."""
        return self._get_entity_risk_config_wf.execute()

    def get_tenant_instance(self) -> TenantInstanceDetails:
        """Retrieves root tenant instance details and configuration flags."""
        return self._get_tenant_instance_wf.execute()

    # --- Milestone 6.1: SOAR Settings & Case Data Configuration ---

    def search_soar_users(
        self,
        query: str = "",
        role_filter: Optional[int] = None,
        limit: int = 100,
    ) -> SoarUserBatch:
        """Searches and filters SOAR users and external identity profiles."""
        return self._search_soar_users_wf.execute(
            query=query,
            role_filter=role_filter,
            limit=limit,
        )

    def get_soar_user(self, user_id: str) -> SoarUserDetail:
        """Retrieves deep inspection of a single SOAR user."""
        return self._get_soar_user_wf.execute(user_id=user_id)

    def list_soc_roles(self, limit: int = 100) -> SocRoleBatch:
        """Lists configured SOC roles and workflow assignment access hierarchy."""
        return self._list_soc_roles_wf.execute(limit=limit)

    def get_company_settings(self) -> CompanySettingsBatch:
        """Retrieves tenant company rebranding and reporting settings."""
        return self._get_company_settings_wf.execute()

    def search_case_tag_definitions(
        self,
        query: str = "",
        match_criteria: str = "ALL",
        limit: int = 100,
    ) -> CaseTagDefinitionBatch:
        """Discovers and filters case tag classification rules."""
        return self._search_case_tags_wf.execute(
            query=query,
            match_criteria=match_criteria,
            limit=limit,
        )

    def list_case_stage_definitions(self, limit: int = 100) -> CaseStageDefinitionBatch:
        """Lists ordered SOC case lifecycle pipeline stage definitions."""
        return self._list_case_stages_wf.execute(limit=limit)

    def list_case_close_definitions(self, limit: int = 100) -> CaseCloseDefinitionBatch:
        """Catalogs predefined case close reasons and root causes."""
        return self._list_case_close_defs_wf.execute(limit=limit)

    def list_case_close_dynamic_parameters(
        self,
        limit: int = 100,
    ) -> CaseCloseDynamicParameterBatch:
        """Lists dynamic form parameters and custom field schemas for case closure."""
        return self._list_case_close_params_wf.execute(limit=limit)

    def get_case_title_settings(self) -> CaseTitleSettingsBatch:
        """Retrieves case title formatting priority rules."""
        return self._get_case_title_settings_wf.execute()

    def search_case_views(
        self,
        query: str = "",
        view_type: str = "",
        limit: int = 100,
    ) -> CaseViewBatch:
        """Discovers and filters layout view templates for Cases, Alerts, and Detections."""
        return self._search_case_views_wf.execute(
            query=query,
            view_type=view_type,
            limit=limit,
        )

    def get_case_view(self, view_id: str) -> CaseViewDetail:
        """Retrieves deep inspection of a specific view layout template and widget hierarchy."""
        return self._get_case_view_wf.execute(view_id=view_id)

    def search_custom_fields(
        self,
        query: str = "",
        field_type: str = "",
        scope: str = "",
        limit: int = 100,
    ) -> CustomFieldBatch:
        """Lists and filters custom typed fields across Case and Alert scopes."""
        return self._search_custom_fields_wf.execute(
            query=query,
            field_type=field_type,
            scope=scope,
            limit=limit,
        )

    def get_custom_field(self, field_id: str) -> CustomFieldDetail:
        """Retrieves deep inspection of a single custom field definition."""
        return self._get_custom_field_wf.execute(field_id=field_id)

    def search_calculated_fields(
        self,
        query: str = "",
        limit: int = 100,
    ) -> CalculatedFieldBatch:
        """Lists and filters calculated field formula definitions."""
        return self._search_calculated_fields_wf.execute(
            query=query,
            limit=limit,
        )

    def get_calculated_field(self, definition_id: str) -> CalculatedFieldDetail:
        """Retrieves deep inspection of a single calculated field definition."""
        return self._get_calculated_field_wf.execute(definition_id=definition_id)

    def search_alert_grouping_rules(
        self,
        query: str = "",
        category: str = "",
        limit: int = 100,
    ) -> AlertGroupingRuleBatch:
        """Discovers and filters SOAR alert grouping rules determining case clustering."""
        return self._search_alert_grouping_rules_wf.execute(
            query=query,
            category=category,
            limit=limit,
        )

    def get_alert_grouping_rule(self, rule_id: str) -> AlertGroupingRuleDetail:
        """Retrieves deep inspection of a single alert grouping rule."""
        return self._get_alert_grouping_rule_wf.execute(rule_id=rule_id)

    def get_alert_grouping_settings(self) -> AlertGroupingSettingsBatch:
        """Retrieves global SOAR alert grouping configuration parameters."""
        return self._get_alert_grouping_settings_wf.execute()

    def get_data_retention_settings(self) -> DataRetentionSettingsBatch:
        """Retrieves SOAR data retention configuration and environment policy settings."""
        return self._get_data_retention_settings_wf.execute()

    def search_environments(
        self,
        query: str = "",
        limit: int = 100,
    ) -> EnvironmentBatch:
        """Discovers and filters multi-tenancy environments."""
        return self._search_environments_wf.execute(
            query=query if query else None,
            limit=limit,
        )

    def get_environment(self, env_id: str) -> EnvironmentDetail:
        """Retrieves deep configuration of a single multi-tenancy environment."""
        return self._get_environment_wf.execute(env_id=env_id)

    def search_environment_groups(
        self,
        query: str = "",
        limit: int = 100,
    ) -> EnvironmentGroupBatch:
        """Discovers and lists logical groupings of multi-tenancy environments."""
        return self._search_environment_groups_wf.execute(
            query=query if query else None,
            limit=limit,
        )

    def search_remote_agents(
        self,
        query: str = "",
        environment: str = "",
        agent_state: str = "",
        limit: int = 100,
    ) -> RemoteAgentBatch:
        """Discovers and filters remote SOAR agents."""
        return self._search_remote_agents_wf.execute(
            query=query if query else None,
            environment=environment if environment else None,
            agent_state=agent_state if agent_state else None,
            limit=limit,
        )

    def get_remote_agent(self, agent_id: str) -> RemoteAgentDetail:
        """Retrieves deep configuration of a single remote agent."""
        return self._get_remote_agent_wf.execute(agent_id=agent_id)

    def get_email_settings(self) -> EmailSettingsBatch:
        """Retrieves composite email transport configuration."""
        return self._get_email_settings_wf.execute()

    def get_support_settings(self) -> SupportSettingsBatch:
        """Retrieves Google Support access delegation properties."""
        return self._get_support_settings_wf.execute()

    def search_soar_networks(
        self,
        query: str = "",
        environment: str = "",
        limit: int = 100,
    ) -> SoarNetworkBatch:
        """Discovers and filters customer-defined CIDR network address ranges."""
        return self._search_soar_networks_wf.execute(
            query=query if query else None,
            environment=environment if environment else None,
            limit=limit,
        )

    def get_soar_network(self, network_id: str) -> SoarNetworkDetail:
        """Retrieves deep configuration of a single customer-defined CIDR network."""
        return self._get_soar_network_wf.execute(network_id=network_id)

    def search_soar_domains(
        self,
        query: str = "",
        environment: str = "",
        limit: int = 100,
    ) -> SoarDomainBatch:
        """Discovers and filters approved customer domain names."""
        return self._search_soar_domains_wf.execute(
            query=query if query else None,
            environment=environment if environment else None,
            limit=limit,
        )

    def get_soar_domain(self, domain_id: str) -> SoarDomainDetail:
        """Retrieves deep configuration of a single approved customer domain."""
        return self._get_soar_domain_wf.execute(domain_id=domain_id)

    def search_soar_custom_lists(
        self,
        query: str = "",
        category: str = "",
        environment: str = "",
        limit: int = 100,
    ) -> SoarCustomListBatch:
        """Discovers and filters SOAR custom list key-value retention entries."""
        return self._search_soar_custom_lists_wf.execute(
            query=query if query else None,
            category=category if category else None,
            environment=environment if environment else None,
            limit=limit,
        )

    def get_soar_custom_list(self, list_id: str) -> SoarCustomListDetail:
        """Retrieves deep configuration of a single SOAR custom list entry."""
        return self._get_soar_custom_list_wf.execute(list_id=list_id)

    def search_email_templates(
        self,
        query: str = "",
        template_type: str = "",
        environment: str = "",
        limit: int = 100,
    ) -> EmailTemplateBatch:
        """Discovers and filters email templates (plain text and HTML)."""
        return self._search_email_templates_wf.execute(
            query=query if query else None,
            template_type=template_type if template_type else None,
            environment=environment if environment else None,
            limit=limit,
        )

    def get_email_template(self, template_id: str) -> EmailTemplateDetail:
        """Retrieves deep configuration and content of a single email template."""
        return self._get_email_template_wf.execute(template_id=template_id)

    def search_entities_blocklists(
        self,
        query: str = "",
        entity_type: str = "",
        environment: str = "",
        limit: int = 100,
    ) -> EntitiesBlocklistBatch:
        """Discovers and filters entity noise-reduction blocklist rules."""
        return self._search_entities_blocklists_wf.execute(
            query=query if query else None,
            entity_type=entity_type if entity_type else None,
            environment=environment if environment else None,
            limit=limit,
        )

    def get_entities_blocklist(self, blocklist_id: str) -> EntitiesBlocklistDetail:
        """Retrieves deep configuration of a single entity blocklist entry."""
        return self._get_entities_blocklist_wf.execute(blocklist_id=blocklist_id)

    def search_sla_definitions(
        self,
        query: str = "",
        sla_type: str = "",
        environment: str = "",
        limit: int = 100,
    ) -> SlaDefinitionBatch:
        """Discovers and filters Service Level Agreement definitions."""
        return self._search_sla_definitions_wf.execute(
            query=query if query else None,
            sla_type=sla_type if sla_type else None,
            environment=environment if environment else None,
            limit=limit,
        )

    def get_sla_definition(self, sla_id: str) -> SlaDefinitionDetail:
        """Retrieves deep configuration of a single SLA definition."""
        return self._get_sla_definition_wf.execute(sla_id=sla_id)

    def search_request_templates(
        self,
        query: str = "",
        environment: str = "",
        limit: int = 100,
    ) -> RequestTemplateBatch:
        """Discovers and filters manual case request form templates."""
        return self._search_request_templates_wf.execute(
            query=query if query else None,
            environment=environment if environment else None,
            limit=limit,
        )

    def get_request_template(self, template_id: str) -> RequestTemplateDetail:
        """Retrieves deep configuration and field definitions of a single request template."""
        return self._get_request_template_wf.execute(template_id=template_id)

    def search_soar_ingestion_connectors(
        self,
        query: str = "",
        integration: str = "-",
        connector_id: str = "-",
        environment: str = "",
        enabled_only: bool = False,
        limit: int = 100,
    ) -> SoarIngestionConnectorBatch:
        """Discovers and filters configured SOAR ingestion connector instances across integrations."""
        return self._search_soar_ingestion_connectors_wf.execute(
            query=query if query else None,
            integration=integration,
            connector_id=connector_id,
            environment=environment if environment else None,
            enabled_only=enabled_only,
            limit=limit,
        )

    def get_soar_ingestion_connector(
        self,
        instance_id: str,
        integration: str = "-",
        connector_id: str = "-",
    ) -> SoarIngestionConnectorDetail:
        """Retrieves deep configuration of a single SOAR ingestion connector instance."""
        return self._get_soar_ingestion_connector_wf.execute(
            instance_id=instance_id,
            integration=integration,
            connector_id=connector_id,
        )

    def search_soar_webhooks(
        self,
        query: str = "",
        environment: str = "",
        enabled_only: bool = False,
        limit: int = 100,
    ) -> SoarWebhookBatch:
        """Discovers and filters configured SOAR event ingestion webhooks."""
        return self._search_soar_webhooks_wf.execute(
            query=query if query else None,
            environment=environment if environment else None,
            enabled_only=enabled_only,
            limit=limit,
        )

    def get_soar_webhook(self, webhook_id: str) -> SoarWebhookDetail:
        """Retrieves deep configuration and JSON schema mapping of a single SOAR event ingestion webhook."""
        return self._get_soar_webhook_wf.execute(webhook_id=webhook_id)

    def list_capabilities(self, category: Optional[str] = None) -> List[WorkflowCapability]:
        """Lists capabilities available in this engine instance."""
        return self.registry.list_capabilities(category=category)














