from typing import Any, Callable, Dict, List, Optional, Union

from engine.domain import (
    AlertInvestigation,
    AlertPlaybookStatus,
    PlaybookInstanceCard,
    PlaybookInstanceRun,
    PlaybookInstanceStep,
    CaseCommentRecord,
    CaseInvestigation,
    CaseSearchBatch,
    CaseSearchPrefix,
    CaseSearchQuery,
    CaseSearchResultItem,
    CaseStatus,
    CaseTimeline,
    CaseTimelineEvent,
    CaseTriageAssessment,
    CaseTriageBatch,
    CaseWallRecord,
    CaseWallResult,
    TriageVerdict,
    CasePrecedentSummary,
    EntityPrecedentItem,
    CaseUpdateResult,
    CaseAlertUpdateResult,
    CaseAlertRecommendationJob,
    CaseAlertRecommendation,
    CaseSummary,
    DataTable,
    DataTableColumnInfo,
    DataTableHealthFinding,
    DataTableHealthReport,
    DataTableHealthStatus,
    DataTableRow,
    DataTableListResult,
    DataTableRowListResult,
    RuleSeverity,
    RuleCompilationDiagnostic,
    RuleValidationResult,
    RuleDeployment,
    RuleExecutionError,
    RuleExecutionErrorListResult,
    RuleSummary,
    RuleDetail,
    RuleListResult,
    RuleRevisionListResult,
    RuleHealthFinding,
    RuleHealthReport,
    RuleHealthStatus,
    ContentPackBatch,
    ContentPackDetail,
    ContentPackSearchQuery,
    ContentPackSummary,
    CuratedDetectionMetrics,
    CuratedRuleDetail,
    CuratedRuleSearchQuery,
    CuratedRuleSetBatch,
    CuratedRuleSetDeployment,
    CuratedRuleSetDetail,
    CuratedRuleSetSummary,
    CuratedRuleSummary,
    DashboardBatch,
    DashboardChart,
    DashboardDetail,
    DashboardHealthFinding,
    DashboardHealthReport,
    DashboardHealthStatus,
    DashboardQuery,
    DashboardQueryResult,
    DashboardSearchQuery,
    DashboardSummary,
    EnterpriseIocBatch,
    EnterpriseIocMatch,
    EntityInvestigationReport,
    EntitySummaryResult,
    EntityType,
    EventInvestigation,
    EventReference,
    FeedBatch,
    FeedDetail,
    FeedHealthFinding,
    FeedHealthReport,
    FeedHealthStatus,
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
    ParserHealthFinding,
    ParserHealthReport,
    ParserHealthStatus,
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
    StatsSearchRequest,
    StatsSearchResult,
    StatsSearchSession,
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
from engine.workflows.case_actions import (
    AssignCaseWorkflow,
    CreateCaseAlertRecommendationWorkflow,
    FetchCaseAlertRecommendationWorkflow,
    GetCaseAlertRecommendationWorkflow,
    GetCaseSummaryWorkflow,
    GetOrCreateCaseSummaryWorkflow,
    SetCaseAlertPriorityWorkflow,
    SetCaseIncidentWorkflow,
    SetCaseStageWorkflow,
    UpdateCaseAlertWorkflow,
    UpdateCaseWorkflow,
)
from engine.workflows.case_investigation import (
    AddCaseCommentWorkflow,
    InvestigateCaseWorkflow,
)
from engine.workflows.case_search import SearchCasesWorkflow
from engine.workflows.case_triage import OrchestrateCaseTriageWorkflow
from engine.workflows.case_wall import (
    GetCaseWallWorkflow,
    ListCaseCommentsWorkflow,
)
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
    SetCuratedRuleSetDeploymentWorkflow,
)
from engine.workflows.dashboards import (
    run_dashboard_health_check,
    ExecuteDashboardQueryWorkflow,
    GetDashboardDetailWorkflow,
    SearchDashboardsWorkflow,
    ValidateDashboardQueryWorkflow,
)
from engine.workflows.dashboard_health import AuditDashboardHealthWorkflow
from engine.workflows.data_rbac import (
    GetDataAccessLabelWorkflow,
    GetDataAccessScopeWorkflow,
    SearchDataAccessLabelsWorkflow,
    SearchDataAccessScopesWorkflow,
    SearchEnvironmentScopesWorkflow,
)
from engine.entity_detector import DetectedEntity, EntityCategory, detect_entity
from engine.workflows.enrichment import (
    GetEnrichmentControlWorkflow,
    ListEnrichmentCombinationsWorkflow,
    SearchEnrichmentControlsWorkflow,
)
from engine.workflows.entity_search import (
    InvestigateEntityWorkflow,
    SearchEntityGraphWorkflow,
    SearchEnterpriseIocsWorkflow,
    SummarizeEntityWorkflow,
)
from engine.workflows.feed import (
    GetFeedDetailWorkflow,
    ListFeedLogTypeSchemasWorkflow,
    ListFeedSourceTypeSchemasWorkflow,
    SearchFeedsWorkflow,
)
from engine.workflows.feed_health import AuditFeedHealthWorkflow
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
from engine.workflows.parser_health import AuditParserHealthWorkflow
from engine.workflows.playbook import (
    GetAlertPlaybookInstancesWorkflow,
    GetPlaybookWorkflow,
    ListPlaybookCategoriesWorkflow,
    SearchPlaybooksWorkflow,
)
from engine.workflows.playbook_health import AuditPlaybookHealthWorkflow
from engine.workflows.preview_feature import (
    GetPreviewFeatureWorkflow,
    ListPreviewFeaturesWorkflow,
)
from engine.workflows.refine_search import (
    RefineSearchWorkflow,
    SearchFromEntityWorkflow,
)
from engine.workflows.search_udm import SearchUDMWorkflow
from engine.workflows.search_udm_stats import SearchUDMStatsWorkflow
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
from engine.workflows.data_tables import (
    ListDataTablesWorkflow,
    GetDataTableWorkflow,
    CreateDataTableWorkflow,
    PatchDataTableWorkflow,
    DeleteDataTableWorkflow,
    ListDataTableRowsWorkflow,
    AddDataTableRowsWorkflow,
    DeleteDataTableRowWorkflow,
)
from engine.workflows.data_table_health import (
    AuditDataTableHealthWorkflow,
)
from engine.workflows.detection_rules import (
    ListRulesWorkflow,
    GetRuleWorkflow,
    VerifyRuleWorkflow,
    CreateRuleWorkflow,
    PatchRuleWorkflow,
    DeleteRuleWorkflow,
    ListRuleRevisionsWorkflow,
    GetRuleDeploymentWorkflow,
    UpdateRuleDeploymentWorkflow,
    ListRuleErrorsWorkflow,
)
from engine.workflows.rule_health import AuditRuleHealthWorkflow



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
        "_search_udm_stats_wf": lambda e: SearchUDMStatsWorkflow(e.adapter),
        "_investigate_event_wf": lambda e: InvestigateEventWorkflow(e.adapter),
        "_refine_search_wf": lambda e: RefineSearchWorkflow(e._search_udm_wf),
        "_search_from_entity_wf": lambda e: SearchFromEntityWorkflow(e._search_udm_wf),
        "_investigate_case_wf": lambda e: InvestigateCaseWorkflow(e.adapter),
        "_add_case_comment_wf": lambda e: AddCaseCommentWorkflow(e.adapter),
        "_list_case_comments_wf": lambda e: ListCaseCommentsWorkflow(e.adapter),
        "_get_case_wall_wf": lambda e: GetCaseWallWorkflow(e.adapter),
        "_update_case_wf": lambda e: UpdateCaseWorkflow(e.adapter),
        "_assign_case_wf": lambda e: AssignCaseWorkflow(e.adapter),
        "_set_case_stage_wf": lambda e: SetCaseStageWorkflow(e.adapter),
        "_set_case_incident_wf": lambda e: SetCaseIncidentWorkflow(e.adapter),
        "_update_case_alert_wf": lambda e: UpdateCaseAlertWorkflow(e.adapter),
        "_set_case_alert_priority_wf": lambda e: SetCaseAlertPriorityWorkflow(e.adapter),
        "_create_case_alert_recommendation_wf": lambda e: CreateCaseAlertRecommendationWorkflow(e.adapter),
        "_fetch_case_alert_recommendation_wf": lambda e: FetchCaseAlertRecommendationWorkflow(e.adapter),
        "_get_case_alert_recommendation_wf": lambda e: GetCaseAlertRecommendationWorkflow(e.adapter),
        "_get_or_create_case_summary_wf": lambda e: GetOrCreateCaseSummaryWorkflow(e.adapter),
        "_get_case_summary_wf": lambda e: GetCaseSummaryWorkflow(e.adapter),
        "_investigate_alert_wf": lambda e: InvestigateAlertWorkflow(e.adapter),
        "_search_cases_wf": lambda e: SearchCasesWorkflow(e.adapter),
        "_orchestrate_case_triage_wf": lambda e: OrchestrateCaseTriageWorkflow(e.adapter),
        "_search_playbooks_wf": lambda e: SearchPlaybooksWorkflow(e.adapter),
        "_get_playbook_wf": lambda e: GetPlaybookWorkflow(e.adapter),
        "_list_playbook_cats_wf": lambda e: ListPlaybookCategoriesWorkflow(e.adapter),
        "_alert_playbook_instances_wf": lambda e: GetAlertPlaybookInstancesWorkflow(e.adapter),
        "_audit_soar_playbook_health_wf": lambda e: AuditPlaybookHealthWorkflow(e),
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
        "_set_curated_ruleset_deployment_wf": lambda e: SetCuratedRuleSetDeploymentWorkflow(e.adapter),
        "_search_marketplace_integrations_wf": lambda e: SearchMarketplaceIntegrationsWorkflow(e.adapter),
        "_get_marketplace_integration_wf": lambda e: GetMarketplaceIntegrationDetailWorkflow(e.adapter),
        "_get_marketplace_integration_diff_wf": lambda e: GetMarketplaceIntegrationDiffWorkflow(e.adapter),
        "_get_marketplace_affected_items_wf": lambda e: GetMarketplaceIntegrationAffectedItemsWorkflow(e.adapter),
        "_search_dashboards_wf": lambda e: SearchDashboardsWorkflow(e.adapter),
        "_get_dashboard_wf": lambda e: GetDashboardDetailWorkflow(e.adapter),
        "_execute_dashboard_query_wf": lambda e: ExecuteDashboardQueryWorkflow(e.adapter),
        "_validate_dashboard_query_wf": lambda e: ValidateDashboardQueryWorkflow(e.adapter),
        "_audit_dashboard_health_wf": lambda e: AuditDashboardHealthWorkflow(e.adapter),
        "_get_managed_domains_wf": lambda e: GetManagedDomainSettingsWorkflow(e.adapter),
        "_search_feeds_wf": lambda e: SearchFeedsWorkflow(e.adapter),
        "_get_feed_wf": lambda e: GetFeedDetailWorkflow(e.adapter),
        "_audit_feed_health_wf": lambda e: AuditFeedHealthWorkflow(e.adapter),
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
        "_audit_parser_health_wf": lambda e: AuditParserHealthWorkflow(e.adapter),
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
        "_search_entity_graph_wf": lambda e: SearchEntityGraphWorkflow(e._search_udm_wf),
        "_search_enterprise_iocs_wf": lambda e: SearchEnterpriseIocsWorkflow(e.adapter),
        "_summarize_entity_wf": lambda e: SummarizeEntityWorkflow(e.adapter),
        "_investigate_entity_wf": lambda e: InvestigateEntityWorkflow(
            e._search_entity_graph_wf,
            e._search_from_entity_wf,
            e._search_enterprise_iocs_wf,
            e._search_cases_wf,
            e._summarize_entity_wf,
        ),
        "_list_data_tables_wf": lambda e: ListDataTablesWorkflow(e.adapter),
        "_get_data_table_wf": lambda e: GetDataTableWorkflow(e.adapter),
        "_create_data_table_wf": lambda e: CreateDataTableWorkflow(e.adapter),
        "_patch_data_table_wf": lambda e: PatchDataTableWorkflow(e.adapter),
        "_delete_data_table_wf": lambda e: DeleteDataTableWorkflow(e.adapter),
        "_list_data_table_rows_wf": lambda e: ListDataTableRowsWorkflow(e.adapter),
        "_add_data_table_rows_wf": lambda e: AddDataTableRowsWorkflow(e.adapter),
        "_delete_data_table_row_wf": lambda e: DeleteDataTableRowWorkflow(e.adapter),
        "_audit_data_table_health_wf": lambda e: AuditDataTableHealthWorkflow(e.adapter),
        "_list_rules_wf": lambda e: ListRulesWorkflow(e.adapter),
        "_get_rule_wf": lambda e: GetRuleWorkflow(e.adapter),
        "_verify_rule_wf": lambda e: VerifyRuleWorkflow(e.adapter),
        "_create_rule_wf": lambda e: CreateRuleWorkflow(e.adapter),
        "_patch_rule_wf": lambda e: PatchRuleWorkflow(e.adapter),
        "_delete_rule_wf": lambda e: DeleteRuleWorkflow(e.adapter),
        "_list_rule_revisions_wf": lambda e: ListRuleRevisionsWorkflow(e.adapter),
        "_get_rule_deployment_wf": lambda e: GetRuleDeploymentWorkflow(e.adapter),
        "_update_rule_deployment_wf": lambda e: UpdateRuleDeploymentWorkflow(e.adapter),
        "_list_rule_errors_wf": lambda e: ListRuleErrorsWorkflow(e.adapter),
        "_audit_rule_health_wf": lambda e: AuditRuleHealthWorkflow(e.adapter),
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
                capability_id="search.udm.stats",
                name="UDM Stats Search (Aggregation & Analytics)",
                description="Validates, initiates, streams, and aggregates UDM statistics, match/outcome metrics, and multi-field grouping operations via LRO.",
                category="search",
                handler=self.search_udm_stats,
                mcp_tool_name="search_udm_stats",
                composed=False,
                evidence_path="evidence/search/udm_stats",
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
                capability_id="entity.search_udm",
                name="UDM Entity Graph Search",
                description="Executes streaming searches across the native UDM entity graph (graph.entity.*).",
                category="entity",
                handler=self.search_entity_graph,
                mcp_tool_name="search_entity_udm",
                composed=True,
                uses=("search.udm",),
                evidence_path="evidence/entity/search_udm",
            )
        )
        self.registry.register(
            WorkflowCapability(
                capability_id="ioc.search_enterprise",
                name="Enterprise-Wide IoC Intelligence Search",
                description="Searches enterprise IoC matches and Mandiant breach intelligence for indicators.",
                category="ioc",
                handler=self.search_enterprise_iocs,
                mcp_tool_name="search_enterprise_iocs",
                composed=False,
                cardinality="bounded",
                evidence_path="evidence/ioc/search_enterprise",
            )
        )
        self.registry.register(
            WorkflowCapability(
                capability_id="entity.summarize",
                name="Entity Summarization Profile",
                description="Retrieves entity timeline intervals, prevalence metrics, and metadata.",
                category="entity",
                handler=self.summarize_entity,
                mcp_tool_name="summarize_entity",
                composed=False,
                cardinality="single",
                evidence_path="evidence/entity/summarize",
            )
        )
        self.registry.register(
            WorkflowCapability(
                capability_id="entity.investigate",
                name="Unified Cross-Engine Entity Investigation",
                description="Correlates an indicator across UDM Entity Graph, UDM Events, Enterprise IoC Intelligence, and SOAR Cases.",
                category="entity",
                handler=self.investigate_entity,
                mcp_tool_name="investigate_entity",
                composed=True,
                uses=("entity.search_udm", "search.from_entity", "ioc.search_enterprise", "case.search"),
                evidence_path="evidence/entity/investigate",
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
                capability_id="case.list_comments",
                name="List SOAR Case Comments",
                description="Lists all analyst comments and AI assessment notes for a SOAR case.",
                category="case",
                handler=self.list_case_comments,
                mcp_tool_name="list_case_comments",
                composed=False,
                evidence_path="evidence/case/comments",
            )
        )
        self.registry.register(
            WorkflowCapability(
                capability_id="case.get_wall",
                name="Get SOAR Case Activity Wall",
                description="Retrieves the complete SOAR case activity stream including status changes, tag updates, and playbook execution steps.",
                category="case",
                handler=self.get_case_wall,
                mcp_tool_name="get_case_wall",
                composed=False,
                evidence_path="evidence/case/wall",
            )
        )
        self.registry.register(
            WorkflowCapability(
                capability_id="case.update",
                name="Update SOAR Case Properties",
                description="Mutates case attributes such as assignee, stage, incident flag, or priority.",
                category="case",
                handler=self.update_case,
                mcp_tool_name="update_case",
                composed=False,
                evidence_path="evidence/case/update",
            )
        )
        self.registry.register(
            WorkflowCapability(
                capability_id="case.assign",
                name="Assign SOAR Case",
                description="Assigns a SOAR case to a SOC role (@Role) or user GUID.",
                category="case",
                handler=self.assign_case,
                mcp_tool_name="assign_case",
                composed=False,
                evidence_path="evidence/case/assign",
            )
        )
        self.registry.register(
            WorkflowCapability(
                capability_id="case.set_stage",
                name="Set SOAR Case Stage",
                description="Updates the lifecycle stage of a SOAR case.",
                category="case",
                handler=self.set_case_stage,
                mcp_tool_name="set_case_stage",
                composed=False,
                evidence_path="evidence/case/set_stage",
            )
        )
        self.registry.register(
            WorkflowCapability(
                capability_id="case.set_incident",
                name="Set SOAR Case Incident Status",
                description="Marks or unmarks a SOAR case as an incident.",
                category="case",
                handler=self.set_case_incident,
                mcp_tool_name="set_case_incident",
                composed=False,
                evidence_path="evidence/case/set_incident",
            )
        )
        self.registry.register(
            WorkflowCapability(
                capability_id="case_alert.update",
                name="Update Case Alert",
                description="Mutates case alert attributes such as priority or status.",
                category="case",
                handler=self.update_case_alert,
                mcp_tool_name="update_case_alert",
                composed=False,
                evidence_path="evidence/case/alert_update",
            )
        )
        self.registry.register(
            WorkflowCapability(
                capability_id="case_alert.set_priority",
                name="Set Case Alert Priority",
                description="Updates the priority level of a specific case alert.",
                category="case",
                handler=self.set_case_alert_priority,
                mcp_tool_name="set_case_alert_priority",
                composed=False,
                evidence_path="evidence/case/alert_set_priority",
            )
        )
        self.registry.register(
            WorkflowCapability(
                capability_id="case_alert.create_recommendation",
                name="Create Case Alert Recommendation",
                description="Initiates asynchronous generation of a Gemini AI recommendation for a case alert.",
                category="case",
                handler=self.create_case_alert_recommendation,
                mcp_tool_name="create_case_alert_recommendation",
                composed=False,
                evidence_path="evidence/case/alert_create_recommendation",
            )
        )
        self.registry.register(
            WorkflowCapability(
                capability_id="case_alert.fetch_recommendation",
                name="Fetch Case Alert Recommendation",
                description="Fetches a previously generated Gemini AI recommendation for a case alert by recommendation ID.",
                category="case",
                handler=self.fetch_case_alert_recommendation,
                mcp_tool_name="fetch_case_alert_recommendation",
                composed=False,
                evidence_path="evidence/case/alert_fetch_recommendation",
            )
        )
        self.registry.register(
            WorkflowCapability(
                capability_id="case_alert.get_recommendation",
                name="Get Case Alert Recommendation",
                description="End-to-end workflow to trigger Gemini AI recommendation generation and poll until completion or failure.",
                category="case",
                handler=self.get_case_alert_recommendation,
                mcp_tool_name="get_case_alert_recommendation",
                composed=True,
                uses=("case_alert.create_recommendation", "case_alert.fetch_recommendation"),
                evidence_path="evidence/case/alert_get_recommendation",
            )
        )
        self.registry.register(
            WorkflowCapability(
                capability_id="case.get_or_create_summary",
                name="Get or Create SOAR Case AI Summary",
                description="Gets or initiates generation of a Gemini AI-driven overview, reasons, and next steps for a SOAR case.",
                category="case",
                handler=self.get_or_create_case_summary,
                mcp_tool_name="get_or_create_case_summary",
                composed=False,
                evidence_path="evidence/case/get_or_create_summary",
            )
        )
        self.registry.register(
            WorkflowCapability(
                capability_id="case.get_summary",
                name="Get SOAR Case AI Summary (Polled)",
                description="Requests Gemini AI case summary and polls until generation is complete or timeout.",
                category="case",
                handler=self.get_case_summary,
                mcp_tool_name="get_case_summary",
                composed=True,
                uses=("case.get_or_create_summary",),
                evidence_path="evidence/case/get_summary",
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
                capability_id="case.orchestrate_triage",
                name="Orchestrate Case Triage",
                description="Batched retrieval, parallel investigation, and automated initial triage assessment for SOAR cases.",
                category="case",
                handler=self.orchestrate_case_triage,
                mcp_tool_name="orchestrate_case_triage",
                composed=True,
                uses=("case.search", "case.investigate", "case.get_summary"),
                evidence_path="discovery/observations/03_case_triage_first_touch.md",
            )
        )
        self.registry.register(
            WorkflowCapability(
                capability_id="case.triage",
                name="Triage Single Case",
                description="End-to-end single case triage: deep investigation, Gemini AI summary, title and entity precedent correlation, novelty assessment, and stage transitions.",
                category="case",
                handler=self.triage_case,
                mcp_tool_name="triage_case",
                composed=True,
                uses=("case.investigate", "case.get_summary", "case.search"),
                evidence_path="discovery/observations/03_case_triage_first_touch.md",
            )
        )
        self.registry.register(
            WorkflowCapability(
                capability_id="case.timeline",
                name="Get Case Chronological Timeline",
                description="Synthesizes a chronologically ordered event timeline across Case Creation, Alert Detections, Playbook Milestones, Analyst Comments, and Case Updates.",
                category="case",
                handler=self.get_case_timeline,
                mcp_tool_name="get_case_timeline",
                composed=True,
                uses=("case.investigate",),
                evidence_path="discovery/observations/03_case_triage_first_touch.md",
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
                capability_id="playbook.instances",
                name="Alert Playbook Run Instances",
                description="Retrieves authoritative per-alert playbook run instances and the executed step DAG.",
                category="playbook",
                handler=self.get_alert_playbook_instances,
                mcp_tool_name="get_alert_playbook_instances",
                composed=False,
                evidence_path="evidence/playbook/instances",
            )
        )
        self.registry.register(
            WorkflowCapability(
                capability_id="playbook.audit_health",
                name="SOAR Playbook Health & Telemetry Audit",
                description="Audits SOAR playbooks and modular blocks for configuration hygiene, failure spikes, faulted actions, and queue latency using native Playbook Dashboard analytics.",
                category="playbook",
                handler=self.audit_soar_playbook_health,
                mcp_tool_name="audit_soar_playbook_health",
                composed=False,
                evidence_path="evidence/playbook/audit_health",
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
                capability_id="curated_detections.set_deployment",
                name="Set Curated Rule Set Deployment",
                description="Updates enabled and alerting states for a Curated Rule Set precision deployment.",
                category="curated_detections",
                handler=self.set_curated_ruleset_deployment,
                mcp_tool_name="set_curated_ruleset_deployment",
                composed=False,
                evidence_path="evidence/curated_detections/deployment_set",
            )
        )
        self.registry.register(
            WorkflowCapability(
                capability_id="curated_detections.audit_health",
                name="Curated Detections Health & Hygiene Audit",
                description="Performs a comprehensive deployment posture audit, detects misconfigurations like broad alerting, identifies top firing rules, and ranks newest/oldest content.",
                category="curated_detections",
                handler=self.audit_curated_detections_health,
                mcp_tool_name="audit_curated_detections_health",
                composed=True,
                uses=["curated_detections.metrics"],
                evidence_path="evidence/curated_detections/audit_health",
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
                capability_id="dashboard.health_check",
                name="Dashboard Health Check Execution",
                description="Executes comprehensive health check for a named dashboard by resolving configuration, executing all widget queries, and generating operational ingestion health summary.",
                category="dashboard",
                handler=self.run_dashboard_health_check,
                mcp_tool_name="run_dashboard_health_check",
                composed=True,
                evidence_path="evidence/dashboard/health_check",
            )
        )
        self.registry.register(
            WorkflowCapability(
                capability_id="dashboard.audit_health",
                name="Audit Dashboard Health & Governance",
                description="Audits native dashboards for recent creations, modifications, broken widget queries, empty placeholders, and staleness.",
                category="dashboard",
                handler=self.audit_dashboard_health,
                mcp_tool_name="audit_dashboard_health",
                composed=True,
                uses=("dashboard.search", "dashboard.get", "dashboard.validate_query"),
                evidence_path="evidence/dashboard/audit_health",
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
                capability_id="feed.audit_health",
                name="Audit Ingestion Feed Health",
                description="Audits and correlates ingestion feed states, Health Hub telemetry, and transport latency.",
                category="feed",
                handler=self.audit_feed_health,
                mcp_tool_name="audit_feed_health",
                composed=True,
                uses=("feed.search", "dashboard.execute_query"),
                evidence_path="evidence/feed/audit_health",
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
                capability_id="parser.audit_health",
                name="Audit SIEM Parser Health",
                description="Audits and correlates SIEM parser states, CBN version drift, extension conflicts, and Health Hub telemetry.",
                category="parser",
                handler=self.audit_parser_health,
                mcp_tool_name="audit_parser_health",
                composed=True,
                uses=("parser.search", "parser.extensions.search", "dashboard.execute_query"),
                evidence_path="evidence/parser/audit_health",
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
        self.registry.register(
            WorkflowCapability(
                capability_id="data_table.list",
                name="List Data Tables",
                description="Lists all structured Data Tables defined in Chronicle SIEM.",
                category="data_table",
                handler=self.list_data_tables,
                mcp_tool_name="list_data_tables",
                composed=False,
                evidence_path="evidence/data_table/list",
            )
        )
        self.registry.register(
            WorkflowCapability(
                capability_id="data_table.get",
                name="Get Data Table",
                description="Retrieves schema, columns, TTL, and metadata for a Chronicle SIEM Data Table.",
                category="data_table",
                handler=self.get_data_table,
                mcp_tool_name="get_data_table",
                composed=False,
                evidence_path="evidence/data_table/get",
            )
        )
        self.registry.register(
            WorkflowCapability(
                capability_id="data_table.create",
                name="Create Data Table",
                description="Creates a new structured Data Table with typed column definitions in Chronicle SIEM.",
                category="data_table",
                handler=self.create_data_table,
                mcp_tool_name="create_data_table",
                composed=False,
                evidence_path="evidence/data_table/create",
            )
        )
        self.registry.register(
            WorkflowCapability(
                capability_id="data_table.patch",
                name="Update Data Table",
                description="Updates description, TTL, or scope info of an existing Chronicle SIEM Data Table.",
                category="data_table",
                handler=self.patch_data_table,
                mcp_tool_name="patch_data_table",
                composed=False,
                evidence_path="evidence/data_table/patch",
            )
        )
        self.registry.register(
            WorkflowCapability(
                capability_id="data_table.delete",
                name="Delete Data Table",
                description="Deletes a structured Data Table from Chronicle SIEM.",
                category="data_table",
                handler=self.delete_data_table,
                mcp_tool_name="delete_data_table",
                composed=False,
                evidence_path="evidence/data_table/delete",
            )
        )
        self.registry.register(
            WorkflowCapability(
                capability_id="data_table.list_rows",
                name="List Data Table Rows",
                description="Queries and filters rows contained within a Chronicle SIEM Data Table.",
                category="data_table",
                handler=self.list_data_table_rows,
                mcp_tool_name="list_data_table_rows",
                composed=False,
                evidence_path="evidence/data_table/list_rows",
            )
        )
        self.registry.register(
            WorkflowCapability(
                capability_id="data_table.add_rows",
                name="Add Data Table Rows",
                description="Creates or appends rows in bulk to a Chronicle SIEM Data Table.",
                category="data_table",
                handler=self.add_data_table_rows,
                mcp_tool_name="add_data_table_rows",
                composed=False,
                evidence_path="evidence/data_table/add_rows",
            )
        )
        self.registry.register(
            WorkflowCapability(
                capability_id="data_table.delete_row",
                name="Delete Data Table Row",
                description="Deletes a single row from a Chronicle SIEM Data Table by row ID.",
                category="data_table",
                handler=self.delete_data_table_row,
                mcp_tool_name="delete_data_table_row",
                composed=False,
                evidence_path="evidence/data_table/delete_row",
            )
        )
        self.registry.register(
            WorkflowCapability(
                capability_id="data_table.audit_health",
                name="Audit Data Table Governance & Lineage",
                description="Audits Data Tables across the tenant for lifecycle recency, schema integrity, and detection false-negative risks.",
                category="data_table",
                handler=self.audit_data_table_health,
                mcp_tool_name="audit_data_tables",
                composed=True,
                uses=("data_table.list", "rule.list"),
                evidence_path="evidence/data_table/audit_health",
            )
        )
        self.registry.register(
            WorkflowCapability(
                capability_id="rule.list",
                name="Search Detection Rules",
                description="Lists custom YARA-L detection rules in Chronicle SIEM.",
                category="rule",
                handler=self.list_rules,
                mcp_tool_name="list_rules",
                composed=False,
                evidence_path="evidence/rule/list",
            )
        )
        self.registry.register(
            WorkflowCapability(
                capability_id="rule.get",
                name="Get Detection Rule",
                description="Retrieves full details and YARA-L logic of a detection rule.",
                category="rule",
                handler=self.get_rule,
                mcp_tool_name="get_rule",
                composed=False,
                evidence_path="evidence/rule/get",
            )
        )
        self.registry.register(
            WorkflowCapability(
                capability_id="rule.verify",
                name="Verify Rule Text",
                description="Validates YARA-L 2.0 rule syntax against the Chronicle compiler.",
                category="rule",
                handler=self.verify_rule,
                mcp_tool_name="verify_rule_text",
                composed=False,
                evidence_path="evidence/rule/verify",
            )
        )
        self.registry.register(
            WorkflowCapability(
                capability_id="rule.create",
                name="Create Detection Rule",
                description="Creates a new YARA-L detection rule in Chronicle SIEM.",
                category="rule",
                handler=self.create_rule,
                mcp_tool_name="create_rule",
                composed=False,
                evidence_path="evidence/rule/create",
            )
        )
        self.registry.register(
            WorkflowCapability(
                capability_id="rule.patch",
                name="Patch Detection Rule",
                description="Updates the YARA-L logic of an existing detection rule.",
                category="rule",
                handler=self.patch_rule,
                mcp_tool_name="patch_rule",
                composed=False,
                evidence_path="evidence/rule/patch",
            )
        )
        self.registry.register(
            WorkflowCapability(
                capability_id="rule.delete",
                name="Delete Detection Rule",
                description="Deletes a custom detection rule from Chronicle SIEM.",
                category="rule",
                handler=self.delete_rule,
                mcp_tool_name="delete_rule",
                composed=False,
                evidence_path="evidence/rule/delete",
            )
        )
        self.registry.register(
            WorkflowCapability(
                capability_id="rule.revisions",
                name="List Rule Revisions",
                description="Lists historical revisions and version history of a detection rule.",
                category="rule",
                handler=self.list_rule_revisions,
                mcp_tool_name="list_rule_revisions",
                composed=False,
                evidence_path="evidence/rule/revisions",
            )
        )
        self.registry.register(
            WorkflowCapability(
                capability_id="rule.deployment.get",
                name="Get Rule Deployment",
                description="Retrieves deployment, frequency, and alerting status of a rule.",
                category="rule",
                handler=self.get_rule_deployment,
                mcp_tool_name="get_rule_deployment",
                composed=False,
                evidence_path="evidence/rule/deployment/get",
            )
        )
        self.registry.register(
            WorkflowCapability(
                capability_id="rule.deployment.update",
                name="Update Rule Deployment",
                description="Updates deployment properties (enabled, alerting, frequency) of a rule.",
                category="rule",
                handler=self.update_rule_deployment,
                mcp_tool_name="update_rule_deployment",
                composed=False,
                evidence_path="evidence/rule/deployment/update",
            )
        )
        self.registry.register(
            WorkflowCapability(
                capability_id="rule.errors",
                name="List Rule Execution Errors",
                description="Lists runtime and execution errors across detection rules.",
                category="rule",
                handler=self.list_rule_errors,
                mcp_tool_name="list_rule_errors",
                composed=False,
                evidence_path="evidence/rule/errors",
            )
        )
        self.registry.register(
            WorkflowCapability(
                capability_id="rule.audit_health",
                name="Audit Detection Rule Health",
                description="Audits and correlates Chronicle YARA-L rules, execution errors, latency observability, and detection decay.",
                category="rule",
                handler=self.audit_rule_health,
                mcp_tool_name="audit_rule_health",
                composed=True,
                uses=("rule.list", "rule.errors", "dashboard.execute_query"),
                evidence_path="evidence/rule/audit_health",
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

    def search_udm_stats(
        self,
        request: Optional[Union[StatsSearchRequest, str]] = None,
        query: Optional[str] = None,
        start_time: Optional[str] = None,
        end_time: Optional[str] = None,
        max_events: int = 10000,
        case_insensitive: bool = True,
        generate_ai_overview: bool = True,
        max_values_per_field: int = 60,
        on_batch: Optional[Callable[[StatsSearchResult, StatsSearchSession], None]] = None,
        on_state_change: Optional[Callable[[Any, Any, StatsSearchSession], None]] = None,
        cancel_token: Optional[Any] = None,
        poll_interval: float = 0.5,
        max_poll_seconds: float = 120.0,
    ) -> StatsSearchSession:
        """Executes the canonical UDM Stats Search (Aggregation & Analytics) workflow."""
        if isinstance(request, StatsSearchRequest):
            req = request
        else:
            q = query or (request if isinstance(request, str) else None)
            if not q:
                raise ValueError("A query string or StatsSearchRequest must be provided")
            if start_time is None or end_time is None:
                raise ValueError("start_time and end_time are required when query is passed as a string")
            req = StatsSearchRequest(
                query=q,
                start_time=start_time,
                end_time=end_time,
                max_events=max_events,
                case_insensitive=case_insensitive,
                generate_ai_overview=generate_ai_overview,
                max_values_per_field=max_values_per_field,
            )

        return self._search_udm_stats_wf.execute(
            request=req,
            on_batch=on_batch,
            on_state_change=on_state_change,
            cancel_token=cancel_token,
            poll_interval=poll_interval,
            max_poll_seconds=max_poll_seconds,
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

    def get_alert_playbook_status(
        self, case_id: str, alert_id: Optional[str] = None
    ) -> List[AlertPlaybookStatus]:
        """Returns the attached playbook + status snapshot for alert(s) in a case.

        Tier-1: reuses the Case Investigation workflow (no extra endpoint) and
        surfaces the playbook association already present in the case-alert payload.
        The reported ``status`` is the alert-level ``playbookStatus`` snapshot, not
        the authoritative per-run instance record.

        Args:
            case_id: Numeric case ID (or resource name; the trailing segment is used).
            alert_id: Optional alert identifier/name to filter to a single alert. When
                omitted, status for every alert in the case is returned.

        Returns:
            A list of :class:`AlertPlaybookStatus`. Empty if the case has no alerts
            (or the given ``alert_id`` does not match).
        """
        investigation = self._investigate_case_wf.execute(case_id=case_id)
        cid = str(case_id).strip().split("/")[-1]
        target = str(alert_id).strip().split("/")[-1] if alert_id else None

        results: List[AlertPlaybookStatus] = []
        for a in investigation.alerts:
            if target is not None and target not in (a.identifier, a.name, a.alert_id):
                continue
            results.append(
                AlertPlaybookStatus(
                    case_id=cid,
                    alert_id=a.alert_id,
                    alert_display_name=a.display_name,
                    attached_playbook_name=a.attached_playbook_name,
                    status=a.playbook_status,
                    run_count=a.playbook_run_count,
                    alert_group_identifier=a.alert_group_identifier,
                )
            )
        return results

    def get_alert_playbook_instances(
        self, case_id: str, alert_identifier: str
    ) -> List[PlaybookInstanceCard]:
        """Tier-2: lists authoritative playbook *run instances* for an alert.

        Unlike :meth:`get_alert_playbook_status` (a Tier-1 snapshot from the
        case-alert payload), this queries ``legacyGetWorkflowInstancesCards`` for
        the actual run instances attached to the alert.

        Args:
            case_id: Numeric case ID (or resource name; trailing segment is used).
            alert_identifier: Either the opaque ``alertGroupIdentifier`` or a plain
                alert id/name (auto-resolved to the group identifier).

        Returns:
            A list of :class:`PlaybookInstanceCard`. Each card's
            ``definition_identifier`` can be passed to
            :meth:`get_alert_playbook_instance` for the full run.
        """
        return self._alert_playbook_instances_wf.execute(
            case_id=case_id, alert_identifier=alert_identifier
        )

    def get_alert_playbook_instance(
        self,
        case_id: str,
        alert_identifier: str,
        definition_identifier: Optional[str] = None,
        should_fetch_steps: bool = True,
        collapse_blocks: bool = True,
        loops_requested_iterations: Optional[List[Any]] = None,
    ) -> PlaybookInstanceRun:
        """Tier-2: retrieves one full playbook run instance incl. the step DAG.

        Wraps ``legacyGetWorkflowInstance``. If ``definition_identifier`` is
        omitted, it is resolved from the alert's first instance card.

        Args:
            case_id: Numeric case ID (or resource name; trailing segment is used).
            alert_identifier: Opaque ``alertGroupIdentifier`` or a plain alert
                id/name (auto-resolved).
            definition_identifier: Playbook UUID. Optional; resolved via the cards
                endpoint when not provided.
            should_fetch_steps: Whether to include per-step execution records.
            collapse_blocks: Whether to collapse nested playbook blocks.
            loops_requested_iterations: Optional loop-iteration selectors.

        Returns:
            A :class:`PlaybookInstanceRun` with runtime status, steps, and the
            execution DAG (``relations``).
        """
        return self._alert_playbook_instances_wf.execute_full(
            case_id=case_id,
            alert_identifier=alert_identifier,
            definition_identifier=definition_identifier,
            should_fetch_steps=should_fetch_steps,
            collapse_blocks=collapse_blocks,
            loops_requested_iterations=loops_requested_iterations,
        )

    def get_alert_playbook_executed_path(
        self,
        case_id: str,
        alert_identifier: str,
        definition_identifier: Optional[str] = None,
    ) -> List[PlaybookInstanceStep]:
        """Return only the playbook steps that actually executed, in run order.

        Convenience wrapper over :meth:`get_alert_playbook_instance` that collapses
        the full conditional step DAG down to the single branch a given run
        actually traversed (see :meth:`PlaybookInstanceRun.executed_path`). Useful
        for post-incident review and for summarizing "what the playbook did" without
        wading through un-taken branches.

        Args:
            case_id: Numeric case ID (or resource name; trailing segment is used).
            alert_identifier: Opaque ``alertGroupIdentifier`` or a plain alert
                id/name (auto-resolved).
            definition_identifier: Playbook UUID. Optional; resolved via the cards
                endpoint when not provided.

        Returns:
            Ordered list of executed :class:`PlaybookInstanceStep` records (may be
            empty if the run has not executed any steps yet).
        """
        run = self.get_alert_playbook_instance(
            case_id=case_id,
            alert_identifier=alert_identifier,
            definition_identifier=definition_identifier,
            should_fetch_steps=True,
        )
        return run.executed_path()


    def add_case_comment(self, case_id: str, comment: str) -> CaseCommentRecord:
        """Executes the Add Case Comment workflow."""
        return self._add_case_comment_wf.execute(case_id=case_id, comment=comment)

    def list_case_comments(self, case_id: str) -> List[CaseCommentRecord]:
        """Lists all analyst comments and AI assessment notes for a SOAR case (`case.list_comments`)."""
        return self._list_case_comments_wf.execute(case_id=case_id)

    def get_case_wall(
        self,
        case_id: str,
        limit: int = 50,
        page_token: Optional[str] = None,
        activity_type: Optional[str] = None,
    ) -> CaseWallResult:
        """Retrieves and parses the complete SOAR Case Activity Wall (`case.get_wall`)."""
        return self._get_case_wall_wf.execute(
            case_id=case_id,
            limit=limit,
            page_token=page_token,
            activity_type=activity_type,
        )

    def update_case(
        self,
        case_id: str,
        assignee: Optional[str] = None,
        stage: Optional[str] = None,
        incident: Optional[bool] = None,
        priority: Optional[str] = None,
        updates: Optional[Dict[str, Any]] = None,
        update_mask: Optional[str] = None,
    ) -> CaseUpdateResult:
        """Executes the Update Case workflow."""
        return self._update_case_wf.execute(
            case_id=case_id,
            assignee=assignee,
            stage=stage,
            incident=incident,
            priority=priority,
            updates=updates,
            update_mask=update_mask,
        )

    def assign_case(self, case_id: str, assignee: str) -> CaseUpdateResult:
        """Executes the Assign Case workflow (to a role e.g. @Tier1 or user GUID/email)."""
        return self._assign_case_wf.execute(case_id=case_id, assignee=assignee)

    def set_case_stage(self, case_id: str, stage: str) -> CaseUpdateResult:
        """Executes the Set Case Stage workflow."""
        return self._set_case_stage_wf.execute(case_id=case_id, stage=stage)

    def set_case_incident(self, case_id: str, incident: bool = True) -> CaseUpdateResult:
        """Executes the Set Case Incident workflow."""
        return self._set_case_incident_wf.execute(case_id=case_id, incident=incident)

    def update_case_alert(
        self,
        case_id: str,
        alert_id: str,
        priority: Optional[str] = None,
        status: Optional[str] = None,
        updates: Optional[Dict[str, Any]] = None,
        update_mask: Optional[str] = None,
    ) -> CaseAlertUpdateResult:
        """Executes the Update Case Alert workflow."""
        return self._update_case_alert_wf.execute(
            case_id=case_id,
            alert_id=alert_id,
            priority=priority,
            status=status,
            updates=updates,
            update_mask=update_mask,
        )

    def set_case_alert_priority(self, case_id: str, alert_id: str, priority: str) -> CaseAlertUpdateResult:
        """Executes the Set Case Alert Priority workflow."""
        return self._set_case_alert_priority_wf.execute(case_id=case_id, alert_id=alert_id, priority=priority)

    def create_case_alert_recommendation(self, case_id: str, alert_id: str) -> CaseAlertRecommendationJob:
        """Initiates async Gemini AI recommendation generation for a case alert."""
        return self._create_case_alert_recommendation_wf.execute(case_id=case_id, alert_id=alert_id)

    def fetch_case_alert_recommendation(self, case_id: str, recommendation_id: str) -> CaseAlertRecommendation:
        """Fetches a previously generated Gemini AI recommendation for a case alert."""
        return self._fetch_case_alert_recommendation_wf.execute(case_id=case_id, recommendation_id=recommendation_id)

    def get_case_alert_recommendation(
        self,
        case_id: str,
        alert_id: str,
        timeout_sec: float = 30.0,
        poll_interval_sec: float = 2.0,
    ) -> CaseAlertRecommendation:
        """Executes end-to-end Gemini AI recommendation generation and polls until complete."""
        return self._get_case_alert_recommendation_wf.execute(
            case_id=case_id,
            alert_id=alert_id,
            timeout_sec=timeout_sec,
            poll_interval_sec=poll_interval_sec,
        )

    def get_or_create_case_summary(self, case_id: str) -> CaseSummary:
        """Gets or initiates generation of a Gemini AI summary for a SOAR case."""
        return self._get_or_create_case_summary_wf.execute(case_id=case_id)

    def get_case_summary(
        self,
        case_id: str,
        timeout_sec: float = 90.0,
        poll_interval_sec: float = 3.0,
    ) -> CaseSummary:
        """Requests a Gemini AI case summary and polls until complete or timeout."""
        return self._get_case_summary_wf.execute(
            case_id=case_id,
            timeout_sec=timeout_sec,
            poll_interval_sec=poll_interval_sec,
        )

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
        """Executes the SOAR Case Search workflow.

        NOTE (SecOps nuance): the ``query`` string maps to the legacy ``title`` field,
        which is a *prefixed query DSL*, not a plain title-substring match. A bare term
        (e.g. a raw hash) will return zero results. Prefix the term using the closed
        vocabulary in :class:`CaseSearchPrefix` -- e.g. ``"Entity:<sha256>"``,
        ``"AlertName:<name>"``, ``"CaseIds:<id>"``, ``"TicketIds:<id>"``, ``"Port:<n>"``.
        For entity-driven lookups prefer :meth:`search_cases_by_entity`.
        """
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

    def search_cases_by_entity(
        self,
        entity_value: str,
        start_time: Optional[Any] = None,
        end_time: Optional[Any] = None,
        environments: Optional[List[str]] = None,
        page_size: int = 50,
        page_number: int = 0,
    ) -> CaseSearchBatch:
        """Finds cases involving a given entity value (IP, hash, user, domain, etc.).

        Thin, discoverable wrapper over :meth:`search_cases` that applies the
        ``Entity:`` prefix required by the case-search DSL. This is the canonical
        "prior/similar cases by entity" lookup.

        Example::

            batch = engine.search_cases_by_entity(
                "2FDA6E766E1B5263D7D957F2FCC998C438BD92C7B7E566E6D31872C254FA88BB")
            print(batch.total_count)  # cases involving this file hash
        """
        return self.search_cases(
            query=CaseSearchPrefix.ENTITY.apply(entity_value),
            start_time=start_time,
            end_time=end_time,
            environments=environments,
            page_size=page_size,
            page_number=page_number,
        )

    def triage_case(
        self,
        case_id: str,
        fetch_summary: bool = True,
        search_precedents: bool = True,
        summary_timeout_sec: float = 15.0,
        apply_stage_update: bool = False,
        post_comment: bool = False,
    ) -> CaseTriageAssessment:
        """Executes full analyst triage workflow for a single specific case (`case.triage`).

        Runs deep case investigation (alerts, entities, comments), retrieves Gemini AI
        summary, performs historical title and entity precedent correlation, evaluates
        novelty vs repeat pattern, and optionally updates stage or posts triage audit comments.
        """
        return self._orchestrate_case_triage_wf.triage_single_case(
            case_id=case_id,
            fetch_summary=fetch_summary,
            search_precedents=search_precedents,
            summary_timeout_sec=summary_timeout_sec,
            apply_stage_update=apply_stage_update,
            post_comment=post_comment,
        )

    def get_case_timeline(self, case_id: str) -> CaseTimeline:
        """Constructs a unified, chronologically sorted timeline of events and milestones in a case (`case.timeline`)."""
        from engine.workflows.case_triage import GetCaseTimelineWorkflow
        return GetCaseTimelineWorkflow(self.adapter).execute(case_id=case_id)

    def orchestrate_case_triage(
        self,
        case_ids: Optional[List[str]] = None,
        limit: int = 5,
        open_only: bool = True,
        query_text: str = "",
        priorities: Optional[List[str]] = None,
        stages: Optional[List[str]] = None,
        tags: Optional[List[str]] = None,
        environments: Optional[List[str]] = None,
        assigned_users: Optional[List[str]] = None,
        is_important: Optional[bool] = None,
        page_number: int = 0,
        search_precedents: bool = True,
        fetch_summary: bool = False,
    ) -> CaseTriageBatch:
        """Executes the Case Orchestrate Triage workflow (`case.orchestrate_triage`).

        Batched retrieval, parallel deep multi-resource investigation, precedent correlation,
        and automated triage scoring & subagent prompt synthesis for SOAR cases.
        """
        return self._orchestrate_case_triage_wf.execute(
            case_ids=case_ids,
            limit=limit,
            open_only=open_only,
            query_text=query_text,
            priorities=priorities,
            stages=stages,
            tags=tags,
            environments=environments,
            assigned_users=assigned_users,
            is_important=is_important,
            page_number=page_number,
            search_precedents=search_precedents,
            fetch_summary=fetch_summary,
        )

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

    def audit_soar_playbook_health(
        self,
        days: int = 7,
        scan_deep: bool = True,
        fail_threshold_pct: float = 15.0,
        slow_threshold_minutes: float = 3.0,
    ) -> Dict[str, Any]:
        """Audits SOAR playbooks and modular blocks for configuration hygiene, failure spikes, faulted actions, and queue latency."""
        return self._audit_soar_playbook_health_wf.execute(
            days=days,
            scan_deep=scan_deep,
            fail_threshold_pct=fail_threshold_pct,
            slow_threshold_minutes=slow_threshold_minutes,
        )

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

    def set_curated_ruleset_deployment(
        self,
        ruleset_id_or_title: str,
        precision: str = "PRECISE",
        enabled: Optional[bool] = None,
        alerting: Optional[bool] = None,
        sync_rules: bool = True,
    ) -> CuratedRuleSetDeployment:
        """Updates enabled and alerting states for a Curated Rule Set precision deployment."""
        return self._set_curated_ruleset_deployment_wf.execute(
            ruleset_id_or_title=ruleset_id_or_title,
            precision=precision,
            enabled=enabled,
            alerting=alerting,
            sync_rules=sync_rules,
        )

    def audit_curated_detections_health(
        self,
        days: int = 7,
        scan_deployments: bool = True,
    ) -> Dict[str, Any]:
        """Performs a comprehensive health check and misconfiguration audit across Curated Detections."""
        from runbooks.operations.curated_detections_health import generate_curated_detections_health_report
        return generate_curated_detections_health_report(
            engine=self,
            days=days,
            scan_deployments=scan_deployments,
        )

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


    def run_dashboard_health_check(
        self,
        dashboard_name: str,
    ) -> Dict[str, Any]:
        """Executes comprehensive health check for a named dashboard.
        
        Workflow retrieves dashboard configuration, executes all widget queries,
        and generates operational summary of ingestion health metrics.
        
        Args:
            dashboard_name: Display name of dashboard (e.g., "Data Ingestion and Health")
        
        Returns:
            Dict containing dashboard_id, query_results, and human-readable summary
        """
        return run_dashboard_health_check(
            adapter=self.adapter,
            dashboard_name=dashboard_name,
            project_id=None,  # Use adapter defaults
            customer_id=None,
            region=None,
        )

    def audit_dashboard_health(
        self,
        lookback_days: int = 14,
        stale_days: int = 180,
        validate_queries: bool = True,
        max_deep_dashboards: int = 50,
    ) -> DashboardHealthReport:
        """Audits native dashboards for creations, modifications, broken widget queries, and staleness."""
        return self._audit_dashboard_health_wf.execute(
            lookback_days=lookback_days,
            stale_days=stale_days,
            validate_queries=validate_queries,
            max_deep_dashboards=max_deep_dashboards,
        )

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

    def audit_feed_health(self, lookback_days: int = 7) -> FeedHealthReport:
        """Audits all configured ingestion feeds against Health Hub telemetry and decay indicators."""
        return self._audit_feed_health_wf.execute(lookback_days=lookback_days)

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

    def audit_parser_health(self, lookback_days: int = 7) -> ParserHealthReport:
        """Audits all configured SIEM parsers and extensions against Health Hub telemetry and version drift."""
        return self._audit_parser_health_wf.execute(lookback_days=lookback_days)

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

    def detect_entity(self, value: str, hint: Optional[str] = None) -> DetectedEntity:
        """Detects entity indicator type, category, and canonical graph & event queries.

        Pass ``hint`` (our EntityType names or SOAR involved-entity type strings) to
        override the regex heuristics when the caller already knows the type.
        """
        return detect_entity(value, hint=hint)

    def search_entity_graph(
        self,
        indicator_or_field: str,
        value: Optional[str] = None,
        start_time: Optional[str] = None,
        end_time: Optional[str] = None,
        receive_limit: int = 10000,
        batch_size: int = 2000,
        hint: Optional[str] = None,
        on_batch: Optional[Callable[[SearchBatchResult, SearchSession], None]] = None,
        on_state_change: Optional[Callable[[SearchSession], None]] = None,
        cancel_token: Optional[Callable[[], bool]] = None,
    ) -> SearchSession:
        """Executes streaming search against the UDM entity graph (graph.entity.*).

        Pass ``hint`` (SOAR entity_type or our EntityType) to bypass the ambiguous
        regex classification when the type is already known.
        """
        return self._search_entity_graph_wf.execute(
            indicator_or_field=indicator_or_field,
            value=value,
            start_time=start_time,
            end_time=end_time,
            receive_limit=receive_limit,
            batch_size=batch_size,
            hint=hint,
            on_batch=on_batch,
            on_state_change=on_state_change,
            cancel_token=cancel_token,
        )

    def search_enterprise_iocs(
        self,
        value: str,
        value_type: Optional[str] = None,
        start_time: Optional[str] = None,
        end_time: Optional[str] = None,
        max_matches: int = 10000,
        add_mandiant_attributes: bool = True,
    ) -> EnterpriseIocBatch:
        """Searches enterprise-wide IoC matches and Mandiant threat intel for an indicator."""
        return self._search_enterprise_iocs_wf.execute(
            value=value,
            value_type=value_type,
            start_time=start_time,
            end_time=end_time,
            max_matches=max_matches,
            add_mandiant_attributes=add_mandiant_attributes,
        )

    def summarize_entity(
        self,
        entity_id: str,
        start_time: Optional[str] = None,
        end_time: Optional[str] = None,
        return_alerts: bool = False,
        return_prevalence: bool = True,
        include_all_udm_event_types: bool = True,
    ) -> EntitySummaryResult:
        """Retrieves entity summary profile, timeline intervals, and prevalence."""
        return self._summarize_entity_wf.execute(
            entity_id=entity_id,
            start_time=start_time,
            end_time=end_time,
            return_alerts=return_alerts,
            return_prevalence=return_prevalence,
            include_all_udm_event_types=include_all_udm_event_types,
        )

    def investigate_entity(
        self,
        indicator: str,
        start_time: Optional[str] = None,
        end_time: Optional[str] = None,
        max_events: int = 50,
        include_cases: bool = True,
    ) -> EntityInvestigationReport:
        """Executes full cross-engine correlation across Entity Graph, UDM Events, IoCs, and SOAR Cases."""
        return self._investigate_entity_wf.execute(
            indicator=indicator,
            start_time=start_time,
            end_time=end_time,
            max_events=max_events,
            include_cases=include_cases,
        )

    def list_capabilities(self, category: Optional[str] = None) -> List[WorkflowCapability]:
        """Lists capabilities available in this engine instance."""
        return self.registry.list_capabilities(category=category)

    # -------------------------------------------------------------------------
    # Chronicle SIEM Data Tables
    # -------------------------------------------------------------------------

    def list_data_tables(
        self,
        page_size: int = 100,
        page_token: Optional[str] = None,
        order_by: Optional[str] = None,
    ) -> DataTableListResult:
        """Lists structured data tables in Chronicle SIEM."""
        return self._list_data_tables_wf.execute(
            page_size=page_size,
            page_token=page_token,
            order_by=order_by,
        )

    def get_data_table(self, table_name_or_id: str) -> DataTable:
        """Gets schema and metadata for a specific Chronicle SIEM Data Table."""
        return self._get_data_table_wf.execute(table_name_or_id=table_name_or_id)

    def create_data_table(
        self,
        table_id: str,
        display_name: Optional[str] = None,
        description: Optional[str] = None,
        column_info: Optional[List[Dict[str, Any]]] = None,
        row_time_to_live: Optional[str] = None,
        scope_info: Optional[Dict[str, Any]] = None,
    ) -> DataTable:
        """Creates a new structured Data Table with column definitions in Chronicle SIEM."""
        return self._create_data_table_wf.execute(
            table_id=table_id,
            display_name=display_name,
            description=description,
            column_info=column_info,
            row_time_to_live=row_time_to_live,
            scope_info=scope_info,
        )

    def patch_data_table(
        self,
        table_name_or_id: str,
        description: Optional[str] = None,
        row_time_to_live: Optional[str] = None,
        scope_info: Optional[Dict[str, Any]] = None,
        update_mask: Optional[str] = None,
    ) -> DataTable:
        """Updates description, TTL, or scope info of an existing Data Table."""
        return self._patch_data_table_wf.execute(
            table_name_or_id=table_name_or_id,
            description=description,
            row_time_to_live=row_time_to_live,
            scope_info=scope_info,
            update_mask=update_mask,
        )

    def delete_data_table(self, table_name_or_id: str) -> Dict[str, Any]:
        """Deletes a Chronicle SIEM Data Table."""
        return self._delete_data_table_wf.execute(table_name_or_id=table_name_or_id)

    def list_data_table_rows(
        self,
        table_name_or_id: str,
        page_size: int = 50,
        page_token: Optional[str] = None,
        filter_expr: Optional[str] = None,
    ) -> DataTableRowListResult:
        """Lists rows contained within a Chronicle SIEM Data Table."""
        return self._list_data_table_rows_wf.execute(
            table_name_or_id=table_name_or_id,
            page_size=page_size,
            page_token=page_token,
            filter_expr=filter_expr,
        )

    def add_data_table_rows(
        self,
        table_name_or_id: str,
        rows: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """Creates or appends rows in bulk to a Chronicle SIEM Data Table."""
        return self._add_data_table_rows_wf.execute(
            table_name_or_id=table_name_or_id,
            rows=rows,
        )

    def delete_data_table_row(
        self,
        table_name_or_id: str,
        row_id: str,
    ) -> Dict[str, Any]:
        """Deletes a single row from a Chronicle SIEM Data Table by row ID."""
        return self._delete_data_table_row_wf.execute(
            table_name_or_id=table_name_or_id,
            row_id=row_id,
        )

    def audit_data_table_health(
        self,
        lookback_days: int = 14,
        stale_days: int = 180,
        correlate_rules: bool = True,
        max_tables: int = 200,
    ) -> DataTableHealthReport:
        """Audits Data Tables for recency, schema hygiene, empty referenced detection risks, and lineage."""
        return self._audit_data_table_health_wf.execute(
            lookback_days=lookback_days,
            stale_days=stale_days,
            correlate_rules=correlate_rules,
            max_tables=max_tables,
        )

    # -------------------------------------------------------------------------
    # Custom YARA-L Detection Rules Facade Methods
    # -------------------------------------------------------------------------

    def list_rules(
        self,
        page_size: int = 100,
        page_token: Optional[str] = None,
        filter_expr: Optional[str] = None,
        view: Optional[str] = None,
    ) -> RuleListResult:
        """Lists custom YARA-L detection rules in Chronicle SIEM."""
        return self._list_rules_wf.execute(
            page_size=page_size,
            page_token=page_token,
            filter_expr=filter_expr,
            view=view,
        )

    def get_rule(
        self,
        rule_id_or_name: str,
        view: str = "FULL",
    ) -> RuleDetail:
        """Retrieves full details and YARA-L logic of a detection rule."""
        return self._get_rule_wf.execute(
            rule_id_or_name=rule_id_or_name,
            view=view,
        )

    def verify_rule(self, rule_text: str) -> RuleValidationResult:
        """Validates YARA-L 2.0 rule syntax against the Chronicle compiler."""
        return self._verify_rule_wf.execute(rule_text=rule_text)

    def validate_rule(self, rule_text: str) -> RuleValidationResult:
        """Alias for verify_rule: validates YARA-L 2.0 rule syntax."""
        return self.verify_rule(rule_text=rule_text)

    def create_rule(self, rule_text: str) -> RuleDetail:
        """Creates a new YARA-L detection rule in Chronicle SIEM."""
        return self._create_rule_wf.execute(rule_text=rule_text)

    def patch_rule(
        self,
        rule_id_or_name: str,
        rule_text: str,
        update_mask: Optional[str] = None,
    ) -> RuleDetail:
        """Updates the YARA-L logic of an existing detection rule."""
        return self._patch_rule_wf.execute(
            rule_id_or_name=rule_id_or_name,
            rule_text=rule_text,
            update_mask=update_mask,
        )

    def delete_rule(self, rule_id_or_name: str) -> Dict[str, Any]:
        """Deletes a custom detection rule from Chronicle SIEM."""
        return self._delete_rule_wf.execute(rule_id_or_name=rule_id_or_name)

    def list_rule_revisions(
        self,
        rule_id_or_name: str,
        page_size: int = 100,
        page_token: Optional[str] = None,
    ) -> RuleRevisionListResult:
        """Lists historical revisions and version history of a detection rule."""
        return self._list_rule_revisions_wf.execute(
            rule_id_or_name=rule_id_or_name,
            page_size=page_size,
            page_token=page_token,
        )

    def get_rule_deployment(self, rule_id_or_name: str) -> RuleDeployment:
        """Retrieves deployment, frequency, and alerting status of a rule."""
        return self._get_rule_deployment_wf.execute(rule_id_or_name=rule_id_or_name)

    def update_rule_deployment(
        self,
        rule_id_or_name: str,
        enabled: Optional[bool] = None,
        alerting: Optional[bool] = None,
        run_frequency: Optional[str] = None,
        update_mask: Optional[str] = None,
    ) -> RuleDeployment:
        """Updates deployment properties (enabled, alerting, frequency) of a rule."""
        return self._update_rule_deployment_wf.execute(
            rule_id_or_name=rule_id_or_name,
            enabled=enabled,
            alerting=alerting,
            run_frequency=run_frequency,
            update_mask=update_mask,
        )

    def list_rule_errors(
        self,
        rule_id_or_name: Optional[str] = None,
        page_size: int = 100,
        page_token: Optional[str] = None,
    ) -> RuleExecutionErrorListResult:
        """Lists runtime and execution errors across detection rules."""
        return self._list_rule_errors_wf.execute(
            rule_id_or_name=rule_id_or_name,
            page_size=page_size,
            page_token=page_token,
        )

    def audit_rule_health(
        self,
        include_curated: bool = True,
        latency_threshold_min: float = 30.0,
        page_size: int = 100,
    ) -> RuleHealthReport:
        """Audits detection rule health, errors, latencies, and decay."""
        return self._audit_rule_health_wf.execute(
            include_curated=include_curated,
            latency_threshold_min=latency_threshold_min,
            page_size=page_size,
        )
















