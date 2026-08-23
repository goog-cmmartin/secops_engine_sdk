#!/usr/bin/env python3
"""
Automated Case Triage Demonstration

This script demonstrates automated case triage using the SecOps Engine SDK.
It finds a recent case, analyzes its alerts and entities, generates a triage
report, and adds an automated triage comment to the case.

Usage:
    python examples/demo_case_triage.py
"""

from engine import SecOpsEngine
from datetime import datetime

def main():
    print("=" * 80)
    print("AUTOMATED CASE TRIAGE DEMONSTRATION")
    print("=" * 80)
    print()

    # Initialize engine
    engine = SecOpsEngine()
    print("✅ Connected to SecOps tenant")
    print()

    # STEP 1: Find most recent case
    print("📋 STEP 1: Finding Most Recent Case")
    print("-" * 80)

    try:
        result = engine.search_cases(query="", page_size=1, page_number=0)
        cases = result.results if hasattr(result, 'results') else []
        
        if not cases:
            print("❌ No cases found")
            return
        
        case = cases[0]
        case_id = case.case_id
        
        print(f"✅ Found Case ID: {case_id}")
        print(f"   Title: {case.title}")
        print(f"   Priority: {case.priority}")
        print(f"   Stage: {case.stage}")
        print(f"   Closed: {'Yes' if case.is_closed else 'No'}")
        print(f"   Environment: {case.environment}")
        print(f"   Alert Count: {case.alerts_count}")
        print()

    except Exception as e:
        print(f"❌ Error finding cases: {e}")
        import traceback
        traceback.print_exc()
        return

    # STEP 2: Get alerts
    print("📊 STEP 2: Gathering Alerts")
    print("-" * 80)

    try:
        alerts = engine.adapter.list_case_alerts(case_id=str(case_id))
        print(f"✅ Found {len(alerts)} alert(s)")
        print()
    except Exception as e:
        print(f"❌ Error getting alerts: {e}")
        return

    # STEP 3: Analyze alerts and entities
    print("🔍 STEP 3: Analyzing Alerts and Entities")
    print("-" * 80)

    alert_summaries = []
    all_entities = []
    unique_entity_types = set()

    for i, alert in enumerate(alerts, 1):
        alert_name = alert.get('name', '')  # Full resource name
        display_name = alert.get('displayName', 'Unknown')
        alert_priority = alert.get('priority', 'N/A')
        alert_status = alert.get('status', 'N/A')
        rule = alert.get('ruleGenerator', 'N/A')
        
        print(f"Alert {i}: {display_name}")
        print(f"  • Rule: {rule}")
        print(f"  • Priority: {alert_priority}, Status: {alert_status}")
        
        try:
            # Use the full alert resource name
            entities = engine.adapter.list_alert_entities(alert_name=alert_name)
            
            print(f"  • Entities: {len(entities)}")
            
            entity_list = []
            for entity in entities:
                entity_type = entity.get('type', 'Unknown')
                entity_id = entity.get('identifier', 'Unknown')
                is_suspicious = entity.get('suspicious', False)
                is_internal = entity.get('internal', False)
                
                unique_entity_types.add(entity_type)
                all_entities.append({
                    'type': entity_type,
                    'identifier': entity_id,
                    'suspicious': is_suspicious,
                    'internal': is_internal,
                    'alert': display_name
                })
                
                if is_suspicious:
                    print(f"    ⚠️  {entity_type}: {entity_id} (SUSPICIOUS)")
                    entity_list.append(f"{entity_type}:{entity_id} (SUSPICIOUS)")
                else:
                    entity_list.append(f"{entity_type}:{entity_id}")
            
            alert_summaries.append({
                'name': display_name,
                'rule': rule,
                'priority': alert_priority,
                'status': alert_status,
                'entity_count': len(entities),
                'entities': entity_list
            })
            
        except Exception as e:
            print(f"  ⚠️  Could not fetch entities: {e}")
        
        print()

    suspicious_count = sum(1 for e in all_entities if e['suspicious'])
    internal_count = sum(1 for e in all_entities if e['internal'])

    print(f"📈 Summary: {len(all_entities)} entities, {suspicious_count} suspicious, {internal_count} internal")
    if unique_entity_types:
        print(f"   Types: {', '.join(sorted(unique_entity_types))}")
    print()

    # STEP 4: Generate Report
    print("=" * 80)
    print("📄 AUTOMATED TRIAGE REPORT")
    print("=" * 80)
    print()

    print(f"CASE: {case.title} (ID: {case_id})")
    print(f"  Priority: {case.priority}")
    print(f"  Stage: {case.stage}")
    print(f"  Closed: {'Yes' if case.is_closed else 'No'}")
    print(f"  Environment: {case.environment}")
    print(f"  Assigned To: {case.user_assigned or 'Unassigned'}")
    print(f"  Important: {'Yes' if case.is_important else 'No'}")
    print(f"  Incident: {'Yes' if case.is_incident else 'No'}")
    print()

    print(f"ALERTS ({len(alerts)} total):")
    for idx, summary in enumerate(alert_summaries, 1):
        print(f"  {idx}. {summary['name']}")
        print(f"     Rule: {summary['rule']}")
        print(f"     Status: {summary['status']}, Priority: {summary['priority']}")
        print(f"     Entities: {summary['entity_count']}")
        for entity in summary['entities'][:2]:
            print(f"       - {entity}")
        if len(summary['entities']) > 2:
            print(f"       ... {len(summary['entities']) - 2} more")
    print()

    print(f"ENTITY ANALYSIS:")
    print(f"  Total: {len(all_entities)}")
    if unique_entity_types:
        print(f"  Types: {', '.join(sorted(unique_entity_types))}")
    print(f"  Suspicious: {suspicious_count}")
    print(f"  Internal: {internal_count}")
    print()

    suspicious_entities = [e for e in all_entities if e['suspicious']]
    if suspicious_entities:
        print(f"⚠️  SUSPICIOUS ENTITIES ({len(suspicious_entities)}):")
        for entity in suspicious_entities[:5]:
            print(f"  • {entity['type']}: {entity['identifier']}")
            print(f"    (from alert: {entity['alert']})")
        if len(suspicious_entities) > 5:
            print(f"  ... and {len(suspicious_entities) - 5} more")
    else:
        print(f"✅ No suspicious entities detected")
    print()

    # Recommendations
    print(f"TRIAGE RECOMMENDATIONS:")
    priority_str = str(case.priority).upper()

    if 'CRITICAL' in priority_str or 'HIGH' in priority_str:
        print(f"  🚨 HIGH PRIORITY - Immediate attention required")
        print(f"  • Escalate to senior analyst")
        print(f"  • Consider activating incident response playbook")
    elif 'MEDIUM' in priority_str:
        print(f"  ⚠️  MEDIUM PRIORITY - Standard workflow")
        print(f"  • Review alerts and investigate")
    else:
        print(f"  ℹ️  INFO/LOW - Monitor and document")

    if suspicious_count > 0:
        print(f"  • Investigate {suspicious_count} suspicious entities")
        print(f"  • Run threat intelligence enrichment")
        print(f"  • Search for lateral movement patterns")

    if case.is_closed:
        print(f"  📝 Note: Case is CLOSED - review for historical context")

    print()
    print(f"NEXT STEPS:")
    print(f"  1. Review {len(alerts)} alerts for false positives")
    print(f"  2. Enrich entities with threat intelligence")
    print(f"  3. Search UDM for related activity")
    print(f"  4. Document findings and update case stage")
    if not case.user_assigned:
        print(f"  5. Assign case to appropriate analyst")
    print()

    # STEP 5: Add automated triage comment
    print("💬 Adding Automated Triage Comment to Case...")
    try:
        entity_types_str = ', '.join(sorted(unique_entity_types)) if unique_entity_types else 'None'
        
        comment = f"""AUTOMATED TRIAGE ANALYSIS
Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S UTC')}

METRICS:
• Alerts: {len(alerts)}
• Total Entities: {len(all_entities)}
• Suspicious Entities: {suspicious_count}
• Internal Entities: {internal_count}
• Entity Types: {entity_types_str}

CASE STATUS:
• Priority: {priority_str}
• Stage: {case.stage}
• Status: {'CLOSED' if case.is_closed else 'OPEN'}
• Important: {'Yes' if case.is_important else 'No'}
• Incident: {'Yes' if case.is_incident else 'No'}

ASSESSMENT:
• Risk Level: {'⚠️ HIGH' if 'CRITICAL' in priority_str or 'HIGH' in priority_str else 'ℹ️ STANDARD'}
• Suspicious Activity: {'⚠️ YES - ' + str(suspicious_count) + ' entities flagged' if suspicious_count > 0 else '✅ None detected'}

RECOMMENDATIONS:
• {'IMMEDIATE ESCALATION REQUIRED' if 'CRITICAL' in priority_str or 'HIGH' in priority_str else 'Follow standard triage workflow'}
• {'Investigate suspicious entities via threat intelligence' if suspicious_count > 0 else 'Validate entity context and alert logic'}
• Search UDM for related events and lateral movement
• Document findings and update case stage accordingly

NEXT ACTIONS:
1. Review {len(alerts)} alert(s) for false positives
2. Enrich entities with threat intelligence lookups
3. Search for related activity in UDM
4. Update case stage and document investigation

--- Auto-generated by SecOps Engine SDK ---
--- Triage Automation Demo ---"""
        
        result = engine.add_case_comment(case_id=str(case_id), comment=comment)
        print("✅ Triage comment added successfully")
        comment_id = result.id if hasattr(result, 'id') else 'Unknown'
        print(f"   Comment ID: {comment_id}")
        print()
    except Exception as e:
        print(f"⚠️  Could not add comment: {e}")
        print()

    # Summary
    print("=" * 80)
    print("✅ AUTOMATED TRIAGE COMPLETE")
    print("=" * 80)
    print()
    print(f"Case {case_id} ({case.title}) has been automatically triaged.")
    print(f"  • Analyzed {len(alerts)} alerts")
    print(f"  • Identified {len(all_entities)} entities ({len(unique_entity_types)} types)")
    if suspicious_count > 0:
        print(f"  ⚠️  {suspicious_count} suspicious entities require investigation")
    else:
        print(f"  ✅ No suspicious entities detected")
    print()
    print("The automated triage comment has been added to the case for analyst review.")
    print()


if __name__ == "__main__":
    main()
