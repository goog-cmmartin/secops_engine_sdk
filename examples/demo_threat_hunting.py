#!/usr/bin/env python3
"""
Threat Hunting Query Reference

This script demonstrates threat hunting query patterns for use with Chronicle SIEM.
It shows how to construct UDM queries for common threat hunting scenarios.

Note: UDM search is a two-step process in the SDK:
  1. start_search() - initiates the search and returns an operation_id
  2. get_events() - retrieves events in batches using the operation_id

For working examples of SDK functionality, see:
  - demo_case_triage.py - Complete case analysis workflow
  - export_batch_udm.py - Batch UDM event export

Usage:
    python examples/demo_threat_hunting.py
"""

from datetime import datetime, timedelta, timezone


# Threat hunting query catalog
HUNT_QUERIES = {
    "Lateral Movement via Remote Execution": {
        "description": "Detects use of remote execution tools like PSExec, WinRM, or WMIC that may indicate lateral movement",
        "query": '''
metadata.event_type = "PROCESS_LAUNCH" AND
(
  target.process.file.full_path = /.*psexec.*/i OR
  target.process.file.full_path = /.*winrm.*/i OR
  target.process.file.full_path = /.*wmic.*/i OR
  target.process.command_line = /.*Invoke-Command.*/i OR
  target.process.command_line = /.*Enter-PSSession.*/i
)
        '''.strip(),
        "severity": "HIGH",
        "mitre_attack": "T1570 - Lateral Tool Transfer, T1021 - Remote Services"
    },
    
    "Credential Dumping Tools": {
        "description": "Detects execution of tools commonly used for credential harvesting like Mimikatz, ProcDump, or NTDSUtil",
        "query": '''
metadata.event_type = "PROCESS_LAUNCH" AND
(
  target.process.file.full_path = /.*mimikatz.*/i OR
  target.process.file.full_path = /.*procdump.*/i OR
  target.process.file.full_path = /.*ntdsutil.*/i OR
  target.process.command_line = /.*lsass.*/i OR
  target.process.command_line = /.*SeDebugPrivilege.*/i
)
        '''.strip(),
        "severity": "CRITICAL",
        "mitre_attack": "T1003 - OS Credential Dumping"
    },
    
    "Suspicious PowerShell Execution": {
        "description": "Detects PowerShell executed with suspicious encoded commands or download cradles",
        "query": '''
metadata.event_type = "PROCESS_LAUNCH" AND
target.process.file.full_path = /.*powershell.*/i AND
(
  target.process.command_line = /.*-enc.*-nop.*/i OR
  target.process.command_line = /.*DownloadString.*/i OR
  target.process.command_line = /.*IEX.*Net.WebClient.*/i OR
  target.process.command_line = /.*hidden.*bypass.*/i
)
        '''.strip(),
        "severity": "HIGH",
        "mitre_attack": "T1059.001 - PowerShell, T1140 - Deobfuscate/Decode Files or Information"
    },
    
    "Unusual Network Connections": {
        "description": "Detects network connections to uncommon high ports or suspicious services",
        "query": '''
metadata.event_type = "NETWORK_CONNECTION" AND
(
  target.port > 49152 OR
  target.port = 4444 OR
  target.port = 5555 OR
  target.port = 8080 OR
  target.port = 9999
) AND
NOT target.ip = /^10\\..*/ AND
NOT target.ip = /^192\\.168\\..*/ AND
NOT target.ip = /^172\\.(1[6-9]|2[0-9]|3[01])\\..*/
        '''.strip(),
        "severity": "MEDIUM",
        "mitre_attack": "T1071 - Application Layer Protocol, T1095 - Non-Application Layer Protocol"
    },
    
    "Scheduled Task Creation": {
        "description": "Detects creation of scheduled tasks which may be used for persistence",
        "query": '''
metadata.event_type = "PROCESS_LAUNCH" AND
(
  target.process.file.full_path = /.*schtasks.*/i OR
  target.process.file.full_path = /.*at.exe/i
) AND
target.process.command_line = /.*/create.*/i
        '''.strip(),
        "severity": "MEDIUM",
        "mitre_attack": "T1053.005 - Scheduled Task"
    },
    
    "Registry Persistence": {
        "description": "Detects modifications to common registry persistence locations",
        "query": '''
metadata.event_type = "REGISTRY_MODIFICATION" AND
(
  target.registry.registry_key = /.*\\\\Software\\\\Microsoft\\\\Windows\\\\CurrentVersion\\\\Run.*/i OR
  target.registry.registry_key = /.*\\\\Software\\\\Microsoft\\\\Windows\\\\CurrentVersion\\\\RunOnce.*/i OR
  target.registry.registry_key = /.*\\\\CurrentVersion\\\\Winlogon.*/i
)
        '''.strip(),
        "severity": "MEDIUM",
        "mitre_attack": "T1547.001 - Registry Run Keys / Startup Folder"
    },
    
    "Suspicious Service Creation": {
        "description": "Detects creation of new Windows services which may be used for persistence or privilege escalation",
        "query": '''
metadata.event_type = "SERVICE_CREATION" OR
(
  metadata.event_type = "PROCESS_LAUNCH" AND
  target.process.file.full_path = /.*sc.exe/i AND
  target.process.command_line = /.*create.*/i
)
        '''.strip(),
        "severity": "HIGH",
        "mitre_attack": "T1543.003 - Create or Modify System Process: Windows Service"
    },
    
    "Data Exfiltration via Archive": {
        "description": "Detects creation of archives (zip, rar, 7z) which may indicate data staging for exfiltration",
        "query": '''
metadata.event_type = "FILE_CREATION" AND
(
  target.file.full_path = /.*\\.zip$/i OR
  target.file.full_path = /.*\\.rar$/i OR
  target.file.full_path = /.*\\.7z$/i
) AND
target.file.size > 10485760
        '''.strip(),
        "severity": "MEDIUM",
        "mitre_attack": "T1560 - Archive Collected Data"
    }
}


