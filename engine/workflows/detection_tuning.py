from __future__ import annotations

"""Detection Tuning and Findings Refinements Workflows for Google SecOps."""

from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING, Any, Dict, List, Optional
import re

if TYPE_CHECKING:
    from adapters.google_secops import GoogleSecOpsAdapter
from engine.domain import (
    DetectionTuningReport,
    DimensionCardinality,
    EntityCardinalityRecord,
    EntityCardinalityReport,
    FindingsRefinementBatch,
    FindingsRefinementSummary,
    FindingsRefinementTestResult,
    NoisyRuleRecord,
    NoisyRulesBatch,
    RuleCaseHistoryBatch,
    RuleCaseHistoryRecord,
)


def translate_to_udm_refinement(field_name: str, value: str, is_regex: bool = True) -> str:
    """Helper that formats a UDM field and value into findings refinement syntax.
    
    Example:
        >>> translate_to_udm_refinement("target.hostname", "byeserver.com", is_regex=True)
        '(target.hostname = /byeserver.com/)'
    """
    clean_field = field_name.strip().lstrip("$e.").lstrip("$")
    clean_val = value.strip()
    if is_regex:
        # Escape slashes
        escaped = clean_val.replace("/", "\\/")
        return f"({clean_field} = /{escaped}/)"
    return f'({clean_field} = "{clean_val}")'


class FindTopNoisyRulesWorkflow:
    """Executes the YARA-L detection noise aggregation query and ranks top alert generators."""

    def __init__(self, adapter: GoogleSecOpsAdapter):
        self.adapter = adapter

    def execute(
        self,
        lookback_days: int = 7,
        alert_state: str = "ALL",
        limit: int = 20,
    ) -> NoisyRulesBatch:
        query_text = """
$rule_name = detection.detection.rule_name
$rule_id = detection.detection.rule_id
$alerting = detection.detection.alert_state 
match: $rule_name, $rule_id, $alerting
outcome:
  $count = count(detection.id)
  $first_seen = min(detection.detection_time.seconds)
  $last_seen = max(detection.detection_time.seconds)
order: $count desc
"""
        res = self.adapter.execute_dashboard_query(
            query_text=query_text,
            time_unit="DAY",
            time_value=str(max(1, lookback_days)),
        )

        desired_alert = alert_state.strip().upper()
        records: List[NoisyRuleRecord] = []
        total_detections = 0

        for row in res.rows:
            r_name = row.get("rule_name") or ""
            r_id = row.get("rule_id") or ""
            r_alert = row.get("alerting") or "NOT_ALERTING"
            count_str = row.get("count") or "0"
            first_seen_str = row.get("first_seen") or "0"
            last_seen_str = row.get("last_seen") or "0"

            try:
                c_val = int(count_str)
            except (ValueError, TypeError):
                c_val = 0

            # Filter by alert_state if requested
            if desired_alert != "ALL" and r_alert.upper() != desired_alert:
                continue

            # Classify rule author origin
            if "ur_" in r_id:
                r_type = "GOOGLE_MANAGED"
            elif r_id.startswith("ru_"):
                r_type = "CUSTOMER"
            else:
                r_type = "OTHER"

            first_seen_dt = None
            last_seen_dt = None
            try:
                fs_sec = int(first_seen_str)
                if fs_sec > 0:
                    first_seen_dt = datetime.fromtimestamp(fs_sec, tz=timezone.utc)
            except (ValueError, TypeError):
                pass

            try:
                ls_sec = int(last_seen_str)
                if ls_sec > 0:
                    last_seen_dt = datetime.fromtimestamp(ls_sec, tz=timezone.utc)
            except (ValueError, TypeError):
                pass

            total_detections += c_val
            records.append(
                NoisyRuleRecord(
                    rule_id=r_id,
                    rule_name=r_name,
                    rule_type=r_type,
                    alert_state=r_alert,
                    detection_count=c_val,
                    first_seen=first_seen_dt,
                    last_seen=last_seen_dt,
                    raw=row,
                )
            )
            if len(records) >= limit:
                break

        return NoisyRulesBatch(
            rules=records,
            total_detections=total_detections,
            time_window=f"{lookback_days}d",
            raw=res.raw,
        )


