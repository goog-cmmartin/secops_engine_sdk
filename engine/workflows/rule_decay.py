"""Detection Rule Decay Audit & Telemetry Ingestion Workflow.

Orchestrates continuous evaluation of YARA-L detection rule decay,
Decay Prioritization Scoring (DPS), 90-day telemetry aggregations via dashboardQueries:execute,
and live UDM field population auditing against Google SecOps.
"""

from __future__ import annotations

from datetime import datetime, timezone
import logging
import re
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Set, Tuple

if TYPE_CHECKING:
    from adapters.google_secops import GoogleSecOpsAdapter

from engine.domain import (
    RuleDecayAssessment,
    RuleDecayReport,
    RuleDetail,
    RuleSummary,
)

logger = logging.getLogger(__name__)

# Validated Chronicle detection schema query for aggregating detection volume by rule ID
AUTHORITATIVE_DETECTION_COUNTS_QUERY = """$rule_id = detection.detection.rule_id
$rule_name = detection.detection.rule_name
match:
    $rule_id, $rule_name
outcome:
    $count = count_distinct(detection.id)
    $first_seen = timestamp.get_timestamp(min(detection.detection_time.seconds))
    $last_seen = timestamp.get_timestamp(max(detection.detection_time.seconds))
order:
    $count desc
limit:
    10000"""

# Regex to isolate events: and outcome: sections in YARA-L 2.0
EVENTS_BLOCK_REGEX = re.compile(r"events:\s*(.*?)(?:match:|outcome:|condition:|options:|\Z)", re.DOTALL | re.IGNORECASE)
OUTCOME_BLOCK_REGEX = re.compile(r"outcome:\s*(.*?)(?:condition:|options:|\Z)", re.DOTALL | re.IGNORECASE)

# Regex matching UDM event field paths prefixed by variable bindings (e.g., $e.principal.process.file.full_path)
UDM_FIELD_REGEX = re.compile(
    r"\$[a-zA-Z0-9_]+\.((?:metadata|principal|target|src|about|security_result|observer|network|intermediary)(?:\.[a-zA-Z0-9_]+)+)"
)


def extract_udm_fields_from_yaral(rule_text: str) -> List[str]:
    """Extracts all referenced UDM field paths from YARA-L 2.0 rule text.

    Scans the events: and outcome: sections for canonical UDM namespaces.

    Args:
        rule_text: The complete YARA-L rule text string.

    Returns:
        Sorted list of unique UDM field paths (e.g. ['principal.process.file.full_path', 'target.user.userid']).
    """
    if not rule_text:
        return []

    fields: Set[str] = set()

    # Search in events: block
    ev_match = EVENTS_BLOCK_REGEX.search(rule_text)
    if ev_match:
        for match in UDM_FIELD_REGEX.finditer(ev_match.group(1)):
            fields.add(match.group(1))

    # Search in outcome: block
    out_match = OUTCOME_BLOCK_REGEX.search(rule_text)
    if out_match:
        for match in UDM_FIELD_REGEX.finditer(out_match.group(1)):
            fields.add(match.group(1))

    # Fallback to full rule text if blocks could not be delineated
    if not fields:
        for match in UDM_FIELD_REGEX.finditer(rule_text):
            fields.add(match.group(1))

    return sorted(list(fields))


