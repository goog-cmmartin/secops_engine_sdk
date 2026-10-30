import ipaddress
import re
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Set, Union

if TYPE_CHECKING:
    from adapters.google_secops import GoogleSecOpsAdapter

from engine.domain import (
    CaseDetectionCorrelationResult,
    CaseEvidenceItem,
    EntityType,
    coerce_entity_type,
)
from engine.parsing import parse_timestamp
from engine.workflows.case_evidence import AttachCaseEvidenceWorkflow
from engine.workflows.case_investigation import InvestigateCaseWorkflow
from engine.workflows.refine_search import SearchFromEntityWorkflow
from engine.workflows.search_udm import SearchUDMWorkflow


def _clean_case_id(raw_id: Union[str, int]) -> str:
    """Extracts numeric case identifier."""
    return str(raw_id).strip().split('/')[-1]


# ---------------------------------------------------------------------------
# GUARDRAILS & SANITIZATION RULES
# ---------------------------------------------------------------------------

GENERIC_USERS = {
    "system", "nt authority\\system", "local service", "nt authority\\local service",
    "network service", "nt authority\\network service", "anonymous logon", "root",
    "nobody", "daemon", "guest", "localhost", "none", "null", "unknown", "n/a",
    "administrator", "admin", "localadmin"
}

GENERIC_BINARIES = {
    "cmd.exe", "powershell.exe", "pwsh.exe", "conhost.exe", "svchost.exe",
    "rundll32.exe", "explorer.exe", "wsmprovhost.exe", "cscript.exe", "wscript.exe",
    "msiexec.exe", "reg.exe", "taskhostw.exe", "services.exe", "lsass.exe",
    "csrss.exe", "smss.exe", "wininit.exe", "winlogon.exe", "taskhost.exe",
    "dllhost.exe", "wmiprvse.exe", "mshta.exe"
}

NOISY_IPS = {
    "8.8.8.8", "8.8.4.4", "1.1.1.1", "1.0.0.1", "9.9.9.9", "149.112.112.112",
    "208.67.222.222", "208.67.220.220", "127.0.0.1", "0.0.0.0", "255.255.255.255",
}


def is_noisy_ip(ip_str: str) -> bool:
    clean = ip_str.strip()
    if clean in NOISY_IPS:
        return True
    try:
        ip = ipaddress.ip_address(clean)
        return (
            ip.is_loopback or
            ip.is_multicast or
            ip.is_link_local or
            ip.is_unspecified or
            ip.is_reserved
        )
    except ValueError:
        return False


def is_noisy_entity(val: str) -> bool:
    clean = val.strip().lower()
    if not clean or len(clean) < 2:
        return True
    if clean in ("unknown", "n/a", "none", "null", "localhost"):
        return True
    if clean in GENERIC_USERS:
        return True
    for bin_name in GENERIC_BINARIES:
        if clean == bin_name or clean.endswith("\\" + bin_name) or clean.endswith("/" + bin_name):
            return True
    if is_noisy_ip(val):
        return True
    if clean.startswith("http://localhost") or clean.startswith("https://localhost"):
        return True
    if "googleapis.com/compute/v1/projects/" in clean and "/operations/" in clean:
        return True
    return False


def is_genuine_yara_l_detection(sec: Dict[str, Any], has_det_obj: bool = False) -> bool:
    """Disqualifies parser annotations (e.g. Sysmon EventID: 1) and retains genuine YARA-L detections."""
    rule_id = (sec.get("ruleId") or "").strip()
    rule_name = (sec.get("ruleName") or "").strip()
    if rule_name.lower().startswith("eventid:") or rule_name.lower().startswith("technique_id="):
        return False
    if rule_id.startswith("ru_") or rule_id.startswith("ur_"):
        return True
    if has_det_obj and rule_name and not rule_name.lower().startswith("eventid"):
        return True
    if rule_name and not rule_name.lower().startswith("eventid") and sec.get("alertState") and sec.get("severity") in ("LOW", "MEDIUM", "HIGH", "CRITICAL"):
        return True
    return False