class AnalyzeEntityCardinalityWorkflow:
    """Calculates field-level cardinality distributions across key UDM subfields for a rule."""

    STANDARD_DIMENSIONS: Dict[str, str] = {
        "principal_ip": "detection.collection_elements.references.event.principal.ip",
        "target_ip": "detection.collection_elements.references.event.target.ip",
        "src_ip": "detection.collection_elements.references.event.src.ip",
        "principal_hostname": "detection.collection_elements.references.event.principal.hostname",
        "target_hostname": "detection.collection_elements.references.event.target.hostname",
        "src_hostname": "detection.collection_elements.references.event.src.hostname",
        "principal_user": "detection.collection_elements.references.event.principal.user.userid",
        "target_user": "detection.collection_elements.references.event.target.user.userid",
        "process_cmdline": "detection.collection_elements.references.event.target.process.command_line",
        "process_path": "detection.collection_elements.references.event.target.process.file.full_path",
        "dns_query": "detection.collection_elements.references.event.network.dns.questions.name",
    }

    DIMENSION_GROUPS: Dict[str, List[str]] = {
        "ips": ["principal_ip", "target_ip", "src_ip"],
        "hostnames": ["principal_hostname", "target_hostname", "src_hostname"],
        "users": ["principal_user", "target_user"],
        "processes": ["process_cmdline", "process_path"],
        "all": [
            "principal_ip",
            "principal_hostname",
            "target_hostname",
            "principal_user",
            "process_cmdline",
            "dns_query",
        ],
    }

    def __init__(self, adapter: GoogleSecOpsAdapter):
        self.adapter = adapter

    def execute(
        self,
        rule_id: str,
        dimensions: Optional[List[str]] = None,
        lookback_days: int = 14,
        limit_per_dimension: int = 10,
    ) -> EntityCardinalityReport:
        clean_rule_id = rule_id.split("/")[-1].strip()

        # Resolve selected dimensions
        target_dims: List[tuple[str, str]] = []
        if not dimensions or "all" in dimensions:
            dim_names = self.DIMENSION_GROUPS["all"]
        else:
            dim_names = []
            for d in dimensions:
                d_lower = d.lower()
                if d_lower in self.DIMENSION_GROUPS:
                    dim_names.extend(self.DIMENSION_GROUPS[d_lower])
                elif d_lower in self.STANDARD_DIMENSIONS:
                    dim_names.append(d_lower)
                else:
                    # Allow custom path
                    dim_names.append(d)

        # De-duplicate preserving order
        seen = set()
        unique_dim_names = []
        for d in dim_names:
            if d not in seen:
                seen.add(d)
                unique_dim_names.append(d)

        for d_name in unique_dim_names:
            path = self.STANDARD_DIMENSIONS.get(d_name, d_name)
            target_dims.append((d_name, path))

        dimension_results: List[DimensionCardinality] = []

        for dim_name, subfield_path in target_dims:
            query = f"""
$val = {subfield_path}
$val != ""
$ruleId = detection.detection.rule_id
$ruleId = "{clean_rule_id}"
match: $val
outcome: $count = count(detection.id)
order: $count desc
limit: {limit_per_dimension}
"""
            try:
                res = self.adapter.execute_dashboard_query(
                    query_text=query,
                    time_unit="DAY",
                    time_value=str(max(1, lookback_days)),
                )
                records: List[EntityCardinalityRecord] = []
                for row in res.rows:
                    val = row.get("val") or ""
                    cnt_str = row.get("count") or "0"
                    try:
                        cnt = int(cnt_str)
                    except (ValueError, TypeError):
                        cnt = 0
                    if val:
                        records.append(EntityCardinalityRecord(value=val, count=cnt, raw=row))

                dimension_results.append(
                    DimensionCardinality(
                        dimension=dim_name,
                        subfield_path=subfield_path,
                        records=records,
                        total_distinct_values=len(records),
                    )
                )
            except Exception:
                # If a field is not indexed or supported for this event type, record empty
                dimension_results.append(
                    DimensionCardinality(
                        dimension=dim_name,
                        subfield_path=subfield_path,
                        records=[],
                        total_distinct_values=0,
                    )
                )

        return EntityCardinalityReport(
            rule_id=clean_rule_id,
            dimensions=dimension_results,
            time_window=f"{lookback_days}d",
        )


