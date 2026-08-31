"""Rule & Detection Health Audit Workflow.

Orchestrates comprehensive health auditing for Chronicle YARA-L detection rules,
curated rulesets, compilation errors, execution errors, latency observability,
and detection decay across Google SecOps.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Set

if TYPE_CHECKING:
    from adapters.google_secops import GoogleSecOpsAdapter

from engine.domain import (
    RuleHealthFinding,
    RuleHealthReport,
    RuleHealthStatus,
    RuleSummary,
    RuleDetail,
    RuleExecutionError,
)
from engine.workflows.dashboards import (
    ExecuteDashboardQueryWorkflow,
    GetDashboardDetailWorkflow,
)
from engine.workflows.detection_rules import (
    ListRulesWorkflow,
    ListRuleErrorsWorkflow,
    GetRuleWorkflow,
)

logger = logging.getLogger(__name__)

RULE_DETECTIONS_OVERVIEW_DASHBOARD_ID = "8c706509-d2c9-4f1c-9572-5f96f10e0df6"
RULE_OBSERVABILITY_DASHBOARD_ID = "ede65743-5a8f-4c80-bc31-ebdf9797b2ce"


class AuditRuleHealthWorkflow:
    """Orchestrates comprehensive posture auditing for Chronicle YARA-L rules and curated rulesets."""

    def __init__(self, adapter: GoogleSecOpsAdapter):
        self.adapter = adapter

    def execute(
        self,
        include_curated: bool = True,
        latency_threshold_min: float = 30.0,
        page_size: int = 100,
    ) -> RuleHealthReport:
        """Executes full rule health audit correlating live rules, errors, and dashboard telemetry."""
        # 1. Fetch custom rules
        list_rules_wf = ListRulesWorkflow(self.adapter)
        custom_rules_res = list_rules_wf.execute(page_size=page_size)
        rules = custom_rules_res.rules

        # 2. Fetch execution errors
        list_errors_wf = ListRuleErrorsWorkflow(self.adapter)
        errors_res = list_errors_wf.execute(page_size=100)
        errors = errors_res.errors

        # Map errors by rule id or name
        errors_by_rule: Dict[str, List[RuleExecutionError]] = {}
        for err in errors:
            r_key = (err.rule_resource_name or "").split("/")[-1].lower()
            if not r_key and err.curated_rule:
                r_key = err.curated_rule.split("/")[-1].lower()
            if r_key:
                errors_by_rule.setdefault(r_key, []).append(err)

        # 3. Collect Telemetry from Rule Detections Overview & Rule Observability
        telemetry = self._collect_rule_dashboard_telemetry()

        # 4. Evaluate each rule
        findings: List[RuleHealthFinding] = []
        healthy_count = 0
        failing_count = 0
        decay_count = 0
        latency_alert_count = 0
        misconfigured_count = 0
        disabled_count = 0

        # Correlate custom rules
        for rule in rules:
            finding = self._evaluate_rule(
                rule=rule,
                errors_by_rule=errors_by_rule,
                telemetry=telemetry,
                latency_threshold_min=latency_threshold_min,
            )
            findings.append(finding)

            if finding.status == RuleHealthStatus.HEALTHY:
                healthy_count += 1
            elif finding.status in (RuleHealthStatus.EXECUTION_ERROR, RuleHealthStatus.COMPILATION_ERROR):
                failing_count += 1
            elif finding.status == RuleHealthStatus.SILENT_DECAY:
                decay_count += 1
            elif finding.status == RuleHealthStatus.HIGH_LATENCY:
                latency_alert_count += 1
            elif finding.status == RuleHealthStatus.MISCONFIGURED_ALERTING:
                misconfigured_count += 1
            elif finding.status == RuleHealthStatus.DISABLED:
                disabled_count += 1

        # Optionally correlate curated rulesets if requested
        if include_curated:
            curated_findings = self._evaluate_curated_rulesets(telemetry=telemetry)
            for cf in curated_findings:
                findings.append(cf)
                if cf.status == RuleHealthStatus.HEALTHY:
                    healthy_count += 1
                elif cf.status in (RuleHealthStatus.EXECUTION_ERROR, RuleHealthStatus.COMPILATION_ERROR):
                    failing_count += 1
                elif cf.status == RuleHealthStatus.SILENT_DECAY:
                    decay_count += 1
                elif cf.status == RuleHealthStatus.DISABLED:
                    disabled_count += 1

        return RuleHealthReport(
            findings=findings,
            healthy_count=healthy_count,
            failing_count=failing_count,
            decay_count=decay_count,
            latency_alert_count=latency_alert_count,
            misconfigured_count=misconfigured_count,
            disabled_count=disabled_count,
            total_rules_audited=len(findings),
            total_detections_24h=telemetry.get("total_detections", 0),
            average_risk_score=telemetry.get("average_risk_score", 0.0),
            top_mitre_tactics=telemetry.get("top_mitre_tactics", []),
            top_threat_categories=telemetry.get("top_threat_categories", []),
            generated_at=datetime.now(timezone.utc),
        )

    def _evaluate_rule(
        self,
        rule: RuleSummary,
        errors_by_rule: Dict[str, List[RuleExecutionError]],
        telemetry: Dict[str, Any],
        latency_threshold_min: float,
    ) -> RuleHealthFinding:
        """Evaluates health status, latency, detection volume, and error diagnostics for a rule."""
        rule_id = rule.name.split("/")[-1] if rule.name else ""
        rule_id_lower = rule_id.lower()
        rule_display_lower = (rule.display_name or "").lower()

        # Check execution errors
        rule_errors = errors_by_rule.get(rule_id_lower, [])
        if not rule_errors and rule_display_lower:
            rule_errors = errors_by_rule.get(rule_display_lower, [])

        last_error_msg = rule_errors[0].error_message if rule_errors else None
        exec_error_count = len(rule_errors)

        # Check telemetry detection counts
        detection_counts_by_name = telemetry.get("detection_counts_by_name", {})
        detection_count = detection_counts_by_name.get(rule_display_lower, 0)
        if detection_count == 0:
            detection_count = detection_counts_by_name.get(rule_id_lower, 0)

        # Check latency telemetry
        latencies_by_name = telemetry.get("latencies_by_name", {})
        lat_info = latencies_by_name.get(rule_display_lower) or latencies_by_name.get(rule_id_lower)
        ingestion_latency = lat_info.get("ingestion_to_detection") if lat_info else None
        event_latency = lat_info.get("event_to_detection") if lat_info else None

        # Check least active decay set
        least_active_set = telemetry.get("least_active_rules", set())
        is_in_decay_set = (rule_display_lower in least_active_set) or (rule_id_lower in least_active_set)

        # Determine status and remediation
        remediations: List[str] = []
        status = RuleHealthStatus.HEALTHY
        details = "Rule is operating normally."

        # Deployment & enabled status
        is_enabled = bool(rule.run_frequency in ("LIVE", "HOURLY", "DAILY") or rule.raw.get("enabled", True))
        is_alerting = bool(rule.raw.get("alerting", True))

        if not is_enabled:
            status = RuleHealthStatus.DISABLED
            details = f"Rule '{rule.display_name}' is currently disabled or has no active run frequency."
            remediations.append("Review rule logic and enable rule execution if detection coverage is required.")
        elif exec_error_count > 0:
            status = RuleHealthStatus.EXECUTION_ERROR
            details = f"Rule encountered {exec_error_count} runtime execution error(s). Last error: {last_error_msg}"
            remediations.append(f"Inspect YARA-L logic for runtime evaluation errors: {last_error_msg}")
            remediations.append("Validate rule against test events using VerifyRule workflow.")
        elif ingestion_latency is not None and ingestion_latency > latency_threshold_min:
            status = RuleHealthStatus.HIGH_LATENCY
            details = f"Rule detection latency is {ingestion_latency:.1f} min (threshold: {latency_threshold_min} min)."
            remediations.append("Optimize YARA-L condition window duration (e.g. reduce match window or narrow events).")
            remediations.append("Ensure joins utilize indexed UDM fields (e.g. principal.hostname, target.user.userid).")
        elif is_in_decay_set and detection_count == 0:
            status = RuleHealthStatus.SILENT_DECAY
            details = f"Rule '{rule.display_name}' is flagged in Least Active Rules with 0 detections."
            remediations.append("Verify if upstream log sources mapped to this rule are still ingesting active telemetry.")
            remediations.append("Review rule conditions against recent UDM events to check for schema drift or stale values.")
        elif not is_alerting and is_enabled:
            status = RuleHealthStatus.MISCONFIGURED_ALERTING
            details = f"Rule '{rule.display_name}' is executing but alerting is disabled."
            remediations.append("Enable alerting on rule deployment if detection notifications should generate alerts/cases.")

        return RuleHealthFinding(
            rule_id=rule_id,
            display_name=rule.display_name or rule_id,
            rule_owner="CUSTOMER",
            severity=rule.severity or "MEDIUM",
            status=status,
            enabled=is_enabled,
            alerting=is_alerting,
            run_frequency=rule.run_frequency or "LIVE",
            detection_count_recent=detection_count,
            execution_error_count=exec_error_count,
            last_error_message=last_error_msg,
            ingestion_to_detection_latency_min=ingestion_latency,
            event_to_detection_latency_min=event_latency,
            details=details,
            remediation_steps=remediations,
            raw=rule.raw,
        )

    def _evaluate_curated_rulesets(self, telemetry: Dict[str, Any]) -> List[RuleHealthFinding]:
        """Evaluates status of Google curated ruleset categories and deployments."""
        curated_findings: List[RuleHealthFinding] = []
        try:
            if hasattr(self.adapter, "list_curated_rulesets"):
                resp = self.adapter.list_curated_rulesets()
                rulesets = resp.get("curatedRuleSets", []) or resp.get("ruleSets", [])
                for rs in rulesets:
                    rs_id = rs.get("name", "").split("/")[-1] or rs.get("id", "")
                    title = rs.get("title") or rs.get("displayName") or rs_id
                    enabled = bool(rs.get("enabled", False) or rs.get("deploymentState") == "ENABLED")
                    alerting = bool(rs.get("alerting", False))

                    status = RuleHealthStatus.HEALTHY if enabled else RuleHealthStatus.DISABLED
                    details = "Curated ruleset is enabled and active." if enabled else "Curated ruleset is disabled."
                    remediations = []
                    if not enabled:
                        remediations.append(f"Enable curated ruleset '{title}' to activate Google out-of-the-box detection coverage.")

                    curated_findings.append(
                        RuleHealthFinding(
                            rule_id=rs_id,
                            display_name=title,
                            rule_owner="GOOGLE",
                            severity="HIGH",
                            status=status,
                            enabled=enabled,
                            alerting=alerting,
                            run_frequency="LIVE",
                            details=details,
                            remediation_steps=remediations,
                            raw=rs,
                        )
                    )
        except Exception as exc:
            logger.warning(f"Could not audit curated rulesets: {exc}")

        return curated_findings

    def _collect_rule_dashboard_telemetry(self) -> Dict[str, Any]:
        """Extracts detection counts, latencies, MITRE tactics, and decay metrics from native dashboards."""
        telemetry: Dict[str, Any] = {
            "detection_counts_by_name": {},
            "latencies_by_name": {},
            "least_active_rules": set(),
            "top_mitre_tactics": [],
            "top_threat_categories": [],
            "average_risk_score": 0.0,
            "total_detections": 0,
        }

        # Query 1: Rule Detections Overview Dashboard
        try:
            get_dash_wf = GetDashboardDetailWorkflow(self.adapter)
            overview_dash = get_dash_wf.execute(RULE_DETECTIONS_OVERVIEW_DASHBOARD_ID, include_queries=False)
            exec_wf = ExecuteDashboardQueryWorkflow(self.adapter)

            for chart in overview_dash.charts:
                q_name = chart.query_name or chart.raw.get("chartDatasource", {}).get("dashboardQuery")
                if not q_name:
                    continue

                c_name = (chart.display_name or "").lower()

                # Target Top Active Rules
                if "top 10 active rules" in c_name:
                    try:
                        res = exec_wf.execute(query_name_or_id=q_name)
                        for row in res.rows:
                            r_name = (row.get("Rulename") or row.get("rule_name") or "").lower()
                            count_val = int(row.get("Count") or row.get("count") or 0)
                            if r_name:
                                telemetry["detection_counts_by_name"][r_name] = count_val
                                telemetry["total_detections"] += count_val
                    except Exception as e:
                        logger.debug(f"Failed to execute Top Active Rules query: {e}")

                # Target Least Active Rules
                elif "least 10 active rules" in c_name:
                    try:
                        res = exec_wf.execute(query_name_or_id=q_name)
                        for row in res.rows:
                            r_name = (row.get("Rulename") or row.get("rule_name") or "").lower()
                            if r_name:
                                telemetry["least_active_rules"].add(r_name)
                    except Exception as e:
                        logger.debug(f"Failed to execute Least Active Rules query: {e}")

                # Target Average Risk Score
                elif "average risk score" in c_name:
                    try:
                        res = exec_wf.execute(query_name_or_id=q_name)
                        if res.rows:
                            score_val = float(res.rows[0].get("Average_Risk_Score") or res.rows[0].get("risk_score") or 0.0)
                            telemetry["average_risk_score"] = score_val
                    except Exception as e:
                        logger.debug(f"Failed to execute Average Risk Score query: {e}")

                # Target MITRE Tactics
                elif "mitre" in c_name:
                    try:
                        res = exec_wf.execute(query_name_or_id=q_name)
                        telemetry["top_mitre_tactics"] = res.rows[:10]
                    except Exception as e:
                        logger.debug(f"Failed to execute MITRE query: {e}")

                # Target Threat Categories
                elif "threat categories" in c_name:
                    try:
                        res = exec_wf.execute(query_name_or_id=q_name)
                        telemetry["top_threat_categories"] = res.rows[:10]
                    except Exception as e:
                        logger.debug(f"Failed to execute Threat Categories query: {e}")

        except Exception as exc:
            logger.warning(f"Could not query Rule Detections Overview dashboard: {exc}")

        # Query 2: Rule Observability Dashboard
        try:
            get_dash_wf = GetDashboardDetailWorkflow(self.adapter)
            obs_dash = get_dash_wf.execute(RULE_OBSERVABILITY_DASHBOARD_ID, include_queries=False)
            exec_wf = ExecuteDashboardQueryWorkflow(self.adapter)

            for chart in obs_dash.charts:
                q_name = chart.query_name or chart.raw.get("chartDatasource", {}).get("dashboardQuery")
                if not q_name:
                    continue

                c_name = (chart.display_name or "").lower()
                if "per-detection latency" in c_name or "latency numbers" in c_name:
                    try:
                        res = exec_wf.execute(query_name_or_id=q_name)
                        for row in res.rows:
                            r_name = (row.get("rule_name") or row.get("Rulename") or "").lower()
                            ingest_to_det = float(row.get("ingestion_to_detection") or 0.0)
                            event_to_det = float(row.get("event_to_deteciton") or row.get("event_to_detection") or 0.0)
                            if r_name:
                                telemetry["latencies_by_name"][r_name] = {
                                    "ingestion_to_detection": ingest_to_det,
                                    "event_to_detection": event_to_det,
                                    "detect_id": row.get("detect_id", ""),
                                }
                    except Exception as e:
                        logger.debug(f"Failed to execute Per-Detection Latency query: {e}")

        except Exception as exc:
            logger.warning(f"Could not query Rule Observability dashboard: {exc}")

        return telemetry
