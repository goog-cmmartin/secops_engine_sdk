"""Live Probe for SOAR Case Search & Entity Search Endpoints."""

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

def post_json(custom_verb, body):
    url = f"{base_url}/legacySearches:{custom_verb}"
    print(f"\n[*] Probing POST {url}")
    print(f"    Body: {json.dumps(body)}")
    req = urllib.request.Request(url, headers=headers, method="POST", data=json.dumps(body).encode("utf-8"))
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            raw = resp.read().decode("utf-8")
            parsed = json.loads(raw) if raw else {}
            print(f"    [+] HTTP {resp.status}, keys={list(parsed.keys()) if isinstance(parsed, dict) else type(parsed)}")
            return resp.status, parsed
    except urllib.error.HTTPError as e:
        err = e.read().decode("utf-8") if e.fp else ""
        print(f"    [-] HTTP {e.code}: {err[:300]}")
        return e.code, {"error": err}
    except Exception as e:
        print(f"    [-] Error: {e}")
        return None, {"error": str(e)}

# 1. Probe Filter Values for Cases
status, f_env = post_json("legacyGetCasesFilterValues", {"typeOfFilter": "ENVIRONMENTS", "numberOfValuesToReturn": 10, "searchTerm": ""})
print(f"    Environments: {f_env}")

status, f_tags = post_json("legacyGetCasesFilterValues", {"typeOfFilter": "TAGS", "numberOfValuesToReturn": 10, "searchTerm": ""})
print(f"    Tags: {f_tags}")

# 2. Probe legacyCaseSearchEverything (Broad Search)
search_payload = {
    "startTime": "2026-08-01T00:00:00.000Z",
    "endTime": "2026-08-19T23:59:59.999Z",
    "title": "",
    "tags": [],
    "ruleGenerator": [],
    "caseSource": [],
    "stage": [],
    "environments": [],
    "assignedUsers": [],
    "products": [],
    "ports": [],
    "categoryOutcomes": [],
    "importance": [],
    "priorities": [],
    "incident": [],
    "timeRangeFilter": "CUSTOM",
    "paging": {"pageSize": 10, "requestedPage": 0},
    "pageSize": 10,
    "requestedPage": 0
}
status, cases_res = post_json("legacyCaseSearchEverything", search_payload)
print(f"    Total Cases Found: {cases_res.get('totalCount')}")
if cases_res.get("results"):
    sample_case = cases_res["results"][0]
    print(f"    Sample Case Result: id={sample_case.get('id')}, title={sample_case.get('title')}, priority={sample_case.get('priority')}, stage={sample_case.get('stage')}")

# 3. Probe legacyCaseSearchEverything by specific search term (e.g., "File IoCs" or "PROMPTFLUX" or "104185")
search_kw_payload = dict(search_payload)
search_kw_payload["title"] = "File IoCs"
status, kw_res = post_json("legacyCaseSearchEverything", search_kw_payload)
print(f"    Keyword 'File IoCs' Found: {kw_res.get('totalCount')}")

# 4. Probe Entity Filter Values
status, ent_filter = post_json("legacyGetEntitiesFilterValues", {"typeOfFilter": "ENVIRONMENT", "numberOfValuesToReturn": 10, "searchTerm": ""})
print(f"    Entity Filter Values: {ent_filter}")

# 5. Probe legacyEntitySearchCount
status, ent_search = post_json("legacyEntitySearchCount", {"term": "Contains:CHRIS", "type": [], "networkName": [], "environmentsName": []})
print(f"    Entity Search Results: total={len(ent_search.get('results', [])) if isinstance(ent_search, dict) else 0}")
if isinstance(ent_search, dict) and ent_search.get("results"):
    print(f"    Sample Entity: {ent_search['results'][0].get('entity', {}).get('identifier')}")
