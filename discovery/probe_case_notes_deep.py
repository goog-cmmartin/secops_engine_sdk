"""Detailed Probe for Widget Resolution, Pagination, and Case Mutations."""

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

def request_json(method, url, body=None):
    req = urllib.request.Request(url, headers=headers, method=method)
    data = json.dumps(body).encode("utf-8") if body else None
    with urllib.request.urlopen(req, data=data, timeout=30) as resp:
        return resp.status, json.loads(resp.read().decode("utf-8"))

case_id = "104185"
case_name = f"projects/{adapter.project_id}/locations/{adapter.location}/instances/{adapter.customer_id}/cases/{case_id}"

# 1. Resolve Overview Widget
widget_id = "227f9551-e4bd-4478-9133-b1d40a56bf23"
url = f"{base_url}/cases/{case_id}:resolveOverviewWidget?firstRequest=true&forceRefresh=true&widgetIdentifier={widget_id}"
try:
    status, data = request_json("GET", url)
    print(f"[+] resolveOverviewWidget: HTTP {status}, keys={list(data.keys())}")
    print(f"    sample={str(data)[:300]}")
except Exception as e:
    print(f"[-] resolveOverviewWidget failed: {e}")

# 2. Case Wall pagination verification
# Check if caseWallRecords uses nextPageToken or fetchActivitiesCount
url_wall = f"{base_url}/cases/{case_id}/caseWallRecords?filter=caseId%20=%20{case_id}&orderBy=createTime%20desc&pageSize=3"
status, data = request_json("GET", url_wall)
print(f"\n[+] caseWallRecords: HTTP {status}")
print(f"    keys={list(data.keys())}")
print(f"    records_count={len(data.get('caseWallRecords', []))}")
print(f"    nextPageToken={data.get('nextPageToken')}")
print(f"    totalSize={data.get('totalSize')}")

# If nextPageToken present, test page 2
if data.get("nextPageToken"):
    page_token = urllib.parse.quote(data["nextPageToken"])
    url_wall_p2 = f"{base_url}/cases/{case_id}/caseWallRecords?filter=caseId%20=%20{case_id}&orderBy=createTime%20desc&pageSize=3&pageToken={page_token}"
    status2, data2 = request_json("GET", url_wall_p2)
    print(f"    page 2 records_count={len(data2.get('caseWallRecords', []))}")

# 3. Test Mutation: Mark Case as Important (and restore)
# First get current state
status, current_case = request_json("GET", f"{base_url}/cases/{case_id}")
current_important = current_case.get("important", False)
print(f"\n[+] Current Case {case_id} important={current_important}")

# Toggle important
toggle_url = f"{base_url}/cases/{case_id}?updateMask=important"
patch_body = {
    "name": case_name,
    "important": not current_important
}
status, patched = request_json("PATCH", toggle_url, patch_body)
print(f"[+] PATCH updateMask=important: HTTP {status}, new important={patched.get('important')}")

# Restore original important
patch_body_restore = {
    "name": case_name,
    "important": current_important
}
status, restored = request_json("PATCH", toggle_url, patch_body_restore)
print(f"[+] PATCH updateMask=important restored: HTTP {status}, important={restored.get('important')}")

# 4. Test Mutation: Update Stage (Triage)
current_stage = current_case.get("stage", "Triage")
print(f"\n[+] Current Case {case_id} stage={current_stage}")
stage_url = f"{base_url}/cases/{case_id}?updateMask=stage"
patch_stage_body = {
    "name": case_name,
    "stage": current_stage
}
status, stage_patched = request_json("PATCH", stage_url, patch_stage_body)
print(f"[+] PATCH updateMask=stage: HTTP {status}, stage={stage_patched.get('stage')}")

# 5. Dual Ontology Inspection: Detections vs Case Alerts
print(f"\n[+] Dual Ontology check:")
status, det_data = request_json("GET", f"{base_url}/cases/{case_id}/detections?pageSize=1")
status, alert_data = request_json("GET", f"{base_url}/cases/{case_id}/caseAlerts?pageSize=1")

if det_data.get("caseDetections"):
    d0 = det_data["caseDetections"][0]
    print(f"    Detection [UDM Native] keys={list(d0.keys())}")
    print(f"    Collection type={d0.get('collection', {}).get('type')}")
    print(f"    Detection rule={d0.get('collection', {}).get('detection', [{}])[0].get('ruleName')}")

if alert_data.get("caseAlerts"):
    a0 = alert_data["caseAlerts"][0]
    print(f"    Alert [Legacy SOAR] keys={list(a0.keys())}")
    print(f"    Identifier={a0.get('identifier')}")
    print(f"    Vendor={a0.get('vendor')}, Product={a0.get('product')}")