def calculate_decay_score(
    rule_detail: Any,
    detection_telemetry_90d: Optional[Dict[str, Any]] = None,
    unpopulated_fields: Optional[List[str]] = None,
    syntax_verified: bool = True,
    compiler_diagnostics: Optional[List[str]] = None,
) -> Tuple[int, List[str], str, int]:
    """Computes the Decay Prioritization Score (DPS: 0-100) and operational classification.

    Scoring Model:
      - Base Weight:
          Broken Compilation (+40), Silent (+30), Unpopulated (+20), Healthy (+5).
      - Operational Weight:
          Live/Enabled rule (+30).
      - Staleness Bonus:
          >365 days unrevised (+30), >180 days (+15), >90 days (+5).

    Args:
        rule_detail: Rule domain object or dictionary with metadata and timestamps.
        detection_telemetry_90d: Telemetry dictionary with detection_count, first_seen, last_seen.
        unpopulated_fields: List of UDM fields in the rule with 0 observed events in telemetry.
        syntax_verified: Whether the rule text passed live Chronicle compilation.
        compiler_diagnostics: Optional list of compiler diagnostic messages.

    Returns:
        Tuple of (dps_score, decay_flags, recommendation, days_stale).
    """
    flags: List[str] = []
    base_weight = 0

    # 1. Broken compilation check
    has_compilation_error = not syntax_verified
    if not has_compilation_error and compiler_diagnostics:
        for diag in compiler_diagnostics:
            diag_str = str(diag).lower()
            if "error" in diag_str or "fail" in diag_str:
                has_compilation_error = True
                break

    if has_compilation_error:
        base_weight += 40
        flags.append("BROKEN_COMPILATION")

    # 2. Operational / Live status check
    is_live = False
    if hasattr(rule_detail, "live_mode_enabled"):
        is_live = bool(rule_detail.live_mode_enabled)
    elif hasattr(rule_detail, "deployment_state"):
        is_live = str(rule_detail.deployment_state).upper() in ("LIVE", "ENABLED")
    elif isinstance(rule_detail, dict):
        is_live = bool(rule_detail.get("live_mode_enabled") or rule_detail.get("liveModeEnabled") or rule_detail.get("deployment_state") == "LIVE")

    operational_weight = 30 if is_live else 0

    # 3. 90-day detection count / Silence check
    count_90d = 0
    if detection_telemetry_90d:
        count_90d = int(detection_telemetry_90d.get("count", 0))

    if is_live and count_90d == 0:
        base_weight += 30
        flags.append("SILENT")

    # 4. Unpopulated UDM fields check
    unpop = unpopulated_fields or []
    if unpop:
        base_weight += 20
        flags.append("UNPOPULATED")

    if not flags:
        base_weight += 5
        flags.append("HEALTHY")

    # 5. Staleness calculation
    days_stale = 0
    now = datetime.now(timezone.utc)
    rev_time_str = None

    if hasattr(rule_detail, "revision_create_time") and rule_detail.revision_create_time:
        rev_time_str = str(rule_detail.revision_create_time)
    elif hasattr(rule_detail, "create_time") and rule_detail.create_time:
        rev_time_str = str(rule_detail.create_time)
    elif isinstance(rule_detail, dict):
        rev_time_str = rule_detail.get("revision_create_time") or rule_detail.get("revisionCreateTime") or rule_detail.get("create_time") or rule_detail.get("createTime")

    if rev_time_str:
        try:
            clean_ts = rev_time_str.replace("Z", "+00:00")
            parsed_dt = datetime.fromisoformat(clean_ts)
            if parsed_dt.tzinfo is None:
                parsed_dt = parsed_dt.replace(tzinfo=timezone.utc)
            delta = now - parsed_dt
            days_stale = max(0, delta.days)
        except Exception:
            days_stale = 0

    staleness_bonus = 0
    if days_stale >= 365:
        staleness_bonus = 30
        flags.append("STALE")
    elif days_stale >= 180:
        staleness_bonus = 15
        flags.append("STALE")
    elif days_stale >= 90:
        staleness_bonus = 5
        flags.append("STALE")

    # Compute total DPS clamped to [0, 100]
    total_dps = min(100, max(0, base_weight + operational_weight + staleness_bonus))

    # Determine recommended action
    if "BROKEN_COMPILATION" in flags or "UNPOPULATED" in flags:
        recommendation = "REFACTOR"
    elif "STALE" in flags and "SILENT" in flags:
        recommendation = "ARCHIVE"
    elif total_dps >= 60:
        recommendation = "REFACTOR"
    else:
        recommendation = "KEEP_ACTIVE"

    return total_dps, flags, recommendation, days_stale