class CrossReferenceRuleCasesWorkflow:
    """Queries historical SOAR cases triggered by a rule to extract analyst resolutions."""

    def __init__(self, adapter: GoogleSecOpsAdapter):
        self.adapter = adapter

    def execute(
        self,
        rule_id: str,
        lookback_days: int = 90,
        limit: int = 20,
    ) -> RuleCaseHistoryBatch:
        clean_rule_id = rule_id.split("/")[-1].strip()

        case_query = f"""
$case_name = case.name
$case_display_name = case.display_name
$case_status = case.status
$case_closure_details_reason = case.closure_details.reason
$case_closure_details_root_cause = case.closure_details.root_cause
$rule_id = case.alerts.metadata.detection.rule_id 
$rule_id = "{clean_rule_id}"
match:
    $case_name, $case_display_name, $case_status, $case_closure_details_reason, $case_closure_details_root_cause, $rule_id
limit: {limit}
"""
        res = self.adapter.execute_dashboard_query(
            query_text=case_query,
            time_unit="DAY",
            time_value=str(max(1, lookback_days)),
        )

        cases: List[RuleCaseHistoryRecord] = []
        for row in res.rows:
            c_name = row.get("case_name") or ""
            c_disp = row.get("case_display_name") or ""
            c_status = row.get("case_status") or "UNKNOWN"
            c_reason = row.get("case_closure_details_reason") or ""
            c_root = row.get("case_closure_details_root_cause") or ""
            r_id = row.get("rule_id") or clean_rule_id

            cases.append(
                RuleCaseHistoryRecord(
                    case_name=c_name,
                    display_name=c_disp,
                    status=c_status,
                    close_reason=c_reason,
                    root_cause=c_root,
                    rule_id=r_id,
                    raw=row,
                )
            )

        return RuleCaseHistoryBatch(
            cases=cases,
            rule_id=clean_rule_id,
            total_cases=len(cases),
            raw=res.raw,
        )


class TestFindingsRefinementWorkflow:
    """Executes a dry-run test of a findings refinement exclusion against historical detections."""

    def __init__(self, adapter: GoogleSecOpsAdapter):
        self.adapter = adapter

    def execute(
        self,
        curated_rule_ids: List[str],
        query: str,
        lookback_days: int = 14,
        start_time: Optional[str] = None,
        end_time: Optional[str] = None,
    ) -> FindingsRefinementTestResult:
        if not start_time or not end_time:
            now = datetime.now(timezone.utc)
            start_dt = now - timedelta(days=max(1, lookback_days))
            start_time = start_dt.strftime("%Y-%m-%dT00:00:00.000Z")
            end_time = now.strftime("%Y-%m-%dT23:59:59.999Z")

        raw_list = self.adapter.test_findings_refinement(
            curated_rule_ids=curated_rule_ids,
            query=query,
            start_time=start_time,
            end_time=end_time,
        )

        total_count = 0
        excluded_count = 0
        rule_id_ref = curated_rule_ids[0] if curated_rule_ids else ""

        # Inspect activities array in response
        for item in raw_list:
            activity = item.get("activity", {})
            d_activity = activity.get("detectionExclusionActivity", {})
            detector_activities = d_activity.get("detectionExclusionDetectorActivities", [])
            for da in detector_activities:
                t_str = da.get("totalDetectionCount") or "0"
                e_str = da.get("excludedDetectionCount") or "0"
                c_rule = da.get("curatedRule") or rule_id_ref
                try:
                    t_val = int(t_str)
                    e_val = int(e_str)
                    if t_val > total_count:
                        total_count = t_val
                    if e_val > excluded_count:
                        excluded_count = e_val
                    if c_rule:
                        rule_id_ref = c_rule
                except (ValueError, TypeError):
                    pass

        ratio = (float(excluded_count) / float(total_count)) if total_count > 0 else 0.0

        return FindingsRefinementTestResult(
            curated_rule_id=rule_id_ref,
            query=query,
            total_detections=total_count,
            excluded_detections=excluded_count,
            suppression_ratio=ratio,
            raw=raw_list,
        )


class ManageFindingsRefinementsWorkflow:
    """Manages CRUD lifecycle for tenant UDM findings refinements and exclusions."""

    def __init__(self, adapter: GoogleSecOpsAdapter):
        self.adapter = adapter

    def list_refinements(self, page_size: int = 100) -> FindingsRefinementBatch:
        res = self.adapter.list_findings_refinements(page_size=page_size)
        items: List[FindingsRefinementSummary] = []
        for ref in res.get("findingsRefinements", []):
            name = ref.get("name", "")
            ref_id = name.split("/")[-1]
            disp = ref.get("displayName", "")
            q = ref.get("query", "")
            r_type = ref.get("type", "DETECTION_EXCLUSION")
            c_rules: List[str] = []
            dex = ref.get("detectionExclusionApplication", {})
            if isinstance(dex, dict) and "curatedRules" in dex:
                c_rules = dex.get("curatedRules") or []

            items.append(
                FindingsRefinementSummary(
                    id=ref_id,
                    name=name,
                    display_name=disp,
                    type=r_type,
                    query=q,
                    curated_rule_ids=c_rules,
                    raw=ref,
                )
            )

        return FindingsRefinementBatch(refinements=items, raw=res)

    def create_refinement(
        self,
        display_name: str,
        query: str,
        curated_rule_ids: Optional[List[str]] = None,
    ) -> FindingsRefinementSummary:
        res = self.adapter.create_findings_refinement(
            display_name=display_name,
            query=query,
            curated_rule_ids=curated_rule_ids,
        )
        name = res.get("name", "")
        ref_id = name.split("/")[-1]
        return FindingsRefinementSummary(
            id=ref_id,
            name=name,
            display_name=res.get("displayName", display_name),
            type=res.get("type", "DETECTION_EXCLUSION"),
            query=res.get("query", query),
            curated_rule_ids=curated_rule_ids or [],
            raw=res,
        )

    def delete_refinement(self, refinement_id: str) -> Dict[str, Any]:
        return self.adapter.delete_findings_refinement(refinement_id)