def print_hunt_catalog():
    """Print the threat hunting query catalog."""
    print("=" * 80)
    print("THREAT HUNTING QUERY CATALOG")
    print("=" * 80)
    print()
    
    for idx, (hunt_name, hunt_data) in enumerate(HUNT_QUERIES.items(), 1):
        print(f"{idx}. {hunt_name}")
        print(f"   Severity: {hunt_data['severity']}")
        print(f"   MITRE ATT&CK: {hunt_data['mitre_attack']}")
        print(f"   Description: {hunt_data['description']}")
        print()
        print(f"   UDM Query:")
        for line in hunt_data['query'].split('\n'):
            print(f"   {line}")
        print()
        print("-" * 80)
        print()


def print_usage_example():
    """Print SDK usage examples for UDM search."""
    print("=" * 80)
    print("SDK USAGE EXAMPLES")
    print("=" * 80)
    print()
    
    print("1. BASIC UDM SEARCH")
    print("-" * 80)
    print('''
from engine import SecOpsEngine
from datetime import datetime, timedelta, timezone

engine = SecOpsEngine()

# Define time range
end_time = datetime.now(timezone.utc)
start_time = end_time - timedelta(days=7)

# Start a UDM search
query = """
metadata.event_type = "PROCESS_LAUNCH" AND
target.process.file.full_path = /.*powershell.*/i
"""

operation_id = engine.adapter.start_search(
    query=query,
    start_time=start_time.isoformat(),
    end_time=end_time.isoformat(),
    max_events=1000
)

# Retrieve results in batches
start_index = 0
batch_size = 500
all_events = []

while True:
    result = engine.adapter.get_events(
        operation_id=operation_id,
        start_index=start_index,
        batch_size=batch_size
    )
    
    batch_events = result.events if hasattr(result, 'events') else []
    if not batch_events:
        break
    
    all_events.extend(batch_events)
    start_index += len(batch_events)
    
    has_more = result.has_more if hasattr(result, 'has_more') else False
    if not has_more or len(batch_events) < batch_size:
        break

print(f"Found {len(all_events)} events")
    '''.strip())
    print()
    print()
    
    print("2. ANALYZING UDM EVENTS")
    print("-" * 80)
    print('''
# Extract information from UDM events
hostnames = set()
users = set()

for event in all_events:
    # Principal (source) information
    principal = event.get('principal', {})
    if 'hostname' in principal:
        hostnames.add(principal['hostname'])
    if 'user' in principal:
        user = principal['user']
        if isinstance(user, dict) and 'userid' in user:
            users.add(user['userid'])
    
    # Target (destination) information
    target = event.get('target', {})
    if 'process' in target:
        process = target['process']
        if isinstance(process, dict):
            print(f"Process: {process.get('command_line', 'N/A')}")

print(f"Unique hosts: {len(hostnames)}")
print(f"Unique users: {len(users)}")
    '''.strip())
    print()
    print()
    
    print("3. CREATING CASES FROM FINDINGS")
    print("-" * 80)
    print('''
# Create a case for suspicious findings
if len(all_events) > 0:
    case_result = engine.create_case(
        title="Suspicious PowerShell Activity Detected",
        description=f"Automated hunt detected {len(all_events)} suspicious PowerShell executions",
        priority="HIGH",
        stage="Investigation"
    )
    case_id = case_result.case_id
    
    # Add analysis comment
    comment = f"""
AUTOMATED THREAT HUNT RESULTS

Hunt: Suspicious PowerShell Execution
Events Found: {len(all_events)}
Unique Hosts: {len(hostnames)}
Unique Users: {len(users)}

RECOMMENDATION:
• Review command lines for malicious patterns
• Investigate affected hosts for additional IOCs
• Check for lateral movement from affected systems
    """
    
    engine.add_case_comment(case_id=case_id, comment=comment)
    print(f"Created case {case_id}")
    '''.strip())
    print()
    print()