class QueryRuleDetectionCountsWorkflow:
    """Executes the authoritative SecOps detection count aggregation query over 90 days."""

    def __init__(self, adapter: GoogleSecOpsAdapter):
        self.adapter = adapter

    def execute(self, lookback_days: int = 90) -> Dict[str, Dict[str, Any]]:
        """Queries 90-day detection counts for all rules in the tenant.

        Returns:
            Dictionary mapping rule_id to telemetry dict:
            {
               "ru_123": {
                   "rule_id": "ru_123",
                   "rule_name": "Suspicious PowerShell Execution",
                   "count": 42,
                   "first_seen": "2026-06-20T10:00:00Z",
                   "last_seen": "2026-09-19T14:30:00Z"
               }
            }
        """
        results_by_rule: Dict[str, Dict[str, Any]] = {}
        try:
            query_res = self.adapter.execute_dashboard_query(
                query_text=AUTHORITATIVE_DETECTION_COUNTS_QUERY,
                time_unit="DAY",
                time_value=str(lookback_days),
                dialect="YL2",
            )
            for row in getattr(query_res, "rows", []):
                rule_id = str(row.get("rule_id") or row.get("$rule_id") or "")
                if not rule_id:
                    continue
                rule_name = str(row.get("rule_name") or row.get("$rule_name") or "")
                raw_count = row.get("count") or row.get("$count") or 0
                first_seen = str(row.get("first_seen") or row.get("$first_seen") or "")
                last_seen = str(row.get("last_seen") or row.get("$last_seen") or "")

                try:
                    count_val = int(raw_count)
                except (ValueError, TypeError):
                    count_val = 0

                results_by_rule[rule_id] = {
                    "rule_id": rule_id,
                    "rule_name": rule_name,
                    "count": count_val,
                    "first_seen": first_seen if first_seen else None,
                    "last_seen": last_seen if last_seen else None,
                }
        except Exception as e:
            logger.warning("Failed executing authoritative detection counts query: %s", e)

        return results_by_rule


