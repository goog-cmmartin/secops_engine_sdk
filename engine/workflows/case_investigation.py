from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set

from engine.domain import (
    CaseAlertSummary,
    CaseCommentRecord,
    CaseInvestigation,
    CasePriority,
    CaseStatus,
    InvolvedEntitySummary,
)


from engine.parsing import (
    parse_priority,
    parse_priority as _parse_priority,
    parse_status,
    parse_status as _parse_status,
    parse_timestamp,
    parse_timestamp as _parse_timestamp,
)


class InvestigateCaseWorkflow:
    """Orchestrates comprehensive investigation of a SecOps case and its sub-resources."""

    def __init__(self, adapter: Optional[Any] = None):
        if adapter is None:
            from adapters.google_secops import GoogleSecOpsAdapter
            adapter = GoogleSecOpsAdapter()
        self.adapter = adapter

    def execute(self, case_id: str) -> CaseInvestigation:
        if not case_id or not str(case_id).strip():
            raise ValueError("case_id must be a non-empty string.")

        clean_case_id = str(case_id).strip().split("/")[-1]

        # Fetch case metadata, alerts, and comments in parallel
        with ThreadPoolExecutor(max_workers=4) as executor:
            future_case = executor.submit(self.adapter.get_case, clean_case_id)
            future_alerts = executor.submit(self.adapter.list_case_alerts, clean_case_id)
            future_comments = executor.submit(self.adapter.list_case_comments, clean_case_id)

            case_raw = future_case.result()
            alerts_raw = future_alerts.result()
            comments_raw = future_comments.result()

        # Parse alert summaries and fan out entity collection
        alerts: List[CaseAlertSummary] = []
        alert_names: List[str] = []
        for a in alerts_raw:
            alert_name = a.get("name", "")
            if alert_name:
                alert_names.append(alert_name)
            alerts.append(
                CaseAlertSummary(
                    name=alert_name,
                    identifier=a.get("identifier") or alert_name.split("/")[-1],
                    display_name=a.get("displayName") or a.get("ruleGenerator") or "Alert",
                    priority=a.get("priority", "UNKNOWN"),
                    status=a.get("status", "UNKNOWN"),
                    product=a.get("product"),
                    vendor=a.get("vendor"),
                    event_count=int(a.get("eventCount", 0) or 0),
                    start_time=_parse_timestamp(a.get("startTime")),
                    end_time=_parse_timestamp(a.get("endTime")),
                    rule_name=a.get("sourceRuleIdentifier") or a.get("displayName"),
                    attached_playbook_name=a.get("attachedPlaybookName"),
                    playbook_status=a.get("playbookStatus"),
                    playbook_run_count=int(a.get("playbookRunCount", 0) or 0),
                    alert_group_identifier=a.get("alertGroupIdentifier"),
                    raw=a,
                )
            )

        # Fetch involved entities for all alerts in parallel
        entities: List[InvolvedEntitySummary] = []
        seen_entity_keys: Set[str] = set()

        if alert_names:
            with ThreadPoolExecutor(max_workers=min(8, len(alert_names))) as executor:
                entity_futures = {
                    executor.submit(self.adapter.list_alert_entities, aname): aname
                    for aname in alert_names
                }
                for f in as_completed(entity_futures):
                    ents_raw = f.result()
                    for e in ents_raw:
                        identifier = e.get("identifier") or e.get("name") or ""
                        etype = e.get("entityType") or e.get("type")
                        dedup_key = f"{identifier}::{etype}"
                        if identifier and dedup_key not in seen_entity_keys:
                            seen_entity_keys.add(dedup_key)
                            entities.append(
                                InvolvedEntitySummary(
                                    identifier=identifier,
                                    display_name=e.get("name") or identifier,
                                    entity_type=etype,
                                    role=e.get("role"),
                                    is_suspicious=bool(e.get("isSuspicious", False)),
                                    raw=e,
                                )
                            )

        # Parse case comments
        comments: List[CaseCommentRecord] = []
        for c in comments_raw:
            comments.append(
                CaseCommentRecord(
                    name=c.get("name", ""),
                    comment=c.get("comment", ""),
                    author=c.get("user") or c.get("creator"),
                    author_name=c.get("userOwnerFullName") or c.get("lastEditorFullName"),
                    create_time=_parse_timestamp(c.get("createTime")),
                    is_deleted=bool(c.get("isDeleted", False)),
                    raw=c,
                )
            )

        # Build composite CaseInvestigation
        provenance = {
            "retrieved_at": datetime.now(timezone.utc).isoformat(),
            "case_id": clean_case_id,
            "raw_resource_name": case_raw.get("name", ""),
            "alert_count_returned": len(alerts),
            "entity_count_returned": len(entities),
            "comment_count_returned": len(comments),
        }

        return CaseInvestigation(
            case_id=clean_case_id,
            name=case_raw.get("name", f"cases/{clean_case_id}"),
            display_name=case_raw.get("displayName") or case_raw.get("title") or f"Case {clean_case_id}",
            status=_parse_status(case_raw.get("status")),
            priority=_parse_priority(case_raw.get("priority")),
            stage=case_raw.get("stage", "Unknown"),
            create_time=_parse_timestamp(case_raw.get("createTime")),
            update_time=_parse_timestamp(case_raw.get("updateTime")),
            assignee=case_raw.get("assignee") or case_raw.get("assignedUser"),
            alert_count=int(case_raw.get("alertCount", len(alerts)) or len(alerts)),
            alerts=alerts,
            entities=entities,
            comments=comments,
            provenance=provenance,
            raw_case=case_raw,
        )


class AddCaseCommentWorkflow:
    """Orchestrates posting comments to a SecOps case with strict error visibility."""

    def __init__(self, adapter: Optional[Any] = None):
        if adapter is None:
            from adapters.google_secops import GoogleSecOpsAdapter
            adapter = GoogleSecOpsAdapter()
        self.adapter = adapter

    def execute(self, case_id: str, comment: str) -> CaseCommentRecord:
        if not case_id or not str(case_id).strip():
            raise ValueError("case_id must be a non-empty string.")
        if not comment or not comment.strip():
            raise ValueError("comment cannot be empty or whitespace.")

        clean_case_id = str(case_id).strip().split("/")[-1]
        raw_res = self.adapter.create_case_comment(case_id=clean_case_id, comment=comment.strip())

        return CaseCommentRecord(
            name=raw_res.get("name", ""),
            comment=raw_res.get("comment", comment.strip()),
            author=raw_res.get("user") or raw_res.get("creator"),
            author_name=raw_res.get("userOwnerFullName") or raw_res.get("lastEditorFullName"),
            create_time=_parse_timestamp(raw_res.get("createTime")),
            is_deleted=bool(raw_res.get("isDeleted", False)),
            raw=raw_res,
        )
