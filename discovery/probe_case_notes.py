"""Live Endpoint Verification Probe for Case Notes.
Tests all endpoints from take2/case_notes.md against live Google SecOps.
"""

import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from adapters.google_secops import GoogleSecOpsAdapter


adapter = GoogleSecOpsAdapter()
token = adapter._get_auth_token()
base_url = f"https://us-chronicle.googleapis.com/v1alpha/projects/{adapter.project_id}/locations/{adapter.location}/instances/{adapter.customer_id}"

headers = {
    "Authorization": f"Bearer {token}",
    "Accept": "application/json",
    "Content-Type": "application/json",
}

results = {}

def probe(name, method, url, body=None):
    print(f"[*] Probing {name}: {method} {url}")
    req = urllib.request.Request(url, headers=headers, method=method)
    data = json.dumps(body).encode("utf-8") if body else None
    try:
        with urllib.request.urlopen(req, data=data, timeout=30) as resp:
            status = resp.status
            raw = resp.read().decode("utf-8")
            parsed = json.loads(raw) if raw else {}
            # Summarize response
            if isinstance(parsed, dict):
                keys = list(parsed.keys())
                item_counts = {k: len(v) if isinstance(v, list) else type(v).__name__ for k, v in parsed.items()}
            elif isinstance(parsed, list):
                keys = f"List[{len(parsed)}]"
                item_counts = len(parsed)
            else:
                keys = type(parsed).__name__
                item_counts = None
            results[name] = {
                "status": status,
                "success": True,
                "keys": keys,
                "summary": item_counts,
                "sample": str(parsed)[:400]
            }
            print(f"    [+] Success: HTTP {status}, keys={keys}")
    except urllib.error.HTTPError as e:
        err_body = e.read().decode("utf-8") if e.fp else ""
        results[name] = {
            "status": e.code,
            "success": False,
            "error": err_body[:400]
        }
        print(f"    [-] HTTPError {e.code}: {err_body[:200]}")
    except Exception as e:
        results[name] = {
            "status": None,
            "success": False,
            "error": str(e)
        }
        print(f"    [-] Error: {e}")

# Known live case
case_id = "104185"

# 1. List Cases
probe("list_cases", "GET", f"{base_url}/cases?expand=sla,tags,customFieldValues&filter=status%20=%20%27OPENED%27&orderBy=id%20desc&pageSize=5")

# 2. Case Queue Filters
probe("case_queue_filters", "GET", f"{base_url}/caseQueueFilters?expand=criteria&pageSize=10")

# 3. Get Case with expansions
probe("get_case_expanded", "GET", f"{base_url}/cases/{case_id}?expand=products,%20tasks,%20tags,%20closureDetails,%20sla,%20alertsSla")

# 4. Detections (UDM)
probe("case_detections", "GET", f"{base_url}/cases/{case_id}/detections?pageSize=10")

# 5. Case Alerts (legacy SOAR)
probe("case_alerts", "GET", f"{base_url}/cases/{case_id}/caseAlerts?expand=sla,tags&pageSize=10")

# 6. Case Overview Data
probe("case_overview_data", "GET", f"{base_url}/cases/{case_id}:caseOverviewData")

# 7. Resolve Overview Widget
# (Will test once we get a widget identifier from case_overview_data)

# 8. Case Wall Records
probe("case_wall_records", "GET", f"{base_url}/cases/{case_id}/caseWallRecords?filter=caseId%20=%20{case_id}&orderBy=createTime%20desc&pageSize=10")

# 9. Case Wall Fetch Activities Count
probe("case_wall_activities_count", "GET", f"{base_url}/cases/{case_id}/caseWallRecords:fetchActivitiesCount")

# 10. SOC Roles
probe("soc_roles", "GET", f"{base_url}/socRoles?pageSize=10")

# 11. Case Stage Definitions
probe("case_stage_definitions", "GET", f"{base_url}/caseStageDefinitions?orderBy=order&pageSize=20")

# 12. Legacy SOAR Users
probe("legacy_soar_users", "GET", f"{base_url}/legacySoarUsers?pageSize=10")

# 13. TINA Investigations
probe("investigations", "GET", f"{base_url}/investigations?orderBy=start_time%20desc&pageSize=10")

print("\n--- ALL RESULTS SUMMARY ---")
print(json.dumps(results, indent=2))
