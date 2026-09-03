"""Chronicle SIEM Custom YARA-L Detection Rules workflows.

Orchestrates listing, retrieving, validating, creating, updating, deleting,
versioning, deployment management, and error tracking for detection rules.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Dict, List, Optional

if TYPE_CHECKING:
    from adapters.google_secops import GoogleSecOpsAdapter

from engine.domain import (
    RuleCompilationDiagnostic,
    RuleDeployment,
    RuleDetail,
    RuleExecutionError,
    RuleExecutionErrorListResult,
    RuleListResult,
    RuleRevisionListResult,
    RuleSummary,
    RuleValidationResult,
)


def _map_rule_summary(raw: Dict[str, Any]) -> RuleSummary:
    """Maps raw rule summary JSON into RuleSummary dataclass."""
    sev_obj = raw.get("severity", {})
    sev_name = sev_obj.get("displayName", "INFO") if isinstance(sev_obj, dict) else str(sev_obj)

    return RuleSummary(
        name=raw.get("name", ""),
        display_name=raw.get("displayName", ""),
        author=raw.get("author", ""),
        severity=sev_name,
        rule_type=raw.get("type", "SINGLE_EVENT"),
        allowed_run_frequencies=raw.get("allowedRunFrequencies", []),
        near_real_time_live_rule_eligible=bool(raw.get("nearRealTimeLiveRuleEligible", False)),
        etag=raw.get("etag", ""),
        rule_text_tags=raw.get("ruleTextTags", []),
        time_window_duration=raw.get("timeWindowDuration", ""),
        create_time=raw.get("createTime", ""),
        revision_id=raw.get("revisionId", ""),
        run_frequency=raw.get("runFrequency", ""),
        raw=raw,
    )


def _map_rule_detail(raw: Dict[str, Any]) -> RuleDetail:
    """Maps raw rule detail JSON into RuleDetail dataclass."""
    sev_obj = raw.get("severity", {})
    sev_name = sev_obj.get("displayName", "INFO") if isinstance(sev_obj, dict) else str(sev_obj)

    return RuleDetail(
        name=raw.get("name", ""),
        display_name=raw.get("displayName", ""),
        text=raw.get("text", ""),
        revision_id=raw.get("revisionId", ""),
        author=raw.get("author", ""),
        severity=sev_name,
        metadata=raw.get("metadata", {}),
        create_time=raw.get("createTime", ""),
        revision_create_time=raw.get("revisionCreateTime", ""),
        compilation_state=raw.get("compilationState", "SUCCEEDED"),
        rule_type=raw.get("type", "SINGLE_EVENT"),
        allowed_run_frequencies=raw.get("allowedRunFrequencies", []),
        etag=raw.get("etag", ""),
        near_real_time_live_rule_eligible=bool(raw.get("nearRealTimeLiveRuleEligible", False)),
        inputs_used=raw.get("inputsUsed", {}),
        rule_owner=raw.get("ruleOwner", "CUSTOMER"),
        run_frequency=raw.get("runFrequency", "LIVE"),
        rule_language=raw.get("ruleLanguage", "YARA_L_2_0"),
        raw=raw,
    )


def _map_diagnostic(raw: Dict[str, Any]) -> RuleCompilationDiagnostic:
    """Maps raw compilation diagnostic into RuleCompilationDiagnostic."""
    pos = raw.get("position", {})
    return RuleCompilationDiagnostic(
        message=raw.get("message", ""),
        severity=raw.get("severity", "ERROR"),
        start_line=pos.get("startLine"),
        start_column=pos.get("startColumn"),
        end_line=pos.get("endLine"),
        end_column=pos.get("endColumn"),
        raw=raw,
    )


def _map_rule_deployment(raw: Dict[str, Any]) -> RuleDeployment:
    """Maps raw rule deployment JSON into RuleDeployment dataclass."""
    return RuleDeployment(
        name=raw.get("name", ""),
        run_frequency=raw.get("runFrequency", "LIVE"),
        execution_state=raw.get("executionState", "DEFAULT"),
        enabled=bool(raw.get("enabled", False) or raw.get("executionState") == "ACTIVE" or raw.get("runFrequency") in ("LIVE", "HOURLY", "DAILY")),
        alerting=bool(raw.get("alerting", False)),
        last_alert_status_change_time=raw.get("lastAlertStatusChangeTime", ""),
        display_name=raw.get("displayName", ""),
        raw=raw,
    )


def _map_execution_error(raw: Dict[str, Any]) -> RuleExecutionError:
    """Maps raw rule execution error JSON into RuleExecutionError dataclass."""
    err_obj = raw.get("error", {})
    err_code = err_obj.get("code", 0) if isinstance(err_obj, dict) else 0
    err_msg = err_obj.get("message", "") if isinstance(err_obj, dict) else str(err_obj)

    time_range = raw.get("timeRange", {})
    return RuleExecutionError(
        name=raw.get("name", ""),
        error_code=err_code,
        error_message=err_msg,
        start_time=time_range.get("startTime", ""),
        end_time=time_range.get("endTime", ""),
        rule_resource_name=raw.get("rule", ""),
        curated_rule=raw.get("curatedRule", ""),
        raw=raw,
    )


class ListRulesWorkflow:
    """Workflow to list detection rules in Chronicle SIEM."""

    def __init__(self, adapter: GoogleSecOpsAdapter):
        self._adapter = adapter

    def execute(
        self,
        page_size: int = 100,
        page_token: Optional[str] = None,
        filter_expr: Optional[str] = None,
        view: Optional[str] = None,
    ) -> RuleListResult:
        resp = self._adapter.list_rules(
            page_size=page_size,
            page_token=page_token,
            filter_expr=filter_expr,
            view=view,
        )
        raw_rules = resp.get("rules", [])
        rules = [_map_rule_summary(r) for r in raw_rules]
        return RuleListResult(
            rules=rules,
            next_page_token=resp.get("nextPageToken"),
            provenance={"count": len(rules), "filter": filter_expr, "view": view},
        )


class GetRuleWorkflow:
    """Workflow to fetch full details and YARA-L logic of a detection rule."""

    def __init__(self, adapter: GoogleSecOpsAdapter):
        self._adapter = adapter

    def execute(self, rule_id_or_name: str, view: str = "FULL") -> RuleDetail:
        resp = self._adapter.get_rule(rule_id_or_name=rule_id_or_name, view=view)
        return _map_rule_detail(resp)


class VerifyRuleWorkflow:
    """Workflow to compile/verify YARA-L rule text against Chronicle compiler."""

    def __init__(self, adapter: GoogleSecOpsAdapter):
        self._adapter = adapter

    def execute(self, rule_text: str) -> RuleValidationResult:
        resp = self._adapter.verify_rule_text(rule_text=rule_text)
        success = bool(resp.get("success", False))
        diag_raw = resp.get("compilationDiagnostics", [])
        diagnostics = [_map_diagnostic(d) for d in diag_raw]
        return RuleValidationResult(
            success=success,
            diagnostics=diagnostics,
            raw=resp,
        )


class CreateRuleWorkflow:
    """Workflow to create a new YARA-L detection rule in Chronicle SIEM."""

    def __init__(self, adapter: GoogleSecOpsAdapter):
        self._adapter = adapter

    def execute(self, rule_text: str) -> RuleDetail:
        resp = self._adapter.create_rule(rule_text=rule_text)
        return _map_rule_detail(resp)


class PatchRuleWorkflow:
    """Workflow to update an existing detection rule's YARA-L text."""

    def __init__(self, adapter: GoogleSecOpsAdapter):
        self._adapter = adapter

    def execute(
        self,
        rule_id_or_name: str,
        rule_text: str,
        update_mask: Optional[str] = None,
    ) -> RuleDetail:
        resp = self._adapter.patch_rule(
            rule_id_or_name=rule_id_or_name,
            rule_text=rule_text,
            update_mask=update_mask,
        )
        return _map_rule_detail(resp)


