#!/usr/bin/env python3
"""Launcher for the SecOps TUI proof-of-concept.

Run from anywhere; this script anchors ``sys.path`` to the project root so the
facade's root-relative imports (``from adapters.google_secops import ...``)
resolve correctly.

Usage:
    python run_tui.py                     # live engine (needs configured creds)
    python run_tui.py --query "..."       # seed the search box
    python run_tui.py --demo              # offline: fake data, no API calls
"""
from __future__ import annotations

import argparse
import os
import sys

# --- anchor project root (invariant #2 from clients/tui/__init__.py) ------
_ROOT = os.path.dirname(os.path.abspath(__file__))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)


def _build_demo_engine():
    """A stand-in engine exposing methods for the TUI interactive workflows.

    Lets us validate layout / threading / rendering with zero live dependency.
    """
    from datetime import datetime, timedelta, timezone
    from engine.domain import (
        CaseSearchBatch,
        CaseSearchResultItem,
        CaseInvestigation,
        CaseAlertSummary,
        InvolvedEntitySummary,
        CaseCommentRecord,
        AlertInvestigation,
        EntityInvestigationReport,
        EnterpriseIocMatch,
        PlaybookInstanceRun,
        PlaybookInstanceStep,
        PlaybookInstanceCard,
        CasePriority,
        CaseStatus,
        CuratedRuleSetBatch,
        CuratedRuleSetSummary,
        CuratedRuleSetDetail,
        CuratedRuleSummary,
        CuratedRuleSetDeployment,
        MitreAttackMapping,
        PlaybookBatch,
        PlaybookSummary,
        PlaybookDetail,
        PlaybookType,
        PlaybookTrigger,
        PlaybookTriggerCondition,
        PlaybookStep,
        SearchSession,
        CompletenessState,
        LifecycleState,
        EventInvestigation,
        RawLogPayload,
        InvestigationProvenance,
        DashboardBatch,
        DashboardSummary,
        DashboardDetail,
        DashboardChart,
        DashboardChartLayout,
        DashboardQuery,
        DashboardQueryResult,
    )

    now = datetime.now(timezone.utc)
    demo_comments: dict[str, list[CaseCommentRecord]] = {}

    demo_rulesets = [
        CuratedRuleSetSummary(
            id="crs-gcti-ransomware-01",
            title="Cloud Threat: Suspicious GCP IAM & Privilege Escalation",
            description="Detects anomalous GCP Service Account Key creation and role binding additions.",
            category_name="Cloud Security",
            log_sources=["GCP_CLOUDAUDIT", "GCP_IAM"],
            tactics=[MitreAttackMapping(id="TA0004", display_name="Privilege Escalation")],
            techniques=[MitreAttackMapping(id="T1098", display_name="Account Manipulation")],
            authors=["Google Cloud Threat Intelligence (GCTI)"],
            detection_count=14,
            deployments=[CuratedRuleSetDeployment(precision="PRECISE", enabled=True)],
        ),
        CuratedRuleSetSummary(
            id="crs-gcti-endpoint-lolbins",
            title="Endpoint: Living off the Land Binaries (LOLBins)",
            description="Identifies suspicious CertUtil, PowerShell, and MSBuild invocation patterns.",
            category_name="Endpoint Threat",
            log_sources=["WINEVTLOG", "SYSMON", "CROWDSTRIKE"],
            tactics=[MitreAttackMapping(id="TA0005", display_name="Defense Evasion")],
            techniques=[MitreAttackMapping(id="T1218", display_name="System Binary Proxy Execution")],
            authors=["Google Cloud Threat Intelligence (GCTI)"],
            detection_count=28,
            deployments=[CuratedRuleSetDeployment(precision="BROAD", enabled=True)],
        ),
        CuratedRuleSetSummary(
            id="crs-gcti-c2-cobaltstrike",
            title="Network: Cobalt Strike C2 & Beacon Telemetry",
            description="Correlates repetitive HTTP/DNS beaconing intervals matching known Malleable C2 profiles.",
            category_name="Network & Perimeter",
            log_sources=["ZEEK", "PANW_FIREWALL", "ZSCALER"],
            tactics=[MitreAttackMapping(id="TA0011", display_name="Command and Control")],
            techniques=[MitreAttackMapping(id="T1071", display_name="Application Layer Protocol")],
            authors=["Mandiant Security Research"],
            detection_count=8,
            deployments=[CuratedRuleSetDeployment(precision="PRECISE", enabled=True)],
        ),
    ]

    demo_playbooks = [
        PlaybookSummary(
            id="pb-def-phish-triage-v3",
            identifier="pb-def-phish-triage-v3",
            original_identifier="pb-def-phish-triage-v3",
            name="Phishing Alert Auto-Triage & Extraction",
            is_enabled=True,
            is_debug_mode=False,
            priority=1,
            category_id=10,
            category_name="Phishing",
            creator="secops-auto",
            creator_full_name="SecOps Automation",
            playbook_type=PlaybookType.REGULAR,
        ),
        PlaybookSummary(
            id="pb-def-user-containment-v2",
            identifier="pb-def-user-containment-v2",
            original_identifier="pb-def-user-containment-v2",
            name="Compromised User Containment & Session Revocation",
            is_enabled=True,
            is_debug_mode=False,
            priority=2,
            category_id=20,
            category_name="Identity & Access",
            creator="secops-auto",
            creator_full_name="SecOps Automation",
            playbook_type=PlaybookType.REGULAR,
        ),
        PlaybookSummary(
            id="pb-def-host-isolation-v1",
            identifier="pb-def-host-isolation-v1",
            original_identifier="pb-def-host-isolation-v1",
            name="Host Isolation & Forensic Artifact Collection",
            is_enabled=True,
            is_debug_mode=False,
            priority=1,
            category_id=30,
            category_name="Endpoint Containment",
            creator="ir-team",
            creator_full_name="Incident Response Team",
            playbook_type=PlaybookType.REGULAR,
        ),
    ]

    demo_dashboards = [
        DashboardSummary(
            id="dash-ingestion-health",
            name="dash-ingestion-health",
            display_name="Data Ingestion and Pipeline Health",
            description="Real-time telemetry ingestion volume, parser health, and log source throughput.",
            type="NATIVE_DASHBOARD",
            access="GLOBAL",
            charts_count=3,
            create_time=(now - timedelta(days=30)).strftime("%Y-%m-%d %H:%M:%S"),
            update_time=(now - timedelta(hours=1)).strftime("%Y-%m-%d %H:%M:%S"),
        ),
        DashboardSummary(
            id="dash-threat-overview",
            name="dash-threat-overview",
            display_name="Threat Detections & Rule Alerts Overview",
            description="YARA-L rule detections, severity breakdown, and MITRE ATT&CK coverage.",
            type="NATIVE_DASHBOARD",
            access="GLOBAL",
            charts_count=3,
            create_time=(now - timedelta(days=14)).strftime("%Y-%m-%d %H:%M:%S"),
            update_time=(now - timedelta(hours=3)).strftime("%Y-%m-%d %H:%M:%S"),
        ),
        DashboardSummary(
            id="dash-network-analytics",
            name="dash-network-analytics",
            display_name="Network Traffic & C2 Anomaly Analysis",
            description="DNS query spikes, high-frequency outbound connections, and anomalous egress.",
            type="CUSTOM_DASHBOARD",
            access="PRIVATE",
            charts_count=2,
            create_time=(now - timedelta(days=5)).strftime("%Y-%m-%d %H:%M:%S"),
            update_time=(now - timedelta(minutes=45)).strftime("%Y-%m-%d %H:%M:%S"),
        ),
    ]

    demo_events = [
        {
            "metadata": {
                "eventTimestamp": (now - timedelta(minutes=5)).isoformat(),
                "eventType": "USER_LOGIN",
                "logType": "OKTA",
                "productName": "Okta Identity Cloud",
                "vendorName": "Okta",
                "description": "User login succeeded from unrecognized foreign IP",
            },
            "principal": {
                "user": {"userid": "victim.user@corp.internal"},
                "ip": "198.51.100.42",
                "hostname": "workstation-mac-912.corp",
            },
            "target": {
                "user": {"userid": "victim.user@corp.internal"},
                "hostname": "sso.corp.internal",
                "port": 443,
            },
            "network": {
                "ipProtocol": "TCP",
                "direction": "INBOUND",
                "receivedBytes": 4200,
                "sentBytes": 1820,
            },
        },
        {
            "metadata": {
                "eventTimestamp": (now - timedelta(minutes=15)).isoformat(),
                "eventType": "PROCESS_LAUNCH",
                "logType": "SYSMON",
                "productName": "Microsoft Sysmon",
                "vendorName": "Microsoft",
                "description": "PowerShell spawned with base64 encoded command arguments",
            },
            "principal": {
                "user": {"userid": "svc_backup_admin"},
                "ip": "10.140.4.12",
                "hostname": "srv-db-prod-01.corp",
                "process": {"file": {"name": "powershell.exe"}},
            },
            "target": {
                "file": {"fullPath": "C:\\Windows\\Temp\\stage2_payload.exe"},
            },
            "network": {
                "ipProtocol": "TCP",
                "direction": "OUTBOUND",
                "receivedBytes": 128400,
                "sentBytes": 512,
            },
        },
        {
            "metadata": {
                "eventTimestamp": (now - timedelta(minutes=30)).isoformat(),
                "eventType": "NETWORK_CONNECTION",
                "logType": "ZEEK",
                "productName": "Zeek Network Security Monitor",
                "vendorName": "Zeek",
                "description": "Outbound connection to known C2 indicator",
            },
            "principal": {
                "ip": "10.140.4.12",
                "hostname": "srv-db-prod-01.corp",
            },
            "target": {
                "ip": "203.0.113.88",
                "hostname": "c2-gate-update.live",
                "port": 8443,
            },
            "network": {
                "ipProtocol": "TCP",
                "direction": "OUTBOUND",
                "receivedBytes": 8192,
                "sentBytes": 2048,
            },
        },
    ]

    demo_items = [
        CaseSearchResultItem(
            case_id=str(1000 + i),
            title=title,
            create_time=now - timedelta(hours=i * 3),
            priority=pri,
            stage=stage,
            tags=[],
            products=["Chronicle"],
            user_assigned=assignee,
            is_important=(i % 3 == 0),
            is_incident=(i % 4 == 0),
            is_closed=False,
            alerts_count=alerts,
            environment="Default",
            ticket_ids=[],
            ports=[],
            raw={},
        )
        for i, (title, pri, stage, assignee, alerts) in enumerate([
            ("Suspected credential phishing burst", CasePriority.CRITICAL, "Triage", "amartin", 4),
            ("Impossible travel — VPN + on-prem", CasePriority.HIGH, "Investigation", "bchen", 2),
            ("Malware beacon to known C2", CasePriority.HIGH, "Triage", None, 6),
            ("Excessive failed logins (svc acct)", CasePriority.MEDIUM, "Assessment", "amartin", 1),
            ("DLP: bulk export to personal drive", CasePriority.MEDIUM, "Investigation", None, 3),
            ("Port scan from internal host", CasePriority.LOW, "Triage", "dpatel", 1),
        ])
    ]

    class _DemoEngine:
        def search_cases(self, query="", page_size=50, **_):
            items = demo_items
            if query:
                q = query.lower()
                items = [it for it in demo_items if q in it.title.lower()]
            return CaseSearchBatch(
                results=items,
                total_count=len(items),
                page_size=page_size,
                page_number=0,
                provenance={"demo": True},
            )

        def investigate_case(self, case_id):
            src = next((it for it in demo_items if it.case_id == str(case_id)), demo_items[0])
            cid = src.case_id
            existing_comments = demo_comments.get(cid, [
                CaseCommentRecord(
                    name=f"cases/{cid}/comments/1",
                    comment="Initial alert triage completed. Host isolated pending network telemetry review.",
                    author="analyst_amartin@corp.internal",
                    author_name="Alice Martin",
                    create_time=now - timedelta(hours=1),
                )
            ])
            return CaseInvestigation(
                case_id=src.case_id,
                name=f"cases/{src.case_id}",
                display_name=src.title,
                status=CaseStatus.OPEN,
                priority=src.priority,
                stage=src.stage,
                create_time=src.create_time,
                update_time=now,
                assignee=src.user_assigned,
                alert_count=src.alerts_count,
                alerts=[
                    CaseAlertSummary(
                        name=f"cases/{src.case_id}/alerts/{j}",
                        identifier=f"alert-{cid}-{j+1}",
                        display_name=f"{src.title} — alert {j+1}",
                        priority=src.priority.name,
                        status="OPEN",
                        product="Chronicle",
                        vendor="Google",
                        event_count=(j + 1) * 5,
                        start_time=src.create_time,
                        end_time=now,
                        rule_name=f"rule_detection_{cid}_{j+1}",
                        attached_playbook_name="Phishing-Auto-Triage" if j == 0 else "Host-Containment",
                        playbook_status="Completed" if j == 0 else "Running",
                        playbook_run_count=1,
                        alert_group_identifier=f"group-{cid}-{j+1}",
                        raw={},
                    )
                    for j in range(max(src.alerts_count, 1))
                ],
                entities=[
                    InvolvedEntitySummary(
                        identifier="jdoe@corp.example",
                        display_name="jdoe@corp.example",
                        entity_type="USER",
                        role="source",
                        is_suspicious=True,
                        raw={},
                    ),
                    InvolvedEntitySummary(
                        identifier="10.0.4.17",
                        display_name="10.0.4.17",
                        entity_type="IP",
                        role="target",
                        is_suspicious=False,
                        raw={},
                    ),
                    InvolvedEntitySummary(
                        identifier="e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
                        display_name="e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
                        entity_type="SHA256",
                        role="payload",
                        is_suspicious=True,
                        raw={},
                    ),
                ],
                comments=existing_comments,
                provenance={"demo": True},
                raw_case={},
            )

        def add_case_comment(self, case_id, comment):
            cid = str(case_id)
            rec = CaseCommentRecord(
                name=f"cases/{cid}/comments/{len(demo_comments.get(cid, [])) + 1}",
                comment=comment,
                author="soc_analyst@corp.internal",
                author_name="Current Analyst",
                create_time=datetime.now(),
            )
            if cid not in demo_comments:
                demo_comments[cid] = [
                    CaseCommentRecord(
                        name=f"cases/{cid}/comments/1",
                        comment="Initial alert triage completed. Host isolated pending network telemetry review.",
                        author="analyst_amartin@corp.internal",
                        author_name="Alice Martin",
                        create_time=now - timedelta(hours=1),
                    )
                ]
            demo_comments[cid].append(rec)
            return rec

        def investigate_alert(self, alert_name):
            return AlertInvestigation(
                alert_name=alert_name,
                case_id="1000",
                display_name=f"Deep Investigation — {alert_name}",
                priority="HIGH",
                status="OPEN",
                rule_name="rule_suspected_phishing_credential_access",
                rule_id="r_phish_0921",
                risk_score=85,
                detection_time=now - timedelta(hours=2),
                product="Chronicle SIEM",
                vendor="Google SecOps",
                event_count=12,
                entities=[
                    InvolvedEntitySummary(
                        identifier="jdoe@corp.example",
                        display_name="jdoe@corp.example",
                        entity_type="USER",
                        role="source",
                        is_suspicious=True,
                    ),
                    InvolvedEntitySummary(
                        identifier="198.51.100.44",
                        display_name="198.51.100.44",
                        entity_type="IP",
                        role="c2_endpoint",
                        is_suspicious=True,
                    ),
                ],
                associated_events=[
                    {
                        "metadata": {
                            "eventType": "USER_LOGIN",
                            "eventTimestamp": (now - timedelta(minutes=45)).isoformat(),
                            "logType": "OKTA",
                        },
                        "principal": {"user": {"userid": "jdoe@corp.example"}},
                        "target": {"ip": "198.51.100.44"},
                    },
                    {
                        "metadata": {
                            "eventType": "NETWORK_CONNECTION",
                            "eventTimestamp": (now - timedelta(minutes=30)).isoformat(),
                            "logType": "ZEEK_HTTP",
                        },
                        "principal": {"ip": "10.0.4.17"},
                        "target": {"ip": "198.51.100.44", "hostname": "auth-login-update.com"},
                    },
                ],
                provenance={"demo": True},
                raw_alert={},
            )

        def investigate_entity(self, indicator, **_):
            return EntityInvestigationReport(
                indicator=indicator,
                detected_type="IP" if ("." in indicator and not "@" in indicator) else ("USER" if "@" in indicator else "SHA256"),
                category="NETWORK" if "." in indicator else "IDENTITY",
                entity_graph_events_count=18,
                udm_events_count=42,
                enterprise_iocs_count=2,
                related_cases_count=3,
                ioc_matches=[
                    EnterpriseIocMatch(
                        artifact_indicator={"value": indicator, "type": "IPV4"},
                        sources=["Mandiant Threat Intelligence", "Google Threat Horizons"],
                        categories=["C2_SERVER", "PHISHING_INFRASTRUCTURE"],
                        first_seen=(now - timedelta(days=7)).isoformat(),
                        last_seen=now.isoformat(),
                    ),
                ],
                related_cases=[
                    demo_items[0],
                    demo_items[1],
                ],
                created_at=now,
            )

        def get_alert_playbook_instance(self, case_id, alert_identifier, **_):
            return PlaybookInstanceRun(
                instance_id="pbi-9901-auto-triage",
                identifier="pb-def-phish-triage-v3",
                name="Auto-Triage Phishing & User Investigation",
                case_id=str(case_id),
                alert_identifier=str(alert_identifier),
                status="COMPLETED",
                steps=[
                    PlaybookInstanceStep(
                        identifier="step-1",
                        name="Extract Entities from Alert",
                        action_name="Entity Extractor",
                        status="COMPLETED",
                        integration="Core SOAR",
                        start_time=now - timedelta(minutes=10),
                        end_time=now - timedelta(minutes=9),
                    ),
                    PlaybookInstanceStep(
                        identifier="step-2",
                        name="Query Mandiant IoC Intel",
                        action_name="Enrich Indicators",
                        status="COMPLETED",
                        integration="Mandiant Threat Intel",
                        start_time=now - timedelta(minutes=9),
                        end_time=now - timedelta(minutes=8),
                    ),
                    PlaybookInstanceStep(
                        identifier="step-3",
                        name="Correlate UDM User Logins",
                        action_name="UDM Search",
                        status="COMPLETED",
                        integration="Chronicle SIEM",
                        start_time=now - timedelta(minutes=8),
                        end_time=now - timedelta(minutes=7),
                    ),
                    PlaybookInstanceStep(
                        identifier="step-4",
                        name="Prompt Analyst for Review",
                        action_name="Manual Review Step",
                        status="COMPLETED",
                        integration="SOAR Workspace",
                        start_time=now - timedelta(minutes=7),
                        end_time=now - timedelta(minutes=6),
                    ),
                ],
            )

        def get_alert_playbook_instances(self, case_id, alert_identifier):
            return [
                PlaybookInstanceCard(
                    instance_id="pbi-9901-auto-triage",
                    definition_identifier="pb-def-phish-triage-v3",
                    name="Auto-Triage Phishing & User Investigation",
                    status="COMPLETED",
                )
            ]

        def search_udm(self, request=None, **_):
            q = getattr(request, "query", "") if request else ""
            results = demo_events
            if q and "UNKNOWN_EVENT_TYPE" not in q:
                ql = q.lower()
                results = [
                    ev for ev in demo_events
                    if ql in str(ev.get("metadata", {})).lower()
                    or ql in str(ev.get("principal", {})).lower()
                    or ql in str(ev.get("target", {})).lower()
                ]
            return SearchSession(
                session_id="session-demo-udm-001",
                request=request,
                lifecycle=LifecycleState.COMPLETED,
                completeness=CompletenessState.COMPLETE,
                received_count=len(results),
                events=results,
            )

        def search_events(self, query="", limit=50, **_):
            results = demo_events
            if query and "UNKNOWN_EVENT_TYPE" not in query:
                q = query.lower()
                results = [
                    ev for ev in demo_events
                    if q in str(ev.get("metadata", {})).lower()
                    or q in str(ev.get("principal", {})).lower()
                    or q in str(ev.get("target", {})).lower()
                ]
            class _EventBatch:
                events = results
                total_events = len(results)
            return _EventBatch()

        def investigate_event(self, event_ref, eager_load_raw_log=False, **_):
            if isinstance(event_ref, dict):
                ev = event_ref.get("event") or event_ref.get("udm") or event_ref
                ev_id = ev.get("metadata", {}).get("id") or "ev-demo-001"
                structured = ev
            elif hasattr(event_ref, "event_id"):
                ev_id = event_ref.event_id
                structured = getattr(event_ref, "structured_event", demo_events[0])
            else:
                ev_id = str(event_ref)
                structured = demo_events[0]

            raw_payload = RawLogPayload(
                raw_text=(
                    f"<134>1 {now.isoformat()} srv-db-prod-01.corp Microsoft-Windows-Sysmon 1 - - "
                    f"[EventID=1 ProcessName=\"powershell.exe\" CommandLine=\"powershell.exe -enc SQBYAE0A...\" "
                    f"User=\"svc_backup_admin\" IntegrityLevel=\"High\"]"
                ),
                source_product="Microsoft Sysmon",
                log_type="SYSMON",
                timestamp=now.isoformat(),
                raw_bytes_size=248,
                retrieved_at=now,
            ) if eager_load_raw_log else None

            return EventInvestigation(
                event_id=ev_id,
                event=structured,
                raw_log=raw_payload,
            )

        def get_raw_log(self, event_id="", log_token=None, **_):
            return RawLogPayload(
                raw_text=(
                    f"<134>1 {now.isoformat()} srv-db-prod-01.corp Microsoft-Windows-Sysmon 1 - - "
                    f"[EventID=1 ProcessName=\"powershell.exe\" CommandLine=\"powershell.exe -enc SQBYAE0A...\" "
                    f"User=\"svc_backup_admin\" IntegrityLevel=\"High\"]"
                ),
                source_product="Microsoft Sysmon",
                log_type="SYSMON",
                timestamp=now.isoformat(),
                raw_bytes_size=248,
                retrieved_at=now,
            )

        def search_curated_rulesets(self, query=None, q=None, **_):
            search_term = query or q or ""
            results = demo_rulesets
            if search_term:
                query_str = search_term.lower()
                results = [
                    rs for rs in demo_rulesets
                    if query_str in rs.title.lower()
                    or query_str in rs.description.lower()
                    or query_str in rs.category_name.lower()
                ]
            return CuratedRuleSetBatch(
                results=results,
                total_count=len(results),
            )

        def get_curated_ruleset(self, ruleset_id, **_):
            rs = next((r for r in demo_rulesets if r.id == str(ruleset_id) or r.title == str(ruleset_id)), demo_rulesets[0])
            return CuratedRuleSetDetail(
                rule_set=rs,
                rules=[
                    CuratedRuleSummary(
                        id=f"{rs.id}-rule-01",
                        title=f"{rs.title} — Primary Heuristic",
                        severity="HIGH",
                        precision="PRECISE",
                        rule_type="MULTI_EVENT",
                        curated_rule_set_id=rs.id,
                        techniques=rs.techniques,
                        description=rs.description,
                    ),
                    CuratedRuleSummary(
                        id=f"{rs.id}-rule-02",
                        title=f"{rs.title} — Broad Anomaly Detector",
                        severity="MEDIUM",
                        precision="BROAD",
                        rule_type="SINGLE_EVENT",
                        curated_rule_set_id=rs.id,
                        techniques=rs.techniques,
                        description=f"Supplementary detection logic for {rs.title}",
                    ),
                ],
                deployments=rs.deployments,
                detection_count=rs.detection_count,
            )

        def search_playbooks(self, query="", **_):
            results = demo_playbooks
            if query:
                q = query.lower()
                results = [
                    pb for pb in demo_playbooks
                    if q in pb.name.lower()
                    or q in pb.category_name.lower()
                ]
            return PlaybookBatch(
                results=results,
                total_count=len(results),
            )

        def get_playbook(self, playbook_id, **_):
            pb = next((p for p in demo_playbooks if p.identifier == str(playbook_id) or p.name == str(playbook_id)), demo_playbooks[0])
            return PlaybookDetail(
                id=pb.identifier,
                identifier=pb.identifier,
                name=pb.name,
                description="Automated triage and remediation workflow.",
                is_enabled=pb.is_enabled,
                is_debug_mode=False,
                priority=pb.priority,
                category_id=pb.category_id,
                category_name=pb.category_name,
                creator=pb.creator,
                trigger=PlaybookTrigger(
                    id=f"{pb.identifier}-trig",
                    identifier=f"{pb.identifier}-trig",
                    trigger_type="ALERT",
                    conditions=[
                        PlaybookTriggerCondition(
                            value="Alert.Priority in ['HIGH', 'CRITICAL']",
                        )
                    ],
                ),
                steps=[
                    PlaybookStep(
                        identifier=f"{pb.identifier}-s1",
                        original_step_identifier=f"{pb.identifier}-s1",
                        name="Extract Target Artifacts",
                        instance_name="extract_artifacts_1",
                        action_name="Entity Extractor",
                        action_provider="Chronicle",
                        integration="Core SOAR",
                        step_type="AUTOMATIC",
                        is_automatic=True,
                    ),
                    PlaybookStep(
                        identifier=f"{pb.identifier}-s2",
                        original_step_identifier=f"{pb.identifier}-s2",
                        name="Threat Intelligence Query",
                        instance_name="intel_query_1",
                        action_name="Mandiant IoC Lookup",
                        action_provider="Mandiant",
                        integration="Mandiant Threat Intel",
                        step_type="AUTOMATIC",
                        is_automatic=True,
                    ),
                    PlaybookStep(
                        identifier=f"{pb.identifier}-s3",
                        original_step_identifier=f"{pb.identifier}-s3",
                        name="Contain Host / Revoke Credentials",
                        instance_name="contain_host_1",
                        action_name="Remediation Handler",
                        action_provider="SecOps",
                        integration="SecOps Identity",
                        step_type="MANUAL",
                        is_automatic=False,
                    ),
                ],
            )

        def search_dashboards(self, query="", **_):
            results = demo_dashboards
            if query:
                q = query.lower()
                results = [
                    d for d in demo_dashboards
                    if q in d.display_name.lower()
                    or q in d.description.lower()
                    or q in d.id.lower()
                ]
            return DashboardBatch(
                dashboards=results,
                total_count=len(results),
            )

        def get_dashboard(self, dashboard_id, **_):
            dash = next((d for d in demo_dashboards if d.id == str(dashboard_id) or d.display_name == str(dashboard_id)), demo_dashboards[0])
            
            if dash.id == "dash-ingestion-health":
                charts = [
                    DashboardChart(
                        id="c-ingest-kpi",
                        name="c-ingest-kpi",
                        display_name="24h Telemetry Ingestion Volume",
                        description="Total gigabytes ingested across all forwarders and cloud feeds in the last 24 hours.",
                        chart_type="DASHBOARD_CHART_TYPE_METRIC",
                        query=DashboardQuery(
                            id="q-ingest-kpi",
                            name="q-ingest-kpi",
                            query_text="sum(metadata.event_size) / (1024 * 1024 * 1024) as total_gb",
                            dialect="DIALECT_STATS",
                        ),
                    ),
                    DashboardChart(
                        id="c-ingest-by-logtype",
                        name="c-ingest-by-logtype",
                        display_name="Top Log Types by Volume (GB)",
                        description="Distribution of ingested event volume ranked by log type.",
                        chart_type="DASHBOARD_CHART_TYPE_BAR",
                        query=DashboardQuery(
                            id="q-ingest-by-logtype",
                            name="q-ingest-by-logtype",
                            query_text="group by metadata.log_type, sum(bytes) as volume",
                            dialect="DIALECT_STATS",
                        ),
                    ),
                    DashboardChart(
                        id="c-ingest-hourly",
                        name="c-ingest-hourly",
                        display_name="Hourly Ingestion & Parsing Health Breakdown",
                        description="Hourly event count, parsing error percentage, and ingestion status.",
                        chart_type="DASHBOARD_CHART_TYPE_TABLE",
                        query=DashboardQuery(
                            id="q-ingest-hourly",
                            name="q-ingest-hourly",
                            query_text="window(1h) count(events), sum(errors)",
                            dialect="DIALECT_STATS",
                        ),
                    ),
                ]
            elif dash.id == "dash-threat-overview":
                charts = [
                    DashboardChart(
                        id="c-threat-kpi",
                        name="c-threat-kpi",
                        display_name="Active Threat Detections (24h)",
                        description="Total distinct YARA-L rule detection alerts generated in the active window.",
                        chart_type="DASHBOARD_CHART_TYPE_METRIC",
                        query=DashboardQuery(
                            id="q-threat-kpi",
                            name="q-threat-kpi",
                            query_text="count(distinct alert_id) where severity != 'LOW'",
                            dialect="DIALECT_STATS",
                        ),
                    ),
                    DashboardChart(
                        id="c-threat-severity",
                        name="c-threat-severity",
                        display_name="Alerts by Severity Level",
                        description="Frequency breakdown across CRITICAL, HIGH, MEDIUM, and LOW alerts.",
                        chart_type="DASHBOARD_CHART_TYPE_BAR",
                        query=DashboardQuery(
                            id="q-threat-severity",
                            name="q-threat-severity",
                            query_text="group by security_result.severity, count(alerts)",
                            dialect="DIALECT_STATS",
                        ),
                    ),
                    DashboardChart(
                        id="c-threat-top-rules",
                        name="c-threat-top-rules",
                        display_name="Top Triggered Detection Rules",
                        description="Most active YARA-L detection rules and affected entity counts.",
                        chart_type="DASHBOARD_CHART_TYPE_TABLE",
                        query=DashboardQuery(
                            id="q-threat-top-rules",
                            name="q-threat-top-rules",
                            query_text="group by rule_name, count(alerts), count(distinct principal.ip)",
                            dialect="DIALECT_STATS",
                        ),
                    ),
                ]
            else:
                charts = [
                    DashboardChart(
                        id="c-network-c2",
                        name="c-network-c2",
                        display_name="High-Risk Outbound Destinations",
                        description="Outbound connections to suspicious autonomous systems and countries.",
                        chart_type="DASHBOARD_CHART_TYPE_BAR",
                        query=DashboardQuery(
                            id="q-network-c2",
                            name="q-network-c2",
                            query_text="group by target.ip_geo_artifact.country, count(connections)",
                            dialect="DIALECT_STATS",
                        ),
                    ),
                    DashboardChart(
                        id="c-network-dns",
                        name="c-network-dns",
                        display_name="Recent Anomalous DNS Queries",
                        description="High-entropy domain queries and unusual lookup patterns.",
                        chart_type="DASHBOARD_CHART_TYPE_TABLE",
                        query=DashboardQuery(
                            id="q-network-dns",
                            name="q-network-dns",
                            query_text="filter network.dns.query where is_dga(network.dns.query)",
                            dialect="DIALECT_STATS",
                        ),
                    ),
                ]

            return DashboardDetail(
                summary=dash,
                charts=charts,
                filters=[],
            )

        def execute_dashboard_query(self, query_name_or_id, **_):
            qid = str(query_name_or_id)
            if "ingest-kpi" in qid:
                return DashboardQueryResult(
                    query_name=qid,
                    dialect="DIALECT_STATS",
                    data_sources=["GCP_CLOUDAUDIT", "SYSMON", "ZEEK"],
                    time_window={"startTime": "2026-08-23T00:00:00Z", "endTime": "2026-08-24T00:00:00Z"},
                    columns=["Ingestion Volume (GB)", "Status"],
                    rows=[{"Ingestion Volume (GB)": "48.6 GB", "Status": "HEALTHY"}],
                    total_rows=1,
                )
            elif "ingest-by-logtype" in qid:
                return DashboardQueryResult(
                    query_name=qid,
                    dialect="DIALECT_STATS",
                    data_sources=["ALL_FEEDS"],
                    time_window={"startTime": "2026-08-23T00:00:00Z", "endTime": "2026-08-24T00:00:00Z"},
                    columns=["Log Source", "Volume (GB)"],
                    rows=[
                        {"Log Source": "WINDOWS_SYSMON", "Volume (GB)": 22.4},
                        {"Log Source": "ZEEK_NETWORK", "Volume (GB)": 14.8},
                        {"Log Source": "GCP_CLOUDAUDIT", "Volume (GB)": 7.2},
                        {"Log Source": "OKTA_SSO", "Volume (GB)": 3.1},
                        {"Log Source": "PANW_FIREWALL", "Volume (GB)": 1.1},
                    ],
                    total_rows=5,
                )
            elif "ingest-hourly" in qid:
                return DashboardQueryResult(
                    query_name=qid,
                    dialect="DIALECT_STATS",
                    data_sources=["ALL_FEEDS"],
                    time_window={"startTime": "2026-08-23T00:00:00Z", "endTime": "2026-08-24T00:00:00Z"},
                    columns=["Time Window", "Events Ingested", "Error Rate", "Pipeline Lag"],
                    rows=[
                        {"Time Window": "12:00 - 13:00", "Events Ingested": "1,420,500", "Error Rate": "0.01%", "Pipeline Lag": "1.2s"},
                        {"Time Window": "13:00 - 14:00", "Events Ingested": "1,680,200", "Error Rate": "0.00%", "Pipeline Lag": "0.9s"},
                        {"Time Window": "14:00 - 15:00", "Events Ingested": "1,550,100", "Error Rate": "0.02%", "Pipeline Lag": "1.1s"},
                        {"Time Window": "15:00 - 16:00", "Events Ingested": "1,890,400", "Error Rate": "0.01%", "Pipeline Lag": "1.4s"},
                    ],
                    total_rows=4,
                )
            elif "threat-kpi" in qid:
                return DashboardQueryResult(
                    query_name=qid,
                    dialect="DIALECT_STATS",
                    data_sources=["DETECTIONS"],
                    time_window={"startTime": "2026-08-23T00:00:00Z", "endTime": "2026-08-24T00:00:00Z"},
                    columns=["Active Detections", "Critical Alerts"],
                    rows=[{"Active Detections": 42, "Critical Alerts": 8}],
                    total_rows=1,
                )
            elif "threat-severity" in qid:
                return DashboardQueryResult(
                    query_name=qid,
                    dialect="DIALECT_STATS",
                    data_sources=["DETECTIONS"],
                    time_window={"startTime": "2026-08-23T00:00:00Z", "endTime": "2026-08-24T00:00:00Z"},
                    columns=["Severity", "Alert Count"],
                    rows=[
                        {"Severity": "CRITICAL", "Alert Count": 8},
                        {"Severity": "HIGH", "Alert Count": 18},
                        {"Severity": "MEDIUM", "Alert Count": 12},
                        {"Severity": "LOW", "Alert Count": 4},
                    ],
                    total_rows=4,
                )
            elif "threat-top-rules" in qid:
                return DashboardQueryResult(
                    query_name=qid,
                    dialect="DIALECT_STATS",
                    data_sources=["DETECTIONS"],
                    time_window={"startTime": "2026-08-23T00:00:00Z", "endTime": "2026-08-24T00:00:00Z"},
                    columns=["Rule Name", "Alert Count", "Unique Entities", "Severity"],
                    rows=[
                        {"Rule Name": "Cobalt Strike Beaconing Activity", "Alert Count": 14, "Unique Entities": 4, "Severity": "CRITICAL"},
                        {"Rule Name": "Suspicious GCP Service Account Key", "Alert Count": 11, "Unique Entities": 2, "Severity": "HIGH"},
                        {"Rule Name": "PowerShell Encoded Command Spawn", "Alert Count": 9, "Unique Entities": 5, "Severity": "HIGH"},
                        {"Rule Name": "Living off the Land: CertUtil", "Alert Count": 8, "Unique Entities": 3, "Severity": "MEDIUM"},
                    ],
                    total_rows=4,
                )
            elif "network-c2" in qid:
                return DashboardQueryResult(
                    query_name=qid,
                    dialect="DIALECT_STATS",
                    data_sources=["ZEEK"],
                    time_window={"startTime": "2026-08-23T00:00:00Z", "endTime": "2026-08-24T00:00:00Z"},
                    columns=["Destination Country", "Connection Count"],
                    rows=[
                        {"Destination Country": "United States", "Connection Count": 4500},
                        {"Destination Country": "Germany", "Connection Count": 1200},
                        {"Destination Country": "Singapore", "Connection Count": 840},
                        {"Destination Country": "Romania", "Connection Count": 210},
                    ],
                    total_rows=4,
                )
            else:
                return DashboardQueryResult(
                    query_name=qid,
                    dialect="DIALECT_STATS",
                    data_sources=["ZEEK_DNS"],
                    time_window={"startTime": "2026-08-23T00:00:00Z", "endTime": "2026-08-24T00:00:00Z"},
                    columns=["Timestamp", "Domain Query", "Query Type", "Response Code", "Risk Score"],
                    rows=[
                        {"Timestamp": "2026-08-24 15:42:10", "Domain Query": "c2-gate-update.live", "Query Type": "A", "Response Code": "NOERROR", "Risk Score": "HIGH"},
                        {"Timestamp": "2026-08-24 15:43:05", "Domain Query": "api-sync-cdn99.xyz", "Query Type": "AAAA", "Response Code": "NOERROR", "Risk Score": "HIGH"},
                        {"Timestamp": "2026-08-24 15:44:22", "Domain Query": "raw-telemetry.ru", "Query Type": "TXT", "Response Code": "NXDOMAIN", "Risk Score": "CRITICAL"},
                    ],
                    total_rows=3,
                )

    return _DemoEngine()


def main() -> int:
    parser = argparse.ArgumentParser(description="SecOps TUI proof-of-concept")
    parser.add_argument("--query", default="", help="seed the case search box")
    parser.add_argument("--demo", action="store_true", help="offline demo mode (no API calls)")
    parser.add_argument("--page-size", type=int, default=50)
    args = parser.parse_args()

    try:
        from clients.tui.app import SecOpsTUI
    except ModuleNotFoundError as exc:
        if "textual" in str(exc):
            print("Textual is not installed. Run: pip install -r clients/tui/requirements-tui.txt", file=sys.stderr)
            return 2
        raise

    if args.demo:
        engine = _build_demo_engine()
    else:
        from engine.facade import SecOpsEngine
        try:
            engine = SecOpsEngine()
        except Exception as exc:
            print(f"Failed to construct SecOpsEngine (creds/config?): {exc}", file=sys.stderr)
            print("Tip: use --demo to preview the UI without live credentials.", file=sys.stderr)
            return 3

    SecOpsTUI(engine=engine, initial_query=args.query, page_size=args.page_size).run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
