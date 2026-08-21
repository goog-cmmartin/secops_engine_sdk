"""Probe Case Assignment."""
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

# Get case to see current assignee
req = urllib.request.Request(f"{base_url}/cases/{case_id}", headers=headers)
with urllib.request.urlopen(req) as resp:
    case = json.loads(resp.read().decode("utf-8"))
    print(f"Current assignee: {case.get('assignee')}")

# Get legacy soar users and soc roles
req_users = urllib.request.Request(f"{base_url}/legacySoarUsers?pageSize=3", headers=headers)
with urllib.request.urlopen(req_users) as resp:
    users = json.loads(resp.read().decode("utf-8"))
    print(f"Users sample: {[(u.get('name'), u.get('email'), u.get('displayName')) for u in users.get('legacySoarUsers', [])]}")

req_roles = urllib.request.Request(f"{base_url}/socRoles?pageSize=3", headers=headers)
with urllib.request.urlopen(req_roles) as resp:
    roles = json.loads(resp.read().decode("utf-8"))
    print(f"Roles sample: {[(r.get('name'), r.get('displayName')) for r in roles.get('socRoles', [])]}")

# Try PATCH with updateMask vs without updateMask
# Test with current assignee to avoid breaking case
curr_assignee = case.get("assignee")
url = f"{base_url}/cases/{case_id}"
req_patch = urllib.request.Request(url, headers=headers, method="PATCH")
data = json.dumps({"assignee": curr_assignee}).encode("utf-8")
try:
    with urllib.request.urlopen(req_patch, data=data) as resp:
        print(f"[+] PATCH assignee without updateMask: HTTP {resp.status}")
except urllib.error.HTTPError as e:
    print(f"[-] PATCH assignee error: {e.code} - {e.read().decode('utf-8')}")

url_mask = f"{base_url}/cases/{case_id}?updateMask=assignee"
req_patch_mask = urllib.request.Request(url_mask, headers=headers, method="PATCH")
try:
    with urllib.request.urlopen(req_patch_mask, data=data) as resp:
        print(f"[+] PATCH assignee with updateMask=assignee: HTTP {resp.status}")
except urllib.error.HTTPError as e:
    print(f"[-] PATCH assignee with mask error: {e.code} - {e.read().decode('utf-8')}")
