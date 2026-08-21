"""Probe stage update error body."""
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

case_id = "104185"
case_name = f"projects/{adapter.project_id}/locations/{adapter.location}/instances/{adapter.customer_id}/cases/{case_id}"

# Check caseStageDefinitions
req = urllib.request.Request(f"{base_url}/caseStageDefinitions", headers=headers)
with urllib.request.urlopen(req) as resp:
    stages = json.loads(resp.read().decode("utf-8"))
    print("Stages available:")
    for s in stages.get("caseStageDefinitions", []):
        print(f"  {s.get('name')}: {s.get('displayName')} (id: {s.get('name').split('/')[-1]})")

# Try patch with stage displayName or ID
for test_payload in [
    {"name": case_name, "stage": "Triage"},
    {"name": case_name, "stage": "Investigation"},
    {"name": case_name, "stage": "1"},
    {"stage": "Triage"},
    {"stage": "1"},
]:
    url = f"{base_url}/cases/{case_id}?updateMask=stage"
    req = urllib.request.Request(url, headers=headers, method="PATCH")
    data = json.dumps(test_payload).encode("utf-8")
    try:
        with urllib.request.urlopen(req, data=data) as resp:
            print(f"[+] Success with {test_payload}: {resp.status}")
    except urllib.error.HTTPError as e:
        print(f"[-] HTTP {e.code} with {test_payload}: {e.read().decode('utf-8')}")