class AuditUdmFieldPopulationWorkflow:
    """Audits live UDM field population for detection rule telemetry."""

    def __init__(self, adapter: Optional[GoogleSecOpsAdapter] = None):
        self.adapter = adapter

    def _build_field_population_query(
        self,
        path: str,
        vendor_product: Optional[str] = None,
        is_array: bool = False,
    ) -> str:
        filter_clause = f"$e.{path} = /.+/" if is_array else f'$e.{path} != ""'
        vendor_filter = f' and $e.metadata.product_name = "{vendor_product}"' if vendor_product else ""
        return f"""$field_val = $e.{path}
match:
    $field_val
events:
    {filter_clause}{vendor_filter}
outcome:
    $count = count_distinct($e.metadata.id)
limit:
    10"""

    def execute(
        self,
        field_paths: List[str],
        vendor_product: Optional[str] = None,
        lookback_days: int = 30,
        schema_cache: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Dict[str, Any]]:
        """Checks whether given UDM fields contain values in live events over lookback_days.

        Args:
            field_paths: List of UDM field paths (e.g. ['principal.process.file.full_path']).
            vendor_product: Optional vendor/product scope to avoid cross-product false negatives.
            lookback_days: Number of days to audit.
            schema_cache: Optional dictionary or Firestore client for self-healing schema types.

        Returns:
            Dictionary mapping field_path to audit result:
            {
               "principal.process.file.full_path": {
                   "populated": True,
                   "count": 1420,
                   "is_array": False,
                   "error": None
               }
            }
        """
        audit_results: Dict[str, Dict[str, Any]] = {}
        for path in field_paths:
            is_array = False
            if schema_cache and hasattr(schema_cache, "get_udm_field_schema"):
                cached = schema_cache.get_udm_field_schema(path)
                if cached:
                    is_array = cached.get("is_array", False)

            query_text = self._build_field_population_query(
                path=path,
                vendor_product=vendor_product,
                is_array=is_array,
            )

            try:
                res = self.adapter.execute_dashboard_query(
                    query_text=query_text,
                    time_unit="DAY",
                    time_value=str(lookback_days),
                    dialect="YL2",
                )
                rows = getattr(res, "rows", [])
                total_events = 0
                for r in rows:
                    cnt = r.get("count") or r.get("$count") or 0
                    try:
                        total_events += int(cnt)
                    except (ValueError, TypeError):
                        pass

                audit_results[path] = {
                    "populated": total_events > 0,
                    "count": total_events,
                    "is_array": is_array,
                    "error": None,
                }
            except Exception as query_err:
                err_msg = str(query_err)
                logger.info("Field check error for %s: %s", path, err_msg)
                
                # Self-healing: if error indicates array or repeated field, update cache and retry with array syntax
                if "array" in err_msg.lower() or "repeated" in err_msg.lower():
                    if schema_cache and hasattr(schema_cache, "save_udm_field_schema"):
                        schema_cache.save_udm_field_schema(path, {
                            "field_path": path,
                            "is_array": True,
                            "discovered_at": datetime.now(timezone.utc).isoformat(),
                        })
                    retry_query = f"""$field_val = $e.{path}
match:
    $field_val
events:
    $e.{path} = /.+/{vendor_filter}
outcome:
    $count = count_distinct($e.metadata.id)
limit:
    10"""
                    try:
                        retry_res = self.adapter.execute_dashboard_query(
                            query_text=retry_query,
                            time_unit="DAY",
                            time_value=str(lookback_days),
                            dialect="YL2",
                        )
                        retry_rows = getattr(retry_res, "rows", [])
                        total_events = len(retry_rows)
                        audit_results[path] = {
                            "populated": total_events > 0,
                            "count": total_events,
                            "is_array": True,
                            "error": None,
                        }
                        continue
                    except Exception as retry_err:
                        audit_results[path] = {
                            "populated": False,
                            "count": 0,
                            "is_array": True,
                            "error": str(retry_err),
                        }
                        continue

                audit_results[path] = {
                    "populated": False,
                    "count": 0,
                    "is_array": is_array,
                    "error": err_msg,
                }

        return audit_results


