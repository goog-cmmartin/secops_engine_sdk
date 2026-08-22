"""Reviewed drift baseline for the capability contract suite.

Captured 2026-08-21 against the spec corpus (97 files). These 70 specs do not
yet expose a machine-extractable dotted capability id. This is QUARANTINED,
REVIEWED drift -- not an approval of the state, but a snapshot that:

  * prevents NEW drift (a spec losing its id fails the suite immediately), and
  * makes progress visible (fixing a spec's id => remove it here => locked in).

Do NOT add entries. Only remove them, as specs are normalized to carry
`metadata.capability_id`. When this set reaches empty, delete it and flip
SpecToRegistryLinkageTest to require an id on every spec.
"""

SPECS_WITHOUT_EXTRACTABLE_ID_BASELINE = frozenset({
    "case_config/alert-grouping-rule-get-001.yaml",
    "case_config/alert-grouping-rule-search-001.yaml",
    "case_config/alert-grouping-settings-get-001.yaml",
    "case_config/calculated-field-get-001.yaml",
    "case_config/calculated-field-search-001.yaml",
    "case_config/case-close-definition-list-001.yaml",
    "case_config/case-close-parameter-list-001.yaml",
    "case_config/case-stage-definition-list-001.yaml",
    "case_config/case-tag-definition-search-001.yaml",
    "case_config/case-title-settings-get-001.yaml",
    "case_config/case-view-get-001.yaml",
    "case_config/case-view-search-001.yaml",
    "case_config/custom-field-get-001.yaml",
    "case_config/custom-field-search-001.yaml",
    "curated_detections/curated-metrics-001.yaml",
    "curated_detections/curated-rule-get-001.yaml",
    "curated_detections/curated-ruleset-get-001.yaml",
    "curated_detections/curated-ruleset-search-001.yaml",
    "dashboards/dashboard-get-001.yaml",
    "dashboards/dashboard-query-execute-001.yaml",
    "dashboards/dashboard-query-validate-001.yaml",
    "dashboards/dashboard-search-001.yaml",
    "data_rbac/data-access-label-get-001.yaml",
    "data_rbac/data-access-label-search-001.yaml",
    "data_rbac/data-access-scope-get-001.yaml",
    "data_rbac/data-access-scope-search-001.yaml",
    "data_rbac/environment-scope-search-001.yaml",
    "enrichment/enrichment-combination-list-001.yaml",
    "enrichment/enrichment-control-get-001.yaml",
    "enrichment/enrichment-control-search-001.yaml",
    "feeds/feed-get-001.yaml",
    "feeds/feed-schema-list-001.yaml",
    "feeds/feed-search-001.yaml",
    "marketplace_integrations/marketplace-integration-affected-001.yaml",
    "marketplace_integrations/marketplace-integration-diff-001.yaml",
    "marketplace_integrations/marketplace-integration-get-001.yaml",
    "marketplace_integrations/marketplace-integration-search-001.yaml",
    "parsers/log-type-search-001.yaml",
    "parsers/log-type-setting-get-001.yaml",
    "parsers/parser-extension-get-001.yaml",
    "parsers/parser-extension-search-001.yaml",
    "parsers/parser-get-001.yaml",
    "parsers/parser-search-001.yaml",
    "preview_features/preview-feature-get-001.yaml",
    "preview_features/preview-feature-list-001.yaml",
    "siem_settings/agent-settings-get-001.yaml",
    "siem_settings/entity-risk-config-get-001.yaml",
    "siem_settings/managed-domains-get-001.yaml",
    "siem_settings/pipeline-get-001.yaml",
    "siem_settings/pipeline-search-001.yaml",
    "siem_settings/tenant-instance-get-001.yaml",
    "soar_settings/company-settings-get-001.yaml",
    "soar_settings/custom-list-get-001.yaml",
    "soar_settings/custom-list-search-001.yaml",
    "soar_settings/data-retention-settings-get-001.yaml",
    "soar_settings/domain-get-001.yaml",
    "soar_settings/domain-search-001.yaml",
    "soar_settings/email-template-get-001.yaml",
    "soar_settings/email-template-search-001.yaml",
    "soar_settings/entities-blocklist-get-001.yaml",
    "soar_settings/entities-blocklist-search-001.yaml",
    "soar_settings/network-get-001.yaml",
    "soar_settings/network-search-001.yaml",
    "soar_settings/request-template-get-001.yaml",
    "soar_settings/request-template-search-001.yaml",
    "soar_settings/sla-definition-get-001.yaml",
    "soar_settings/sla-definition-search-001.yaml",
    "soar_settings/soar-user-get-001.yaml",
    "soar_settings/soar-user-search-001.yaml",
    "soar_settings/soc-role-list-001.yaml",
})


# ---------------------------------------------------------------------------
# KNOWN ID MISMATCHES (owed work, to be fixed in Step 3 spec normalization).
# These specs declare a dotted id whose NAMESPACE SEGMENTATION disagrees with
# the registry, even though the capability IS implemented and registered.
# The registry is the source of truth. Each spec's `metadata.capability_id`
# must be corrected to the mapped value, then removed from this set.
# Discovered 2026-08-21 by SpecToRegistryLinkageTest on first run.
# ---------------------------------------------------------------------------
KNOWN_SPEC_ID_MISMATCHES = {
    # EMPTIED 2026-08-21 (Step 3): all four SOAR spec id mismatches fixed.
    # The specs now declare the registry-correct dotted ids. Do not re-add;
    # a spec declaring a wrong id must fail SpecToRegistryLinkageTest outright.
}