def _resolve_entity_type(raw_type: Optional[str], raw_val: str) -> Optional[EntityType]:
    """Resolves raw entity type with fallback heuristics on the entity value."""
    if raw_type:
        try:
            return coerce_entity_type(raw_type)
        except (ValueError, TypeError):
            pass
    val_lower = raw_val.strip().lower()
    if "@" in val_lower and "." in val_lower:
        return EntityType.EMAIL
    if val_lower.startswith(("http://", "https://")):
        return EntityType.URL
    import re
    if re.match(r"^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$", val_lower):
        return EntityType.IP
    if len(val_lower) == 64 and all(c in "0123456789abcdef" for c in val_lower):
        return EntityType.SHA256
    if len(val_lower) == 32 and all(c in "0123456789abcdef" for c in val_lower):
        return EntityType.MD5
    return None


def _extract_event_entities(ev: Dict[str, Any]) -> List[Dict[str, str]]:
    """Extracts high-fidelity candidate entities (IP, USER, URL, HOSTNAME) from a UDM event."""
    candidates: List[Dict[str, str]] = []
    seen: Set[str] = set()

    def _add(identifier: Optional[str], etype: str):
        if not identifier:
            return
        clean_id = str(identifier).strip()
        if is_noisy_entity(clean_id):
            return
        key = f"{clean_id.upper()}::{etype.upper()}"
        if key not in seen:
            seen.add(key)
            candidates.append({"identifier": clean_id, "type": etype})

    # 1. Principal
    p = ev.get("principal") or {}
    if isinstance(p, dict):
        for ip in p.get("ip") or []:
            _add(ip, "IP")
        p_user = p.get("user") or {}
        if isinstance(p_user, dict):
            _add(p_user.get("userid"), "USERUNIQNAME")
            _add(p_user.get("userDisplayName"), "USERUNIQNAME")
            for email in p_user.get("emailAddresses") or []:
                _add(email, "USERUNIQNAME")
        _add(p.get("hostname"), "HOSTNAME")

    # 2. Target
    t = ev.get("target") or {}
    if isinstance(t, dict):
        for ip in t.get("ip") or []:
            _add(ip, "IP")
        t_user = t.get("user") or {}
        if isinstance(t_user, dict):
            _add(t_user.get("userid"), "USERUNIQNAME")
            _add(t_user.get("userDisplayName"), "USERUNIQNAME")
            for email in t_user.get("emailAddresses") or []:
                _add(email, "USERUNIQNAME")
        _add(t.get("hostname"), "HOSTNAME")
        _add(t.get("url"), "DestinationURL")

    # 3. Source
    s = ev.get("src") or {}
    if isinstance(s, dict):
        for ip in s.get("ip") or []:
            _add(ip, "IP")
        _add(s.get("hostname"), "HOSTNAME")

    # 4. Security Result
    sec_results = ev.get("securityResult") or ev.get("security_result") or []
    for sec in sec_results:
        if isinstance(sec, dict):
            _add(sec.get("urlBackToProduct"), "DestinationURL")
            desc = sec.get("description") or ""
            import re
            for ip in re.findall(r"\b(?:\d{1,3}\.){3}\d{1,3}\b", desc):
                _add(ip, "IP")

    return candidates