class AuditRuleDecayWorkflow:
    """Orchestrates comprehensive tenant-wide or single-rule decay auditing."""

    def __init__(self, adapter: GoogleSecOpsAdapter):
        self.adapter = adapter

    def execute(
        self,
        rule_id: Optional[str] = None,
        lookback_days: int = 90,
        check_population: bool = True,
        schema_cache: Optional[Any] = None,
    ) -> RuleDecayReport:
        """Executes full detection rule decay audit correlating inventory, 90d telemetry, and UDM checks."""
        telemetry_wf = QueryRuleDetectionCountsWorkflow(self.adapter)
        telemetry_map = telemetry_wf.execute(lookback_days=lookback_days)

        target_rules: List[Any] = []
        if rule_id:
            try:
                rule_detail = self.adapter.get_rule(rule_id, view="FULL")
                target_rules.append(rule_detail)
            except Exception as e:
                logger.error("Failed fetching rule %s for decay audit: %s", rule_id, e)
        else:
            try:
                rules_res = self.adapter.list_rules(page_size=100, view="FULL")
                if isinstance(rules_res, dict):
                    target_rules = rules_res.get("rules", [])
                else:
                    target_rules = getattr(rules_res, "rules", []) or []
            except Exception as e:
                logger.error("Failed listing rules for decay audit: %s", e)

        assessments: List[RuleDecayAssessment] = []
        broken_count = 0
        silent_count = 0
        stale_count = 0
        unpopulated_count = 0

        for r in target_rules:
            curr_id = (
                getattr(r, "rule_id", "")
                or getattr(r, "id", "")
                or (r.get("rule_id") if isinstance(r, dict) else "")
                or (r.get("id") if isinstance(r, dict) else "")
            )
            if not curr_id:
                raw_name = getattr(r, "name", "") or (r.get("name") if isinstance(r, dict) else "")
                if raw_name:
                    curr_id = raw_name.split("/")[-1].split("@")[0]

            curr_name = (
                getattr(r, "display_name", "")
                or (r.get("display_name") if isinstance(r, dict) else "")
                or getattr(r, "name", "")
                or (r.get("name") if isinstance(r, dict) else "")
            )
            curr_text = getattr(r, "rule_text", "") or getattr(r, "text", "") or (r.get("rule_text", "") if isinstance(r, dict) else "")

            syntax_verified = True
            compiler_diags: List[str] = []
            if curr_text:
                try:
                    val_res = self.adapter.verify_rule_text(rule_text=curr_text)
                    syntax_verified = bool(getattr(val_res, "success", True))
                    compiler_diags = [str(d) for d in getattr(val_res, "diagnostics", [])]
                except Exception as comp_err:
                    syntax_verified = False
                    compiler_diags = [str(comp_err)]

            unpopulated: List[str] = []
            if check_population and curr_text:
                extracted_fields = extract_udm_fields_from_yaral(curr_text)
                if extracted_fields:
                    pop_wf = AuditUdmFieldPopulationWorkflow(self.adapter)
                    pop_results = pop_wf.execute(
                        field_paths=extracted_fields[:10],
                        lookback_days=30,
                        schema_cache=schema_cache,
                    )
                    for f_path, f_info in pop_results.items():
                        if not f_info.get("populated", False):
                            unpopulated.append(f_path)

            rule_telemetry = telemetry_map.get(curr_id)

            dps_score, flags, rec, days_stale = calculate_decay_score(
                rule_detail=r,
                detection_telemetry_90d=rule_telemetry,
                unpopulated_fields=unpopulated,
                syntax_verified=syntax_verified,
                compiler_diagnostics=compiler_diags,
            )

            if "BROKEN_COMPILATION" in flags:
                broken_count += 1
            if "SILENT" in flags:
                silent_count += 1
            if "STALE" in flags:
                stale_count += 1
            if "UNPOPULATED" in flags:
                unpopulated_count += 1

            is_live = bool(getattr(r, "live_mode_enabled", False) or (r.get("live_mode_enabled") if isinstance(r, dict) else False))

            assessment = RuleDecayAssessment(
                rule_id=curr_id,
                rule_name=curr_name,
                dps_score=dps_score,
                decay_flags=flags,
                is_live=is_live,
                days_stale=days_stale,
                detection_count_90d=rule_telemetry.get("count", 0) if rule_telemetry else 0,
                first_seen=rule_telemetry.get("first_seen") if rule_telemetry else None,
                last_seen=rule_telemetry.get("last_seen") if rule_telemetry else None,
                unpopulated_fields=unpopulated,
                compiler_errors=compiler_diags if not syntax_verified else [],
                recommendation=rec,
                raw={
                    "rule_id": curr_id,
                    "name": curr_name,
                    "dps_score": dps_score,
                    "flags": flags,
                },
            )
            assessments.append(assessment)

        assessments.sort(key=lambda x: x.dps_score, reverse=True)
        avg_dps = sum(a.dps_score for a in assessments) / len(assessments) if assessments else 0.0

        return RuleDecayReport(
            assessments=assessments,
            total_audited=len(assessments),
            broken_compilation_count=broken_count,
            silent_count=silent_count,
            stale_count=stale_count,
            unpopulated_count=unpopulated_count,
            average_dps=round(avg_dps, 2),
        )