def print_best_practices():
    """Print threat hunting best practices."""
    print("=" * 80)
    print("THREAT HUNTING BEST PRACTICES")
    print("=" * 80)
    print()
    
    practices = [
        {
            "title": "Start Broad, Then Narrow",
            "description": "Begin with general queries to understand the environment, then refine based on anomalies"
        },
        {
            "title": "Use Time-Boxing",
            "description": "Limit searches to reasonable time windows (7-30 days) to avoid overwhelming results"
        },
        {
            "title": "Baseline Normal Behavior",
            "description": "Understand what's normal in your environment before hunting for abnormal activity"
        },
        {
            "title": "Combine Multiple Data Sources",
            "description": "Correlate UDM events with case data, threat intelligence, and external context"
        },
        {
            "title": "Document Findings",
            "description": "Create cases and add detailed comments for all significant findings"
        },
        {
            "title": "Iterate and Refine",
            "description": "Continuously improve hunt queries based on false positives and new intelligence"
        },
        {
            "title": "Automate What Works",
            "description": "Convert successful manual hunts into automated detection rules"
        },
        {
            "title": "Share Knowledge",
            "description": "Document successful hunts and share queries with the security team"
        }
    ]
    
    for idx, practice in enumerate(practices, 1):
        print(f"{idx}. {practice['title']}")
        print(f"   {practice['description']}")
        print()


def main():
    print()
    print_hunt_catalog()
    print_usage_example()
    print_best_practices()
    
    print("=" * 80)
    print("NEXT STEPS")
    print("=" * 80)
    print()
    print("1. Review the query catalog and select hunts relevant to your environment")
    print("2. Customize queries based on your organization's baseline and threat model")
    print("3. Execute hunts using the SDK examples above")
    print("4. Analyze results and create cases for significant findings")
    print("5. Document successful hunts and convert them to automated detections")
    print()
    print("For working SDK examples, see:")
    print("  • demo_case_triage.py - Complete case analysis workflow")
    print("  • export_batch_udm.py - Batch UDM event export")
    print()
    print("For Chronicle UDM reference:")
    print("  • https://cloud.google.com/chronicle/docs/reference/udm-field-list")
    print()


if __name__ == "__main__":
    main()