class CorrelateSilentDetectionsWorkflow:
    """Correlates a SOAR case's involved entities with silent (non-alerting) detections in UDM."""

    def __init__(self, adapter: Optional['GoogleSecOpsAdapter'] = None):
        if adapter is None:
            from adapters.google_secops import GoogleSecOpsAdapter

            adapter = GoogleSecOpsAdapter()
        self.adapter = adapter
        self.investigate_workflow = InvestigateCaseWorkflow(adapter=self.adapter)
        self.search_workflow = SearchUDMWorkflow(adapter=self.adapter)
        self.attach_workflow = AttachCaseEvidenceWorkflow(adapter=self.adapter)

    def execute(
        self,
        case_id: Union[str, int],
        lookback_hours: int = 24,
        attach_to_case: bool = False,
        attach_entities: bool = True,
        post_wall_comment: bool = True,
        entity_filter: Optional[List[str]] = None,
        max_events: int = 1000,
        correlate_detections: bool = True,
        correlate_udm_events: bool = False,
        attach_udm_events: bool = False,
        extract_entities_from_events: bool = False,
        alert_vendor_filter: Optional[str] = "Google Chronicle",
        max_entities_to_attach: int = 5,
    ) -> CaseDetectionCorrelationResult:
        """Executes entity correlation and attaches non-alerting detections or events to the case.

        Args:
            case_id: The SOAR Case ID or resource name.
            lookback_hours: How far back to search UDM relative to case creation/now (default: 24h).
            attach_to_case: If True, natively attaches discovered detections/events to the case.
            attach_entities: If True (and attach_to_case is True), attaches delta entities to the case alert.
            post_wall_comment: If True, adds a summary note to the Case Wall.
            entity_filter: Optional list of entity identifiers to restrict search to.
            max_events: Max UDM events to fetch (default: 1000).
            correlate_detections: If True, inspects and returns rule detections (default: True).
            correlate_udm_events: If True, collects and returns non-detection raw UDM events (default: False).
            attach_udm_events: If True (and attach_to_case is True), attaches raw UDM events as EVIDENCE_TYPE_EVENT (default: False).
            extract_entities_from_events: If True, extracts candidate entities from non-detection UDM events (default: False).
            alert_vendor_filter: Only consider alerts from this vendor (default: 'Google Chronicle').
            max_entities_to_attach: Maximum number of delta entities to attach to the case alert (default: 5).

        Returns:
            CaseDetectionCorrelationResult with findings and attachment records.
        """
        clean_case_id = _clean_case_id(case_id)

        # 1. Investigate case to extract entities and existing alert context
        investigation = self.investigate_workflow.execute(case_id=clean_case_id)
        
        # Vendor filtering: filter alerts to only those originating from the target vendor
        target_alerts = investigation.alerts
        if alert_vendor_filter and str(alert_vendor_filter).strip():
            v_filter = str(alert_vendor_filter).strip().lower()
            target_alerts = [
                a for a in investigation.alerts
                if (a.vendor or "").strip().lower() == v_filter
                or v_filter in (a.vendor or "").lower()
                or v_filter in (a.raw.get("sourceSystemName") or "").lower()
                or v_filter.replace(" ", "") in (a.raw.get("sourceSystemName") or "").lower()
            ]
            if not target_alerts:
                return CaseDetectionCorrelationResult(
                    case_id=clean_case_id,
                    lookback_hours=lookback_hours,
                    entities_searched=[],
                    query_used='',
                    detections_found=[],
                    events_found=[],
                    attached_evidences=[],
                    comment_id=None,
                    provenance={
                        "workflow": "case.detection.correlate",
                        "status": "NO_MATCHING_ALERTS_FOR_VENDOR",
                        "vendor_filter": alert_vendor_filter,
                        "alerts_inspected": len(investigation.alerts),
                    },
                    raw={"status": "NO_MATCHING_ALERTS_FOR_VENDOR", "vendor_filter": alert_vendor_filter},
                )

        existing_alert_rule_ids = {
            (a.raw.get("sourceRuleIdentifier") or a.rule_name or "").strip()
            for a in target_alerts
            if a.raw.get("sourceRuleIdentifier") or a.rule_name
        }

        existing_identifiers: Set[str] = {
            e.identifier.strip().upper()
            for e in investigation.entities
            if e.identifier and str(e.identifier).strip()
        }
        primary_alert_id = None
        if target_alerts:
            primary_alert_id = target_alerts[0].name.split('/')[-1] or target_alerts[0].identifier

        # 2. Collect high-signal queryable entities and establish anchor set
        case_anchors: Set[str] = set()
        query_clauses: List[str] = []
        searched_entities: List[Dict[str, Any]] = []

        for ent in investigation.entities:
            val = ent.identifier.strip()
            if is_noisy_entity(val):
                continue
            if entity_filter and val not in entity_filter:
                continue

            e_type = _resolve_entity_type(ent.entity_type, val)
            if not e_type:
                continue

            case_anchors.add(val.upper())

            try:
                clause = SearchFromEntityWorkflow.build_entity_query(e_type, val)
                query_clauses.append(f'({clause})')
                searched_entities.append({
                    'identifier': val,
                    'type': e_type.value,
                    'role': ent.role,
                })
            except Exception:
                pass

        # Extract threat IDs from vendor-filtered alerts (e.g. ticketId 'de_...')
        for a in target_alerts:
            tid = (a.raw.get("ticketId") or "").strip()
            if tid.startswith("de_"):
                clean_tid = tid[3:].lower()
                query_clauses.append(f'(security_result.threat_id = "{clean_tid}")')
                case_anchors.add(clean_tid.upper())
                searched_entities.append({
                    'identifier': clean_tid,
                    'type': 'THREAT_ID',
                    'role': 'ALERT_THREAT_ID',
                })

        if not query_clauses:
            return CaseDetectionCorrelationResult(
                case_id=clean_case_id,
                lookback_hours=lookback_hours,
                entities_searched=[],
                query_used='',
                detections_found=[],
                events_found=[],
                attached_evidences=[],
                comment_id=None,
                provenance={
                    "workflow": "case.detection.correlate",
                    "status": "NO_QUERYABLE_ANCHORS",
                },
                raw={'status': 'NO_QUERYABLE_ANCHORS'},
            )

        # Build combined query (limit to first 10 entities to keep query bounded)
        bounded_clauses = query_clauses[:10]
        combined_query = ' OR '.join(bounded_clauses)

        # Calculate time window around case created_time or now
        ref_time = investigation.created_time or datetime.now(timezone.utc)
        if ref_time.tzinfo is None:
            ref_time = ref_time.replace(tzinfo=timezone.utc)
        start_time = (ref_time - timedelta(hours=lookback_hours)).strftime('%Y-%m-%dT%H:%M:%SZ')
        end_time = (ref_time + timedelta(hours=2)).strftime('%Y-%m-%dT%H:%M:%SZ')

        from engine.domain import SearchRequest
        search_req = SearchRequest(
            query=combined_query,
            start_time=start_time,
            end_time=end_time,
            receive_limit=max_events,
            batch_size=min(max_events, 500),
        )

        session = self.search_workflow.execute(request=search_req)

        # 3. Analyze events for genuine detections, anchor corroboration, and relevant events
        detections_found: List[Dict[str, Any]] = []
        events_found: List[Dict[str, Any]] = []
        evidence_to_attach: List[Dict[str, str]] = []
        discovered_candidates: List[Dict[str, str]] = []
        seen_evidence_ids: Set[str] = set()
        seen_det_keys: Set[str] = set()

        for ev in session.events:
            meta = ev.get('metadata') or {}
            event_id = meta.get('id')
            sec_results = ev.get('securityResult') or ev.get('security_result') or []
            detection_objs = ev.get('detections') or []

            # Check if event touches case anchors (hostname, user, IP)
            ev_anchors: Set[str] = set()
            p = ev.get("principal") or {}
            if isinstance(p, dict):
                if p.get("hostname"): ev_anchors.add(p.get("hostname").strip().upper())
                p_usr = p.get("user") or {}
                if isinstance(p_usr, dict) and p_usr.get("userid"):
                    ev_anchors.add(p_usr.get("userid").strip().upper())
                for ip in p.get("ip") or []:
                    ev_anchors.add(ip.strip().upper())
            t = ev.get("target") or {}
            if isinstance(t, dict):
                if t.get("hostname"): ev_anchors.add(t.get("hostname").strip().upper())
                t_usr = t.get("user") or {}
                if isinstance(t_usr, dict) and t_usr.get("userid"):
                    ev_anchors.add(t_usr.get("userid").strip().upper())
                for ip in t.get("ip") or []:
                    ev_anchors.add(ip.strip().upper())

            is_corroborated = bool(ev_anchors.intersection(case_anchors))
            has_genuine_detection = False

            if correlate_detections:
                # Genuine detections from detections objects
                for det in detection_objs:
                    det_id = det.get('id')
                    if det_id and det_id not in seen_evidence_ids and is_corroborated:
                        seen_evidence_ids.add(det_id)
                        evidence_to_attach.append({
                            'evidenceId': det_id,
                            'evidenceType': 'EVIDENCE_TYPE_DETECTION',
                        })

                # Check securityResult entries
                for sec in sec_results:
                    if not is_genuine_yara_l_detection(sec, has_det_obj=bool(detection_objs)):
                        continue

                    rule_name = sec.get('ruleName') or sec.get('ruleId')
                    rule_id = sec.get('ruleId') or ''
                    alert_state = (sec.get('alertState') or 'NOT_ALERTING').upper()
                    is_alerting = alert_state == 'ALERTING'
                    is_silent = not is_alerting and rule_id not in existing_alert_rule_ids

                    det_key = f"{rule_name}::{rule_id}::{event_id}"
                    if det_key in seen_det_keys:
                        continue
                    seen_det_keys.add(det_key)

                    has_genuine_detection = True
                    detection_entry = {
                        'rule_name': rule_name,
                        'rule_id': rule_id,
                        'alert_state': alert_state,
                        'is_alerting': is_alerting,
                        'is_silent': is_silent,
                        'event_id': event_id,
                        'summary': sec.get('summary'),
                        'severity': sec.get('severity'),
                        'corroborated': is_corroborated,
                    }
                    detections_found.append(detection_entry)

                    # Only attach to case if corroborated with anchor
                    if is_corroborated and not is_alerting and attach_udm_events:
                        if event_id and event_id not in seen_evidence_ids:
                            seen_evidence_ids.add(event_id)
                            evidence_to_attach.append({
                                'evidenceId': event_id,
                                'evidenceType': 'EVIDENCE_TYPE_EVENT',
                            })

                # Extract entities only from genuine, corroborated detections
                if has_genuine_detection and is_corroborated:
                    for cand in _extract_event_entities(ev):
                        cid_upper = cand['identifier'].strip().upper()
                        if cid_upper not in existing_identifiers and cid_upper not in case_anchors:
                            discovered_candidates.append(cand)

            if not has_genuine_detection:
                if correlate_udm_events and event_id:
                    events_found.append({
                        'event_id': event_id,
                        'event_type': meta.get('eventType'),
                        'product_log_id': meta.get('productLogId'),
                        'corroborated': is_corroborated,
                    })
                    if attach_udm_events and is_corroborated and event_id not in seen_evidence_ids:
                        seen_evidence_ids.add(event_id)
                        evidence_to_attach.append({
                            'evidenceId': event_id,
                            'evidenceType': 'EVIDENCE_TYPE_EVENT',
                        })
                if extract_entities_from_events and is_corroborated:
                    for cand in _extract_event_entities(ev):
                        cid_upper = cand['identifier'].strip().upper()
                        if cid_upper not in existing_identifiers and cid_upper not in case_anchors:
                            discovered_candidates.append(cand)

        # 4. Attach evidence and delta entities if requested
        attached_items: List[CaseEvidenceItem] = []
        if attach_to_case and evidence_to_attach:
            # Batch attach (up to 50 items per call)
            attach_res = self.attach_workflow.execute(
                case_id=clean_case_id,
                evidence_items=evidence_to_attach[:50],
            )
            attached_items = attach_res.evidence_items

        attached_entities: List[Dict[str, Any]] = []
        if attach_to_case and attach_entities and primary_alert_id and discovered_candidates:
            seen_cand_keys: Set[str] = set()
            for cand in discovered_candidates:
                if len(attached_entities) >= max_entities_to_attach:
                    break
                cid = cand['identifier'].strip()
                ctype = cand['type'].strip()
                ckey = f"{cid.upper()}::{ctype.upper()}"
                if ckey in seen_cand_keys or cid.upper() in existing_identifiers or cid.upper() in case_anchors:
                    continue
                seen_cand_keys.add(ckey)
                try:
                    res = self.adapter.add_case_alert_entity(
                        case_id=clean_case_id,
                        case_alert_id=primary_alert_id,
                        identifier=cid,
                        entity_type=ctype,
                    )
                    attached_entities.append({
                        'identifier': cid,
                        'type': ctype,
                        'entity_id': res.get('id'),
                        'status': 'ATTACHED',
                    })
                    existing_identifiers.add(cid.upper())
                except Exception as e:
                    attached_entities.append({
                        'identifier': cid,
                        'type': ctype,
                        'error': str(e),
                        'status': 'FAILED',
                    })

        # 5. Post summary comment to Case Wall if requested
        comment_id: Optional[str] = None
        if post_wall_comment and (detections_found or events_found or attached_items or attached_entities):
            comment_lines = [
                f'### [Automated Correlation] Silent Detections & Evidence',
                f'- **Lookback Window**: {lookback_hours} hours ({start_time} to {end_time})',
                f'- **Entities Searched**: {len(searched_entities)}',
                f'- **Total Detections Found**: {len(detections_found)}',
                f'- **UDM Events Correlated**: {len(events_found)}',
                f'- **Evidence Items Attached**: {len(attached_items)}',
                f'- **New Entities Attached to Case**: {len(attached_entities)}',
            ]
            if detections_found:
                comment_lines.append("\n**Discovered Detections:**")
                for d in detections_found[:5]:
                    rule_label = d.get("rule_name") or "Unknown Rule"
                    state_label = d.get("alert_state") or "SILENT"
                    sev_label = d.get("severity") or "N/A"
                    comment_lines.append(f"- `{rule_label}` (State: {state_label}, Severity: {sev_label})")
            if events_found:
                comment_lines.append(f"\n**Discovered UDM Events ({len(events_found)} total):**")
                for ev_item in events_found[:5]:
                    ev_type = ev_item.get("event_type") or "UNKNOWN"
                    comment_lines.append(f"- `{ev_item.get('event_id')}` (Type: {ev_type})")
            if attached_entities:
                comment_lines.append("\n**Newly Attached Entities:**")
                for ae in attached_entities[:5]:
                    status_suffix = f" (ID: {ae.get('entity_id')})" if ae.get('status') == 'ATTACHED' else f" (Failed: {ae.get('error')})"
                    comment_lines.append(f"- `{ae['identifier']}` ({ae['type']}){status_suffix}")
            comment_text = "\n".join(comment_lines)
            try:
                comment_res = self.adapter.create_case_comment(case_id=clean_case_id, comment=comment_text)
                comment_id = comment_res.get('name', '').split('/')[-1] or 'created'
            except Exception:
                pass

        return CaseDetectionCorrelationResult(
            case_id=clean_case_id,
            lookback_hours=lookback_hours,
            entities_searched=searched_entities,
            query_used=combined_query,
            detections_found=detections_found,
            events_found=events_found,
            attached_evidences=attached_items,
            attached_entities=attached_entities,
            comment_id=comment_id,
            provenance={
                "workflow": "case.detection.correlate",
                "lookback_hours": lookback_hours,
                "entities_count": len(searched_entities),
                "detections_count": len(detections_found),
                "events_count": len(events_found),
                "attached_count": len(attached_items),
                "attached_entities_count": len(attached_entities),
                "correlate_detections": correlate_detections,
                "correlate_udm_events": correlate_udm_events,
                "attach_udm_events": attach_udm_events,
            },
            raw={
                'events_scanned': len(session.events),
                'total_evidence_candidates': len(evidence_to_attach),
                'total_delta_entity_candidates': len(discovered_candidates),
            },
        )