class DiagnoseAndTuneDetectionWorkflow:
    """Autonomous end-to-end detection tuning workflow."""

    def __init__(
        self,
        adapter: GoogleSecOpsAdapter,
        cardinality_wf: AnalyzeEntityCardinalityWorkflow,
        case_wf: CrossReferenceRuleCasesWorkflow,
        test_wf: TestFindingsRefinementWorkflow,
    ):
        self.adapter = adapter
        self.cardinality_wf = cardinality_wf
        self.case_wf = case_wf
        self.test_wf = test_wf

    def execute(
        self,
        rule_id: str,
        lookback_days: int = 7,
    ) -> DetectionTuningReport:
        clean_rule_id = rule_id.split("/")[-1].strip()
        is_curated = "ur_" in clean_rule_id

        rule_name = ""
        rule_text = ""
        rule_type = "GOOGLE_MANAGED" if is_curated else "CUSTOMER"

        # 1. Fetch rule logic
        if is_curated:
            rule_data = self.adapter.get_featured_content_rule(clean_rule_id)
            if rule_data:
                meta = rule_data.get("contentMetadata") or {}
                rule_name = (
                    rule_data.get("displayName")
                    or meta.get("displayName")
                    or rule_data.get("ruleId")
                    or clean_rule_id
                )
                rule_text = rule_data.get("ruleText") or ""
        else:
            rule_res = self.adapter.get_rule(clean_rule_id)
            if rule_res:
                rule_name = rule_res.get("displayName") or clean_rule_id
                rule_text = rule_res.get("text") or ""

        # 2. Extract entity distributions
        cardinality_report = self.cardinality_wf.execute(
            rule_id=clean_rule_id,
            lookback_days=lookback_days,
            limit_per_dimension=5,
        )

        # 3. Cross-reference cases
        case_history = self.case_wf.execute(
            rule_id=clean_rule_id,
            lookback_days=90,
            limit=5,
        )

        # 4. Identify the single most impactful entity to exclude
        top_field = ""
        top_val = ""
        top_count = 0
        for dim in cardinality_report.dimensions:
            for rec in dim.records:
                if rec.count > top_count:
                    top_count = rec.count
                    top_val = rec.value
                    # Map dimension to UDM field for refinement
                    if "event." in dim.subfield_path:
                        top_field = dim.subfield_path.split("event.")[-1]
                    elif "_ip" in dim.dimension or dim.dimension.endswith("ip"):
                        top_field = "principal.ip" if "principal" in dim.dimension else "target.ip"
                    elif "hostname" in dim.dimension:
                        top_field = "principal.hostname" if "principal" in dim.dimension else "target.hostname"
                    elif "user" in dim.dimension:
                        top_field = "principal.user.userid"
                    elif "dns" in dim.dimension:
                        top_field = "network.dns.questions.name"
                    elif "process" in dim.dimension:
                        top_field = "target.process.command_line"
                    else:
                        top_field = dim.dimension

        # 5. Formulate candidate exclusion
        proposed_refinement = ""
        test_result: Optional[FindingsRefinementTestResult] = None
        validation_errors: List[str] = []

        if top_field and top_val:
            proposed_refinement = translate_to_udm_refinement(top_field, top_val, is_regex=True)
            if is_curated:
                try:
                    test_result = self.test_wf.execute(
                        curated_rule_ids=[clean_rule_id],
                        query=proposed_refinement,
                        lookback_days=lookback_days,
                    )
                except Exception as e:
                    validation_errors.append(f"Dry-run test error: {str(e)}")

        val_status = "VALIDATED" if not validation_errors and (test_result or not is_curated) else "ERROR"

        return DetectionTuningReport(
            rule_id=clean_rule_id,
            rule_name=rule_name,
            rule_type=rule_type,
            rule_text=rule_text,
            total_detections_baseline=top_count,
            entity_cardinality=cardinality_report,
            linked_cases=case_history,
            proposed_refinement_query=proposed_refinement,
            dry_run_impact=test_result,
            validation_status=val_status,
            validation_errors=validation_errors,
        )