class DeleteRuleWorkflow:
    """Workflow to delete a detection rule from Chronicle SIEM."""

    def __init__(self, adapter: GoogleSecOpsAdapter):
        self._adapter = adapter

    def execute(self, rule_id_or_name: str) -> Dict[str, Any]:
        return self._adapter.delete_rule(rule_id_or_name=rule_id_or_name)


class ListRuleRevisionsWorkflow:
    """Workflow to list past revisions and version history of a rule."""

    def __init__(self, adapter: GoogleSecOpsAdapter):
        self._adapter = adapter

    def execute(
        self,
        rule_id_or_name: str,
        page_size: int = 100,
        page_token: Optional[str] = None,
    ) -> RuleRevisionListResult:
        resp = self._adapter.list_rule_revisions(
            rule_id_or_name=rule_id_or_name,
            page_size=page_size,
            page_token=page_token,
        )
        raw_rules = resp.get("rules", [])
        revisions = [_map_rule_detail(r) for r in raw_rules]
        return RuleRevisionListResult(
            rule_id=rule_id_or_name.split("/")[-1],
            revisions=revisions,
            next_page_token=resp.get("nextPageToken"),
            provenance={"count": len(revisions)},
        )


class GetRuleDeploymentWorkflow:
    """Workflow to fetch deployment and frequency status of a rule."""

    def __init__(self, adapter: GoogleSecOpsAdapter):
        self._adapter = adapter

    def execute(self, rule_id_or_name: str) -> RuleDeployment:
        resp = self._adapter.get_rule_deployment(rule_id_or_name=rule_id_or_name)
        return _map_rule_deployment(resp)


class UpdateRuleDeploymentWorkflow:
    """Workflow to update deployment properties (enabled, alerting, frequency)."""

    def __init__(self, adapter: GoogleSecOpsAdapter):
        self._adapter = adapter

    def execute(
        self,
        rule_id_or_name: str,
        enabled: Optional[bool] = None,
        alerting: Optional[bool] = None,
        run_frequency: Optional[str] = None,
        update_mask: Optional[str] = None,
    ) -> RuleDeployment:
        resp = self._adapter.update_rule_deployment(
            rule_id_or_name=rule_id_or_name,
            enabled=enabled,
            alerting=alerting,
            run_frequency=run_frequency,
            update_mask=update_mask,
        )
        return _map_rule_deployment(resp)


class ListRuleErrorsWorkflow:
    """Workflow to list execution and runtime errors across rules."""

    def __init__(self, adapter: GoogleSecOpsAdapter):
        self._adapter = adapter

    def execute(
        self,
        rule_id_or_name: Optional[str] = None,
        page_size: int = 100,
        page_token: Optional[str] = None,
    ) -> RuleExecutionErrorListResult:
        resp = self._adapter.list_rule_execution_errors(
            rule_id_or_name=rule_id_or_name,
            page_size=page_size,
            page_token=page_token,
        )
        raw_errors = resp.get("ruleExecutionErrors", [])
        errors = [_map_execution_error(e) for e in raw_errors]
        return RuleExecutionErrorListResult(
            errors=errors,
            next_page_token=resp.get("nextPageToken"),
            provenance={"count": len(errors), "rule_filter": rule_id_or_name},
        )
