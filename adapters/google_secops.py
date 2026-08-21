"""Google SecOps Provider Adapter.

Responsible exclusively for translating canonical domain operations to/from live
Google SecOps (Chronicle) REST & Long Running Operation (LRO) APIs.
"""

import base64
import json
import subprocess
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from engine.domain import RawLogPayload, SearchBatchResult, ValidationResult


class GoogleSecOpsAdapter:
    def __init__(
        self,
        project_id: str = "sdl-preview-americas",
        project_number: str = "37679061640",
        customer_id: str = "a556547c-1cff-43ef-a2e4-cf5b12a865df",
        location: str = "us",
        api_base: str = "https://us-chronicle.googleapis.com",
    ):
        self.project_id = project_id
        self.project_number = project_number
        self.customer_id = customer_id
        self.location = location
        self.api_base = api_base
        self._token: Optional[str] = None
        self._token_expiry: Optional[datetime] = None

    def _get_auth_token(self) -> str:
        """Acquires a valid Google Cloud ADC access token."""
        now = datetime.now(timezone.utc)
        if self._token and self._token_expiry and now < self._token_expiry:
            return self._token

        res = subprocess.run(
            ["gcloud", "auth", "print-access-token"],
            capture_output=True,
            text=True,
            check=True,
        )
        self._token = res.stdout.strip()
        self._token_expiry = now + timedelta(minutes=45)
        return self._token

    def _request(
        self,
        method: str,
        path: str,
        params: Optional[Dict[str, Any]] = None,
        body: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Executes an authenticated REST request against Google SecOps APIs with transient retry."""
        token = self._get_auth_token()
        url = f"{self.api_base}{path}"
        if params:
            query_string = urllib.parse.urlencode(params)
            url = f"{url}?{query_string}"

        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

        data = json.dumps(body).encode("utf-8") if body is not None else None
        max_retries = 3
        for attempt in range(1, max_retries + 1):
            req = urllib.request.Request(url, data=data, headers=headers, method=method)
            try:
                with urllib.request.urlopen(req, timeout=35) as resp:
                    resp_data = resp.read().decode("utf-8")
                    if not resp_data.strip():
                        return {}
                    return json.loads(resp_data)
            except urllib.error.HTTPError as e:
                if e.code in [429, 502, 503, 504] and attempt < max_retries:
                    time.sleep(1.0 * attempt)
                    continue
                error_body = e.read().decode("utf-8")
                try:
                    err_json = json.loads(error_body)
                    err_msg = err_json.get("error", {}).get("message", error_body)
                except Exception:
                    err_msg = error_body
                raise RuntimeError(f"Google SecOps API Error [{e.code}]: {err_msg}") from e
            except (TimeoutError, urllib.error.URLError) as e:
                if attempt < max_retries:
                    time.sleep(1.0 * attempt)
                    continue
                raise RuntimeError(f"Network error connecting to Google SecOps: {e}") from e

    def validate_query(self, query: str, dialect: str = "udm") -> ValidationResult:
        """Translates query.validate domain operation to :validateQuery API."""
        path = f"/v1alpha/projects/{self.project_number}/locations/{self.location}/instances/{self.customer_id}:validateQuery"
        params = {
            "dialect": "DIALECT_UDM_SEARCH",
            "allowUnreplacedPlaceholders": "false",
            "rawQuery": query,
        }
        try:
            res = self._request("GET", path, params=params)
            query_type = res.get("queryType")
            err_text = res.get("errorText") or res.get("errorType")
            is_valid = query_type == "QUERY_TYPE_UDM_QUERY" and not err_text
            return ValidationResult(
                valid=is_valid,
                dialect="udm",
                raw_query_type=query_type,
                error_message=err_text if not is_valid else None,
            )
        except Exception as e:
            return ValidationResult(
                valid=False,
                dialect="udm",
                error_message=str(e),
            )

    def start_search(
        self,
        query: str,
        start_time: str,
        end_time: str,
        max_events: int = 10000,
    ) -> str:
        """Translates search.start domain operation to legacyFetchUdmSearchView API.

        Returns normalized operation_id.
        """
        path = f"/v1alpha/projects/{self.project_number}/locations/{self.location}/instances/{self.customer_id}/legacy:legacyFetchUdmSearchView"
        body = {
            "baselineQuery": query,
            "baselineTimeRange": {
                "startTime": start_time,
                "endTime": end_time,
            },
            "snapshotQuery": None,
            "eventList": {"maxReturnedEvents": max_events},
            "fieldAggregations": {"maxValuesPerField": 60},
            "detectionOptions": {
                "detectionList": {"maxReturnedDetections": 1000},
                "snapshotQuery": 'feedback_summary.status != "CLOSED"',
                "fieldAggregations": {"maxValuesPerField": 60},
                "fetchNonAlertingDetections": True,
            },
            "prevalence": {
                "bucketSize": {"resolutionInSeconds": 900},
                "getPrevalence": True,
            },
            "caseInsensitive": True,
            "generateAiOverview": True,
            "returnOperationIdOnly": True,
        }

        res = self._request("POST", path, body=body)
        # Observed response: [{"operation": "projects/.../operations/s-udm-..."}]
        if isinstance(res, list) and len(res) > 0 and "operation" in res[0]:
            return res[0]["operation"]
        elif isinstance(res, dict) and "operation" in res:
            return res["operation"]
        elif isinstance(res, dict) and "name" in res:
            return res["name"]
        else:
            raise RuntimeError(f"Unexpected start_search response shape: {res}")

    def get_events(
        self,
        operation_id: str,
        start_index: int,
        batch_size: int = 2000,
    ) -> SearchBatchResult:
        """Translates search.events domain operation to :streamSearch API.

        Returns normalized SearchBatchResult.
        """
        # operation_id is full path or relative operation ID
        if operation_id.startswith("projects/"):
            path = f"/v1alpha/{operation_id}:streamSearch"
        else:
            path = f"/v1alpha/projects/{self.project_number}/locations/{self.location}/instances/{self.customer_id}/operations/{operation_id}:streamSearch"

        end_index = start_index + batch_size - 1
        params = {
            "eventIndexStart": start_index,
            "eventIndexEnd": end_index,
            "pageRequest": "false",
            "paginationEnabled": "true",
        }

        res = self._request("GET", path, params=params)
        all_events = []
        more_data = False

        if isinstance(res, list):
            for item in res:
                op_obj = item.get("operation", item)
                if "error" in op_obj:
                    err = op_obj["error"]
                    err_code = err.get("code", "UNKNOWN")
                    err_msg = err.get("message", str(err))
                    raise RuntimeError(f"Google SecOps Operation Error [{err_code}]: {err_msg}")
                resp_obj = op_obj.get("response", op_obj)
                events_field = resp_obj.get("events", [])
                if isinstance(events_field, dict):
                    item_events = events_field.get("events", [])
                    # Check terminal item complete / moreDataAvailable flag
                    if events_field.get("moreDataAvailable") is True:
                        more_data = True
                    elif events_field.get("complete") is True:
                        more_data = False
                    elif events_field.get("complete") is False:
                        more_data = True
                elif isinstance(events_field, list):
                    item_events = events_field
                else:
                    item_events = []

                all_events.extend(item_events)

                if resp_obj.get("moreDataAvailable") is True:
                    more_data = True
                elif resp_obj.get("complete") is True or op_obj.get("done") is True:
                    more_data = False
                elif op_obj.get("done") is False or resp_obj.get("complete") is False:
                    more_data = True
        elif isinstance(res, dict):
            op_obj = res.get("operation", res)
            if "error" in op_obj:
                err = op_obj["error"]
                err_code = err.get("code", "UNKNOWN")
                err_msg = err.get("message", str(err))
                raise RuntimeError(f"Google SecOps Operation Error [{err_code}]: {err_msg}")
            resp_obj = op_obj.get("response", op_obj)
            events_field = resp_obj.get("events", [])
            if isinstance(events_field, dict):
                all_events = events_field.get("events", [])
                if events_field.get("moreDataAvailable") is True or events_field.get("complete") is False:
                    more_data = True
            elif isinstance(events_field, list):
                all_events = events_field
            else:
                all_events = []

            more_data = more_data or resp_obj.get("moreDataAvailable", False) or not op_obj.get("done", True)

        return SearchBatchResult(
            events=all_events,
            provider_event_count=len(all_events),
            emitted_event_count=len(all_events),
            more_data_available=more_data,
            provider="google_secops",
            workflow_id="search.udm",
            operation_id=operation_id,
            requested_start_index=start_index,
            requested_end_index=end_index,
            returned_start_index=start_index,
            returned_end_index=start_index + len(all_events) - 1 if all_events else start_index,
            retrieved_at=datetime.now(timezone.utc),
            raw_response=res if isinstance(res, (dict, list)) else None,
        )

    def cancel_operation(self, operation_id: str) -> None:
        """Translates search.cancel domain operation to :cancel API."""
        if operation_id.startswith("projects/"):
            path = f"/v1alpha/{operation_id}:cancel"
        else:
            path = f"/v1alpha/projects/{self.project_number}/locations/{self.location}/instances/{self.customer_id}/operations/{operation_id}:cancel"

        try:
            self._request("POST", path, body={})
        except Exception as e:
            # Cancellation should be idempotent; log/preserve if failed
            pass

    def fetch_enriched_event(self, event_id: str) -> Dict[str, Any]:
        """Fetches full enriched UDM event by event ID from Google SecOps."""
        # Convert standard base64 to RFC 4648 section 5 URL-safe unpadded base64
        b64url_id = event_id.rstrip("=").replace("+", "-").replace("/", "_")
        path = f"/v1alpha/projects/{self.project_number}/locations/{self.location}/instances/{self.customer_id}/events/{b64url_id}:fetchEnrichedEvent"
        res = self._request("GET", path)
        if isinstance(res, dict) and "udm" in res:
            return res["udm"]
        return res if isinstance(res, dict) else {}

    def get_raw_log(self, event_id: str, log_token: Optional[str] = None) -> RawLogPayload:
        """Fetches and decodes the unparsed raw log associated with an event ID."""
        path = f"/v1alpha/projects/{self.project_number}/locations/{self.location}/instances/{self.customer_id}/legacy:legacyFindRawLogs"
        params: Dict[str, Any] = {
            "ids": event_id,
            "caseSensitive": "false",
            "maxResponseByteSize": 300000000,
            "query": "",
            "regexSearch": "false",
        }
        if log_token:
            params["batchToken"] = log_token

        res = self._request("GET", path, params=params)
        raw_logs_group = res.get("rawLogs", [])
        if not raw_logs_group:
            raise RuntimeError(f"No raw log found for event ID: {event_id}")

        first_entry = raw_logs_group[0]
        inner_entries = first_entry.get("rawLogs", [first_entry])
        if not inner_entries:
            raise RuntimeError(f"Empty raw logs payload returned for event ID: {event_id}")

        entry = inner_entries[0]
        log_bytes_b64 = entry.get("logBytes", "")
        if log_bytes_b64:
            decoded_text = base64.b64decode(log_bytes_b64).decode("utf-8", errors="replace")
        else:
            decoded_text = ""

        return RawLogPayload(
            raw_text=decoded_text,
            source_product=entry.get("sourceProduct", ""),
            log_type=entry.get("type", ""),
            timestamp=entry.get("timestamp"),
            raw_bytes_size=len(decoded_text.encode("utf-8")),
            retrieved_at=datetime.now(timezone.utc),
        )

    def get_case(self, case_id: str) -> Dict[str, Any]:
        """Fetches raw case metadata by case ID."""
        case_id_clean = case_id.split("/")[-1]
        path = f"/v1alpha/projects/{self.project_id}/locations/{self.location}/instances/{self.customer_id}/cases/{case_id_clean}"
        res = self._request("GET", path)
        if not isinstance(res, dict) or "name" not in res:
            raise RuntimeError(f"Case '{case_id}' not found or invalid response from SecOps.")
        return res

    def list_case_alerts(self, case_id: str) -> List[Dict[str, Any]]:
        """Lists all alerts associated with a specific case."""
        case_id_clean = case_id.split("/")[-1]
        path = f"/v1alpha/projects/{self.project_id}/locations/{self.location}/instances/{self.customer_id}/cases/{case_id_clean}/caseAlerts"
        res = self._request("GET", path)
        if isinstance(res, dict):
            return res.get("caseAlerts", [])
        return []

    def get_case_alert(self, alert_name: str) -> Dict[str, Any]:
        """Fetches specific alert details by resource name."""
        clean_name = alert_name.lstrip("/")
        if not clean_name.startswith("projects/"):
            clean_name = f"projects/{self.project_id}/locations/{self.location}/instances/{self.customer_id}/{clean_name}"
        path = f"/v1alpha/{clean_name}"
        res = self._request("GET", path)
        if not isinstance(res, dict) or "name" not in res:
            raise RuntimeError(f"Case Alert '{alert_name}' not found.")
        return res

    def list_alert_entities(self, alert_name: str) -> List[Dict[str, Any]]:
        """Lists all involved entities for a specific alert."""
        clean_name = alert_name.lstrip("/")
        if not clean_name.startswith("projects/"):
            clean_name = f"projects/{self.project_id}/locations/{self.location}/instances/{self.customer_id}/{clean_name}"
        path = f"/v1alpha/{clean_name}/involvedEntities"
        res = self._request("GET", path)
        if isinstance(res, dict):
            return res.get("involvedEntities", [])
        return []

    def list_case_comments(self, case_id: str) -> List[Dict[str, Any]]:
        """Lists all comments associated with a case."""
        case_id_clean = case_id.split("/")[-1]
        path = f"/v1alpha/projects/{self.project_id}/locations/{self.location}/instances/{self.customer_id}/cases/{case_id_clean}/caseComments"
        res = self._request("GET", path)
        if isinstance(res, dict):
            return res.get("caseComments", [])
        return []

    def create_case_comment(self, case_id: str, comment: str) -> Dict[str, Any]:
        """Posts a new comment to a case and returns the confirmed comment record."""
        if not comment or not comment.strip():
            raise ValueError("Comment text cannot be empty.")
        case_id_clean = case_id.split("/")[-1]
        path = f"/v1alpha/projects/{self.project_id}/locations/{self.location}/instances/{self.customer_id}/cases/{case_id_clean}/caseComments"
        body = {"comment": comment.strip()}
        res = self._request("POST", path, body=body)
        if not isinstance(res, dict) or "name" not in res:
            raise RuntimeError(f"Failed to post comment to case {case_id}: invalid provider response.")
        return res

    def search_cases(
        self,
        query_text: str = "",
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        tags: Optional[List[str]] = None,
        priorities: Optional[List[str]] = None,
        stages: Optional[List[str]] = None,
        environments: Optional[List[str]] = None,
        assigned_users: Optional[List[str]] = None,
        is_important: Optional[bool] = None,
        page_size: int = 50,
        page_number: int = 0,
    ) -> Dict[str, Any]:
        """Executes free-form and multi-facet search across SOAR cases."""
        now = datetime.now(timezone.utc)
        if end_time is None:
            end_time = now
        if start_time is None:
            start_time = end_time - timedelta(days=30)

        start_str = start_time.strftime("%Y-%m-%dT%H:%M:%S.000Z")
        end_str = end_time.strftime("%Y-%m-%dT%H:%M:%S.999Z")

        payload: Dict[str, Any] = {
            "startTime": start_str,
            "endTime": end_str,
            "title": query_text or "",
            "tags": tags or [],
            "ruleGenerator": [],
            "caseSource": [],
            "stage": stages or [],
            "environments": environments or [],
            "assignedUsers": assigned_users or [],
            "products": [],
            "ports": [],
            "categoryOutcomes": [],
            "importance": [is_important] if is_important is not None else [],
            "priorities": priorities or [],
            "incident": [],
            "timeRangeFilter": "CUSTOM",
            "paging": {"pageSize": page_size, "requestedPage": page_number},
            "pageSize": page_size,
            "requestedPage": page_number,
        }

        path = f"/v1alpha/projects/{self.project_id}/locations/{self.location}/instances/{self.customer_id}/legacySearches:legacyCaseSearchEverything"
        res = self._request("POST", path, body=payload)
        if not isinstance(res, dict):
            return {"results": [], "totalCount": 0, "pageSize": page_size}
        return res

    def get_case_filter_values(
        self,
        filter_type: str,
        search_term: str = "",
        limit: int = 20,
    ) -> List[str]:
        """Retrieves facet filter suggestions for cases (ENVIRONMENTS, TAGS, etc.)."""
        payload = {
            "typeOfFilter": filter_type,
            "numberOfValuesToReturn": limit,
            "searchTerm": search_term,
        }
        path = f"/v1alpha/projects/{self.project_id}/locations/{self.location}/instances/{self.customer_id}/legacySearches:legacyGetCasesFilterValues"
        res = self._request("POST", path, body=payload)
        if isinstance(res, dict) and "payload" in res and isinstance(res["payload"], list):
            return res["payload"]
        return []

    def get_playbook_menu_cards(
        self,
        playbook_types: Optional[List[str]] = None,
    ) -> List[Dict[str, Any]]:
        """Lists playbook summary cards with environment/type filter."""
        types = playbook_types or ["NESTED", "REGULAR"]
        path = f"/v1alpha/projects/{self.project_number}/locations/{self.location}/instances/{self.customer_id}/legacyPlaybooks:legacyGetWorkflowMenuCardsWithEnvFilter"
        res = self._request("POST", path, body={"legacyPayload": types})
        if isinstance(res, dict) and "payload" in res and isinstance(res["payload"], list):
            return res["payload"]
        elif isinstance(res, list):
            return res
        return []

    def get_playbook_categories(self) -> List[Dict[str, Any]]:
        """Lists all SOAR Playbook categories/folders."""
        path = f"/v1alpha/projects/{self.project_number}/locations/{self.location}/instances/{self.customer_id}/legacyPlaybooks:legacyGetWorkflowCategories"
        res = self._request("GET", path)
        if isinstance(res, dict) and "payload" in res and isinstance(res["payload"], list):
            return res["payload"]
        elif isinstance(res, list):
            return res
        return []

    def get_playbook_full_info(self, workflow_identifier: str) -> Dict[str, Any]:
        """Fetches complete playbook definition by UUID identifier."""
        path = f"/v1alpha/projects/{self.project_number}/locations/{self.location}/instances/{self.customer_id}/legacyPlaybooks:legacyGetWorkflowFullInfoWithEnvFilterByIdentifier"
        res = self._request("GET", path, params={"workflowIdentifier": workflow_identifier})
        if isinstance(res, dict) and "payload" in res and isinstance(res["payload"], dict):
            return res["payload"]
        elif isinstance(res, dict):
            return res
        return {}

    def get_playbook_stats(self, original_workflow_identifier: str) -> Dict[str, Any]:
        """Fetches execution statistics for a playbook workflow."""
        path = f"/v1alpha/projects/{self.project_number}/locations/{self.location}/instances/{self.customer_id}/legacyPlaybooks:legacyGetPlaybookStatsMap"
        res = self._request("POST", path, body={"originalWorkflowIdentifier": original_workflow_identifier})
        if isinstance(res, dict) and "payload" in res and isinstance(res["payload"], dict):
            return res["payload"]
        elif isinstance(res, dict):
            return res
        return {}

    # =========================================================================
    # Milestone 5.4: SOAR Integrations, Instances & Remote Agents API Methods
    # =========================================================================

    def list_integrations(
        self,
        filter_expr: Optional[str] = None,
        page_size: int = 1000,
    ) -> List[Dict[str, Any]]:
        """Lists SOAR base integration catalog items."""
        path = f"/v1alpha/projects/{self.project_number}/locations/{self.location}/instances/{self.customer_id}/integrations"
        params: Dict[str, Any] = {"pageSize": page_size}
        if filter_expr:
            params["filter"] = filter_expr
        res = self._request("GET", path, params=params)
        if isinstance(res, dict) and "integrations" in res and isinstance(res["integrations"], list):
            return res["integrations"]
        elif isinstance(res, list):
            return res
        return []

    def list_integration_instances(
        self,
        integration_id: Optional[str] = None,
        environment: Optional[str] = None,
        page_size: int = 1000,
    ) -> List[Dict[str, Any]]:
        """Lists configured integration instances across environments or for a specific integration."""
        if integration_id:
            path = f"/v1alpha/projects/{self.project_number}/locations/{self.location}/instances/{self.customer_id}/integrations/{integration_id}/integrationInstances"
        else:
            path = f"/v1alpha/projects/{self.project_number}/locations/{self.location}/instances/{self.customer_id}/integrations/-/integrationInstances"
        params: Dict[str, Any] = {"pageSize": page_size}
        if environment:
            params["filter"] = f"environment = '{environment}'"
        res = self._request("GET", path, params=params)
        if isinstance(res, dict) and "integrationInstances" in res and isinstance(res["integrationInstances"], list):
            return res["integrationInstances"]
        elif isinstance(res, list):
            return res
        return []

    def get_integration_instance(
        self,
        integration_id: str,
        instance_id: str,
    ) -> Dict[str, Any]:
        """Retrieves a specific configured integration instance."""
        path = f"/v1alpha/projects/{self.project_number}/locations/{self.location}/instances/{self.customer_id}/integrations/{integration_id}/integrationInstances/{instance_id}"
        res = self._request("GET", path)
        if isinstance(res, dict):
            return res
        return {}

    def list_remote_agents(
        self,
        state_filter: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Lists remote proxy execution agents."""
        path = f"/v1alpha/projects/{self.project_number}/locations/{self.location}/instances/{self.customer_id}/remoteAgents"
        params: Dict[str, Any] = {"pageSize": 100}
        if state_filter:
            params["filter"] = f'agentState = "{state_filter}"'
        res = self._request("GET", path, params=params)
        if isinstance(res, dict) and "remoteAgents" in res and isinstance(res["remoteAgents"], list):
            return res["remoteAgents"]
        elif isinstance(res, list):
            return res
        return []

    def get_marketplace_integration(
        self,
        identifier: str,
    ) -> Optional[Dict[str, Any]]:
        """Retrieves marketplace metadata and documentation for an integration."""
        path = f"/v1alpha/projects/{self.project_number}/locations/{self.location}/instances/{self.customer_id}/marketplaceIntegrations"
        params = {
            "filter": f"identifier = '{identifier}'",
            "pageSize": 50,
        }
        res = self._request("GET", path, params=params)
        if isinstance(res, dict) and "marketplaceIntegrations" in res:
            mp_list = res.get("marketplaceIntegrations", [])
            if mp_list and isinstance(mp_list, list):
                return mp_list[0]
        return None

    # =========================================================================
    # Milestone 5.5: SOAR Scheduled Jobs, Instances & Execution Logs
    # =========================================================================

    def list_jobs(
        self,
        integration: Optional[str] = None,
        enabled: Optional[bool] = None,
        exclude_staging: bool = True,
        page_size: int = 1000,
    ) -> List[Dict[str, Any]]:
        """Lists SOAR scheduled job definitions."""
        int_segment = integration or "-"
        path = f"/v1alpha/projects/{self.project_number}/locations/{self.location}/instances/{self.customer_id}/integrations/{int_segment}/jobs"
        params: Dict[str, Any] = {
            "excludeStaging": str(exclude_staging).lower(),
            "pageSize": page_size,
        }
        if enabled is not None:
            params["filter"] = f"enabled = {str(enabled).lower()}"
        res = self._request("GET", path, params=params)
        if isinstance(res, dict) and "jobs" in res and isinstance(res["jobs"], list):
            return res["jobs"]
        elif isinstance(res, list):
            return res
        return []

    def get_job(
        self,
        integration: str,
        job_id: str,
    ) -> Dict[str, Any]:
        """Retrieves a specific SOAR job definition."""
        path = f"/v1alpha/projects/{self.project_number}/locations/{self.location}/instances/{self.customer_id}/integrations/{integration}/jobs/{job_id}"
        res = self._request("GET", path)
        if isinstance(res, dict):
            return res
        return {}

    def list_job_instances(
        self,
        integration: Optional[str] = None,
        job_id: Optional[str] = None,
        page_size: int = 1000,
    ) -> List[Dict[str, Any]]:
        """Lists runtime job instances across environments."""
        int_segment = integration or "-"
        job_segment = job_id or "-"
        path = f"/v1alpha/projects/{self.project_number}/locations/{self.location}/instances/{self.customer_id}/integrations/{int_segment}/jobs/{job_segment}/jobInstances"
        params: Dict[str, Any] = {"pageSize": page_size}
        res = self._request("GET", path, params=params)
        if isinstance(res, dict) and "jobInstances" in res and isinstance(res["jobInstances"], list):
            return res["jobInstances"]
        elif isinstance(res, list):
            return res
        return []

    def get_job_instance(
        self,
        integration: str,
        job_id: str,
        instance_id: str,
    ) -> Dict[str, Any]:
        """Retrieves a specific runtime job instance."""
        path = f"/v1alpha/projects/{self.project_number}/locations/{self.location}/instances/{self.customer_id}/integrations/{integration}/jobs/{job_id}/jobInstances/{instance_id}"
        res = self._request("GET", path)
        if isinstance(res, dict):
            return res
        return {}

    def get_job_instance_logs(
        self,
        instance_id: str,
        page_size: int = 20,
        order_by: str = "endTime desc",
    ) -> Dict[str, Any]:
        """Retrieves execution logs for a specific job instance."""
        path = f"/v1alpha/projects/{self.project_number}/locations/{self.location}/instances/{self.customer_id}/integrations/-/jobs/-/jobInstances/{instance_id}/logs"
        params: Dict[str, Any] = {
            "pageSize": page_size,
            "orderBy": order_by,
        }
        res = self._request("GET", path, params=params)
        if isinstance(res, dict):
            return res
        return {"logs": [], "totalSize": 0}

    # ==========================================================================
    # Milestone 5.6: Content Hub (Marketplace) - Content Packs Methods
    # ==========================================================================

    def list_content_packs(
        self,
        query_filter: Optional[str] = None,
        page_size: int = 100,
        expand: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Lists Content Packs from Content Hub Marketplace with optional expands and filter."""
        path = f"/v1alpha/projects/{self.project_number}/locations/{self.location}/instances/{self.customer_id}/contentHub/contentPacks"
        params: Dict[str, Any] = {
            "pageSize": page_size,
            "expand": expand or "playbooks,testCases,connectorInstances,connectorDefinitions,integrations,detectionRules,searchQueries,dashboards,ruleSets",
        }
        if query_filter:
            params["filter"] = query_filter
        res = self._request("GET", path, params=params)
        if isinstance(res, dict):
            return res
        return {"contentPacks": [], "totalSize": 0}

    def get_content_pack(
        self,
        pack_id: str,
        expand: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Retrieves a specific Content Pack from Content Hub by identifier or resource name."""
        # Strip resource name prefix if passed
        clean_id = pack_id.split("/")[-1]
        path = f"/v1alpha/projects/{self.project_number}/locations/{self.location}/instances/{self.customer_id}/contentHub/contentPacks/{clean_id}"
        params: Dict[str, Any] = {
            "expand": expand or "playbooks,testCases,connectorInstances,connectorDefinitions,integrations,detectionRules,searchQueries,dashboards,ruleSets",
        }
        res = self._request("GET", path, params=params)
        if isinstance(res, dict):
            return res
        return {}

    # --- Milestone 5.7: Curated Detections Methods ---

    def list_curated_ruleset_categories(self) -> Dict[str, Any]:
        """Lists all Curated Rule Set categories."""
        path = f"/v1alpha/projects/{self.project_number}/locations/{self.location}/instances/{self.customer_id}/curatedRuleSetCategories"
        res = self._request("GET", path)
        if isinstance(res, dict):
            return res
        return {"curatedRuleSetCategories": []}

    def list_curated_rulesets(
        self,
        category_id: Optional[str] = None,
        page_size: int = 1000,
    ) -> Dict[str, Any]:
        """Lists Curated Rule Sets across all categories or within a specific category."""
        cat_token = category_id.split("/")[-1] if category_id else "-"
        path = f"/v1alpha/projects/{self.project_number}/locations/{self.location}/instances/{self.customer_id}/curatedRuleSetCategories/{cat_token}/curatedRuleSets"
        params = {"pageSize": page_size}
        res = self._request("GET", path, params=params)
        if isinstance(res, dict):
            return res
        return {"curatedRuleSets": []}

    def get_curated_ruleset_deployments(self, curated_ruleset_name: str) -> Dict[str, Any]:
        """Retrieves deployment states (broad/precise, enabled, alerting) for a Curated Rule Set."""
        clean_name = curated_ruleset_name.strip()
        if not clean_name.startswith("projects/"):
            # If a simple ID was given, we cannot reliably reconstruct full path without category
            raise ValueError(f"Full resource name required for deployment status: '{curated_ruleset_name}'")
        path = f"/v1alpha/{clean_name}/curatedRuleSetDeployments"
        res = self._request("GET", path)
        if isinstance(res, dict):
            return res
        return {"curatedRuleSetDeployments": []}

    def list_curated_rules(self, page_size: int = 1000) -> Dict[str, Any]:
        """Lists all Google-curated individual rules."""
        path = f"/v1alpha/projects/{self.project_number}/locations/{self.location}/instances/{self.customer_id}/curatedRules"
        params = {"pageSize": page_size}
        res = self._request("GET", path, params=params)
        if isinstance(res, dict):
            return res
        return {"curatedRules": []}

    def get_featured_content_rule(self, rule_id: str) -> Dict[str, Any]:
        """Retrieves a Curated Rule and its executable YARA-L logic from Content Hub."""
        clean_id = rule_id.split("/")[-1]
        path = f"/v1alpha/projects/{self.project_number}/locations/{self.location}/instances/{self.customer_id}/contentHub/featuredContentRules"
        params = {"filter": f'rule_id:"{clean_id}"'}
        res = self._request("GET", path, params=params)
        if isinstance(res, dict) and res.get("featuredContentRules"):
            return res["featuredContentRules"][0]
        return {}

    def count_curated_ruleset_detections(
        self,
        start_time: str,
        end_time: str,
    ) -> Dict[str, Any]:
        """Aggregates detection firing counts for each curated rule set over a time window."""
        path = f"/v1alpha/projects/{self.project_number}/locations/{self.location}/instances/{self.customer_id}:countAllCuratedRuleSetDetections"
        body = {
            "interval": {
                "startTime": start_time,
                "endTime": end_time,
            }
        }
        res = self._request("POST", path, body=body)
        if isinstance(res, dict):
            return res
        return {"curatedRuleSetCounts": []}

    def get_tenant_rule_metrics(self) -> Dict[str, Any]:
        """Retrieves tenant-wide rule counts and chronicle rules quota usage."""
        path = f"/v1alpha/projects/{self.project_number}/locations/{self.location}/instances/{self.customer_id}/legacy:legacyGetRuleCounts"
        res = self._request("GET", path)
        if isinstance(res, dict):
            return res
        return {}

    # --- Milestone 5.8: Content Hub Marketplace Response Integrations Methods ---

    def list_marketplace_integrations(
        self,
        query_filter: Optional[str] = "powerUp = false",
        order_by: Optional[str] = "identifier asc",
        page_size: int = 1000,
    ) -> Dict[str, Any]:
        """Lists Response Integrations from the Content Hub Marketplace."""
        path = f"/v1alpha/projects/{self.project_number}/locations/{self.location}/instances/{self.customer_id}/marketplaceIntegrations"
        params: Dict[str, Any] = {
            "pageSize": page_size,
        }
        if query_filter:
            params["filter"] = query_filter
        if order_by:
            params["orderBy"] = order_by
        res = self._request("GET", path, params=params)
        if isinstance(res, dict):
            return res
        return {"marketplaceIntegrations": [], "totalSize": 0}

    def get_marketplace_integration(self, identifier: str) -> Dict[str, Any]:
        """Retrieves full details for a Marketplace Response Integration."""
        clean_id = identifier.split("/")[-1]
        path = f"/v1alpha/projects/{self.project_number}/locations/{self.location}/instances/{self.customer_id}/marketplaceIntegrations/{clean_id}"
        res = self._request("GET", path)
        if isinstance(res, dict):
            return res
        return {}

    def get_marketplace_integration_diff(self, identifier: str) -> Dict[str, Any]:
        """Retrieves commercial version diff comparing installed vs latest marketplace version."""
        clean_id = identifier.split("/")[-1]
        path = f"/v1alpha/projects/{self.project_number}/locations/{self.location}/instances/{self.customer_id}/marketplaceIntegrations/{clean_id}:fetchCommercialDiff"
        res = self._request("GET", path)
        if isinstance(res, dict):
            return res
        return {}

    def get_integration_affected_items(self, identifier: str) -> Dict[str, Any]:
        """Retrieves downstream environment instances and playbooks affected by an integration."""
        clean_id = identifier.split("/")[-1]
        path = f"/v1alpha/projects/{self.project_number}/locations/{self.location}/instances/{self.customer_id}/integrations/{clean_id}:fetchAffectedItems"
        res = self._request("GET", path)
        if isinstance(res, dict):
            return res
        return {}

    # ==========================================
    # Milestone 5.9: Native Dashboards Adapters
    # ==========================================

    def list_native_dashboards(
        self,
        page_size: int = 1000,
        page_token: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Lists native dashboards configured in Google SecOps."""
        path = f"/v1alpha/projects/{self.project_number}/locations/{self.location}/instances/{self.customer_id}/nativeDashboards"
        params: Dict[str, Any] = {"pageSize": page_size}
        if page_token:
            params["pageToken"] = page_token
        res = self._request("GET", path, params=params)
        if isinstance(res, dict):
            return res
        return {"nativeDashboards": []}

    def get_native_dashboard(self, dashboard_id: str) -> Dict[str, Any]:
        """Retrieves complete definition of a native dashboard."""
        clean_id = dashboard_id.split("/")[-1]
        path = f"/v1alpha/projects/{self.project_number}/locations/{self.location}/instances/{self.customer_id}/nativeDashboards/{clean_id}"
        res = self._request("GET", path)
        if isinstance(res, dict):
            return res
        return {}

    def batch_get_dashboard_charts(self, chart_names: List[str]) -> Dict[str, Any]:
        """Retrieves multiple dashboard charts in a single batch request."""
        if not chart_names:
            return {"dashboardCharts": []}
        path = f"/v1alpha/projects/{self.project_number}/locations/{self.location}/instances/{self.customer_id}/dashboardCharts:batchGet"
        params = [("names", name) for name in chart_names]
        res = self._request("GET", path, params=params)
        if isinstance(res, dict):
            return res
        return {"dashboardCharts": []}

    def get_dashboard_query(self, query_id: str) -> Dict[str, Any]:
        """Retrieves definition of a dashboard query."""
        clean_id = query_id.split("/")[-1]
        path = f"/v1alpha/projects/{self.project_number}/locations/{self.location}/instances/{self.customer_id}/dashboardQueries/{clean_id}"
        res = self._request("GET", path)
        if isinstance(res, dict):
            return res
        return {}

    def execute_dashboard_query(
        self,
        query_name: str,
        filters: Optional[List[Dict[str, Any]]] = None,
        use_previous_time_range: bool = False,
        query_source: str = "DASHBOARD",
    ) -> Dict[str, Any]:
        """Executes a dashboard query against live SecOps telemetry."""
        full_query_name = query_name
        if not query_name.startswith("projects/"):
            clean_id = query_name.split("/")[-1]
            full_query_name = f"projects/{self.project_number}/locations/{self.location}/instances/{self.customer_id}/dashboardQueries/{clean_id}"

        path = f"/v1alpha/projects/{self.project_number}/locations/{self.location}/instances/{self.customer_id}/dashboardQueries:execute"
        body = {
            "query": {"name": full_query_name},
            "filters": filters or [],
            "usePreviousTimeRange": use_previous_time_range,
            "querySource": query_source,
        }
        res = self._request("POST", path, body=body)
        if isinstance(res, dict):
            return res
        return {}

    def validate_stats_query(
        self,
        raw_query: str,
        dialect: str = "DIALECT_STATS",
    ) -> ValidationResult:
        """Validates statistical or widget query syntax."""
        path = f"/v1alpha/projects/{self.project_number}/locations/{self.location}/instances/{self.customer_id}:validateQuery"
        params = {
            "dialect": dialect,
            "allowUnreplacedPlaceholders": "false",
            "rawQuery": raw_query,
        }
        try:
            res = self._request("GET", path, params=params)
            query_type = res.get("queryType")
            err_text = res.get("errorText") or res.get("errorType")
            is_valid = (query_type in ["QUERY_TYPE_STATS_QUERY", "QUERY_TYPE_UDM_QUERY"]) and not err_text
            return ValidationResult(
                valid=is_valid,
                dialect=dialect,
                raw_query_type=query_type,
                error_message=err_text if not is_valid else None,
            )
        except Exception as e:
            return ValidationResult(
                valid=False,
                dialect=dialect,
                error_message=str(e),
            )

    # -------------------------------------------------------------------------
    # Milestone 5.10: SIEM Settings, Feeds, Pipelines & Feed Schemas Methods
    # -------------------------------------------------------------------------

    def get_managed_domain_settings(self) -> Dict[str, Any]:
        """Retrieves approved email domains for report deliveries and alerts."""
        path = f"/v1alpha/projects/{self.project_number}/locations/{self.location}/instances/{self.customer_id}/managedDomainSettings"
        return self._request("GET", path)

    def list_feeds(
        self,
        page_size: int = 1000,
        page_token: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Lists push and pull log ingestion feeds."""
        path = f"/v1alpha/projects/{self.project_number}/locations/{self.location}/instances/{self.customer_id}/feeds"
        params: Dict[str, Any] = {"pageSize": page_size}
        if page_token:
            params["pageToken"] = page_token
        return self._request("GET", path, params=params)

    def get_feed(self, feed_id: str) -> Dict[str, Any]:
        """Retrieves full configuration details for a specific ingestion feed."""
        clean_id = feed_id.split("/")[-1]
        path = f"/v1alpha/projects/{self.project_number}/locations/{self.location}/instances/{self.customer_id}/feeds/{clean_id}"
        return self._request("GET", path)

    def list_log_processing_pipelines(
        self,
        page_size: int = 1000,
        page_token: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Lists Data Processing Pipelines."""
        path = f"/v1alpha/projects/{self.project_number}/locations/{self.location}/instances/{self.customer_id}/logProcessingPipelines"
        params: Dict[str, Any] = {"pageSize": page_size}
        if page_token:
            params["pageToken"] = page_token
        return self._request("GET", path, params=params)

    def get_log_processing_pipeline(self, pipeline_id: str) -> Dict[str, Any]:
        """Retrieves full configuration and transforms for a Data Processing Pipeline."""
        clean_id = pipeline_id.split("/")[-1]
        path = f"/v1alpha/projects/{self.project_number}/locations/{self.location}/instances/{self.customer_id}/logProcessingPipelines/{clean_id}"
        return self._request("GET", path)

    def list_feed_source_type_schemas(
        self,
        page_size: int = 1000,
    ) -> Dict[str, Any]:
        """Lists all supported feed source types and metadata."""
        path = f"/v1alpha/projects/{self.project_number}/locations/{self.location}/instances/{self.customer_id}/feedSourceTypeSchemas"
        params = {"pageSize": page_size}
        return self._request("GET", path, params=params)

    def list_feed_log_type_schemas(
        self,
        feed_source_type: str,
        page_size: int = 100,
        page_token: Optional[str] = None,
        omit_details_fields: bool = True,
    ) -> Dict[str, Any]:
        """Lists log type schemas for a feed source type, with lean payload handling."""
        clean_source = feed_source_type.split("/")[-1]
        path = f"/v1alpha/projects/{self.project_number}/locations/{self.location}/instances/{self.customer_id}/feedSourceTypeSchemas/{clean_source}/logTypeSchemas"
        params: Dict[str, Any] = {"pageSize": page_size}
        if page_token:
            params["pageToken"] = page_token
        res = self._request("GET", path, params=params)
        if omit_details_fields and "logTypeSchemas" in res:
            for item in res["logTypeSchemas"]:
                if "detailsFieldSchemas" in item:
                    item["detailsFieldSchemasCount"] = len(item["detailsFieldSchemas"])
                    del item["detailsFieldSchemas"]
        return res

    # --------------------------------------------------------------------------
    # Milestone 5.11: SIEM Settings - Parsers, Log Types, Extensions & Settings
    # --------------------------------------------------------------------------

    def list_log_types(
        self,
        page_size: int = 1000,
        page_token: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Lists supported ingestion log types cataloged in Google SecOps."""
        path = f"/v1alpha/projects/{self.project_number}/locations/{self.location}/instances/{self.customer_id}/logTypes"
        params: Dict[str, Any] = {"pageSize": page_size}
        if page_token:
            params["pageToken"] = page_token
        return self._request("GET", path, params=params)

    def list_parsers(
        self,
        log_type: str = "-",
        view: str = "BASIC_VIEW",
        page_size: int = 1000,
        filter_expr: str = "",
        page_token: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Lists parsers across all log types or for a specific log type."""
        clean_lt = log_type.split("/")[-1] if log_type != "-" else "-"
        path = f"/v1alpha/projects/{self.project_number}/locations/{self.location}/instances/{self.customer_id}/logTypes/{clean_lt}/parsers"
        params: Dict[str, Any] = {
            "pageSize": page_size,
            "view": view,
        }
        if filter_expr:
            params["filter"] = filter_expr
        if page_token:
            params["pageToken"] = page_token
        return self._request("GET", path, params=params)

    def get_parser(
        self,
        log_type: str,
        parser_id: str,
        view: str = "FULL_VIEW",
    ) -> Dict[str, Any]:
        """Retrieves a single parser with full CBN configuration."""
        clean_lt = log_type.split("/")[-1]
        clean_id = parser_id.split("/")[-1]
        # First attempt direct GET if parser resource endpoint is available
        path = f"/v1alpha/projects/{self.project_number}/locations/{self.location}/instances/{self.customer_id}/logTypes/{clean_lt}/parsers/{clean_id}"
        try:
            return self._request("GET", path, params={"view": view})
        except Exception:
            # Fallback to list with FULL_VIEW and matching ID
            res = self.list_parsers(log_type=clean_lt, view=view, page_size=1000)
            for p in res.get("parsers", []):
                p_name = p.get("name", "")
                if p_name.endswith(clean_id) or p_name.split("/")[-1] == clean_id:
                    return p
            raise ValueError(f"Parser '{clean_id}' not found for log type '{clean_lt}'")

    def list_parser_extensions(
        self,
        log_type: str = "-",
        page_size: int = 1000,
        page_token: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Lists parser extensions across all log types or for a specific log type."""
        clean_lt = log_type.split("/")[-1] if log_type != "-" else "-"
        path = f"/v1alpha/projects/{self.project_number}/locations/{self.location}/instances/{self.customer_id}/logTypes/{clean_lt}/parserExtensions"
        params: Dict[str, Any] = {"pageSize": page_size}
        if page_token:
            params["pageToken"] = page_token
        return self._request("GET", path, params=params)

    def get_parser_extension(
        self,
        log_type: str,
        extension_id: str,
    ) -> Dict[str, Any]:
        """Retrieves detailed configuration for a parser extension."""
        clean_lt = log_type.split("/")[-1]
        clean_id = extension_id.split("/")[-1]
        # Query extensions for the specific log type and locate matching extension
        res = self.list_parser_extensions(log_type=clean_lt, page_size=1000)
        for ext in res.get("parserExtensions", []):
            ext_name = ext.get("name", "")
            if ext_name.endswith(clean_id) or ext_name.split("/")[-1] == clean_id:
                return ext
        raise ValueError(f"Parser extension '{clean_id}' not found for log type '{clean_lt}'")

    def get_log_type_setting(
        self,
        log_type: str,
    ) -> Dict[str, Any]:
        """Retrieves autonomous parsing extraction settings for a specific log type."""
        clean_lt = log_type.split("/")[-1]
        path = f"/v1alpha/projects/{self.project_number}/locations/{self.location}/instances/{self.customer_id}/logTypes/{clean_lt}/logTypeSetting"
        return self._request("GET", path)

    # --------------------------------------------------------------------------
    # Milestone 5.12: SIEM Settings - Preview Features & Data RBAC
    # --------------------------------------------------------------------------

    def list_preview_features(
        self,
        page_size: int = 1000,
        page_token: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Lists tenant preview features and enablement states."""
        path = f"/v1alpha/projects/{self.project_number}/locations/{self.location}/instances/{self.customer_id}/features"
        params: Dict[str, Any] = {"pageSize": page_size}
        if page_token:
            params["pageToken"] = page_token
        return self._request("GET", path, params=params)

    def get_preview_feature(self, feature_id: str) -> Dict[str, Any]:
        """Retrieves specific preview feature configuration."""
        clean_id = feature_id.split("/")[-1]
        path = f"/v1alpha/projects/{self.project_number}/locations/{self.location}/instances/{self.customer_id}/features/{clean_id}"
        return self._request("GET", path)

    def list_data_access_scopes(
        self,
        page_size: int = 1000,
        page_token: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Lists tenant Data Access Scopes (Data RBAC)."""
        path = f"/v1alpha/projects/{self.project_number}/locations/{self.location}/instances/{self.customer_id}/dataAccessScopes"
        params: Dict[str, Any] = {"pageSize": page_size}
        if page_token:
            params["pageToken"] = page_token
        return self._request("GET", path, params=params)

    def get_data_access_scope(self, scope_id: str) -> Dict[str, Any]:
        """Retrieves specific Data Access Scope deep configuration."""
        clean_id = scope_id.split("/")[-1]
        path = f"/v1alpha/projects/{self.project_number}/locations/{self.location}/instances/{self.customer_id}/dataAccessScopes/{clean_id}"
        return self._request("GET", path)

    def list_data_access_labels(
        self,
        page_size: int = 1000,
        page_token: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Lists tenant Data Access Labels (UDM query expressions)."""
        path = f"/v1alpha/projects/{self.project_number}/locations/{self.location}/instances/{self.customer_id}/dataAccessLabels"
        params: Dict[str, Any] = {"pageSize": page_size}
        if page_token:
            params["pageToken"] = page_token
        return self._request("GET", path, params=params)

    def get_data_access_label(self, label_id: str) -> Dict[str, Any]:
        """Retrieves specific Data Access Label deep configuration."""
        clean_id = label_id.split("/")[-1]
        path = f"/v1alpha/projects/{self.project_number}/locations/{self.location}/instances/{self.customer_id}/dataAccessLabels/{clean_id}"
        return self._request("GET", path)

    def list_soar_environments(
        self,
        fields: Optional[str] = None,
        page_size: int = 1000,
        page_token: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Lists SOAR environments and attached Data Access Scopes."""
        path = f"/v1alpha/projects/{self.project_number}/locations/{self.location}/instances/{self.customer_id}/environments"
        params: Dict[str, Any] = {"pageSize": page_size}
        if fields:
            params["fields"] = fields
        if page_token:
            params["pageToken"] = page_token
        return self._request("GET", path, params=params)

    # -------------------------------------------------------------------------
    # Milestone 5.13: Remaining SIEM Settings & Enrichment Controls
    # -------------------------------------------------------------------------

    def get_enrichment_combination(self) -> Dict[str, Any]:
        """Retrieves available entity enrichment combinations."""
        path = f"/v1alpha/projects/{self.project_number}/locations/{self.location}/instances/{self.customer_id}/enrichmentCombination"
        return self._request("GET", path)

    def list_enrichment_controls(
        self,
        page_size: int = 1000,
        page_token: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Lists deployed enrichment controls."""
        path = f"/v1alpha/projects/{self.project_number}/locations/{self.location}/instances/{self.customer_id}/enrichmentControls"
        params: Dict[str, Any] = {"pageSize": page_size}
        if page_token:
            params["pageToken"] = page_token
        return self._request("GET", path, params=params)

    def get_enrichment_control(self, control_id: str) -> Dict[str, Any]:
        """Retrieves specific deployed enrichment control configuration."""
        clean_id = control_id.split("/")[-1]
        path = f"/v1alpha/projects/{self.project_number}/locations/{self.location}/instances/{self.customer_id}/enrichmentControls/{clean_id}"
        return self._request("GET", path)

    def get_agent_settings(self) -> Dict[str, Any]:
        """Retrieves Gemini Triage & Investigation Agent settings."""
        path = f"/v1alpha/projects/{self.project_number}/locations/{self.location}/instances/{self.customer_id}/agentSettings"
        return self._request("GET", path)

    def get_risk_config(self) -> Dict[str, Any]:
        """Retrieves UEBA entity risk scoring configuration."""
        path = f"/v1alpha/projects/{self.project_number}/locations/{self.location}/instances/{self.customer_id}/riskConfig"
        return self._request("GET", path)

    def get_tenant_instance(self) -> Dict[str, Any]:
        """Retrieves root tenant instance details and configuration."""
        path = f"/v1alpha/projects/{self.project_number}/locations/{self.location}/instances/{self.customer_id}"
        return self._request("GET", path)

    # --- Milestone 6.1: SOAR Settings & Case Data Configuration ---

    def list_soar_users(
        self,
        page_size: int = 1000,
        page_token: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Lists SOAR users and external identity representations."""
        path = f"/v1alpha/projects/{self.project_number}/locations/{self.location}/instances/{self.customer_id}/legacySoarUsers"
        params: Dict[str, Any] = {"pageSize": page_size}
        if page_token:
            params["pageToken"] = page_token
        return self._request("GET", path, params=params)

    def get_soar_user(self, user_id: str) -> Dict[str, Any]:
        """Retrieves specific SOAR user details."""
        clean_id = user_id.split("/")[-1]
        path = f"/v1alpha/projects/{self.project_number}/locations/{self.location}/instances/{self.customer_id}/legacySoarUsers/{clean_id}"
        return self._request("GET", path)

    def list_soc_roles(
        self,
        page_size: int = 1000,
        page_token: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Lists SOC roles and workflow assignment hierarchies."""
        path = f"/v1alpha/projects/{self.project_number}/locations/{self.location}/instances/{self.customer_id}/socRoles"
        params: Dict[str, Any] = {"pageSize": page_size}
        if page_token:
            params["pageToken"] = page_token
        return self._request("GET", path, params=params)

    def get_company_settings(self) -> Dict[str, Any]:
        """Retrieves company / rebranding settings properties."""
        path = f"/v1alpha/projects/{self.project_number}/locations/{self.location}/instances/{self.customer_id}/moduleSettings/CompanySetting/properties"
        return self._request("GET", path)

    def list_case_tag_definitions(
        self,
        page_size: int = 1000,
        page_token: Optional[str] = None,
        filter_expr: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Lists case tag definitions and classification rules."""
        path = f"/v1alpha/projects/{self.project_number}/locations/{self.location}/instances/{self.customer_id}/caseTagDefinitions"
        params: Dict[str, Any] = {"pageSize": page_size}
        if page_token:
            params["pageToken"] = page_token
        if filter_expr:
            params["filter"] = filter_expr
        return self._request("GET", path, params=params)

    def list_case_stage_definitions(
        self,
        page_size: int = 1000,
        page_token: Optional[str] = None,
        order_by: str = "order",
    ) -> Dict[str, Any]:
        """Lists ordered SOC case lifecycle stage definitions."""
        path = f"/v1alpha/projects/{self.project_number}/locations/{self.location}/instances/{self.customer_id}/caseStageDefinitions"
        params: Dict[str, Any] = {"pageSize": page_size, "orderBy": order_by}
        if page_token:
            params["pageToken"] = page_token
        return self._request("GET", path, params=params)

    def list_case_close_definitions(
        self,
        page_size: int = 1000,
        page_token: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Lists predefined case close reasons and root causes."""
        path = f"/v1alpha/projects/{self.project_number}/locations/{self.location}/instances/{self.customer_id}/caseCloseDefinitions"
        params: Dict[str, Any] = {"pageSize": page_size}
        if page_token:
            params["pageToken"] = page_token
        return self._request("GET", path, params=params)

    def list_case_close_dynamic_parameters(
        self,
        page_size: int = 1000,
        page_token: Optional[str] = None,
        expand: str = "relatedCustomField",
        filter_expr: str = "formType = 'CLOSE_CASE'",
    ) -> Dict[str, Any]:
        """Lists dynamic form parameters for case close dialogs."""
        path = f"/v1alpha/projects/{self.project_number}/locations/{self.location}/instances/{self.customer_id}/formDynamicParameters"
        params: Dict[str, Any] = {"pageSize": page_size, "expand": expand, "filter": filter_expr}
        if page_token:
            params["pageToken"] = page_token
        return self._request("GET", path, params=params)

    def get_case_title_settings(self) -> Dict[str, Any]:
        """Retrieves case title naming rule properties."""
        path = f"/v1alpha/projects/{self.project_number}/locations/{self.location}/instances/{self.customer_id}/moduleSettings/CaseTitleSettings/properties"
        params: Dict[str, Any] = {"orderBy": "displayName"}
        return self._request("GET", path, params=params)

    # --- Milestone 6.2: Views, Custom Fields & Calculated Fields ---

    def list_views(
        self,
        page_size: int = 1000,
        page_token: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Lists case, alert, and detection overview layout views."""
        path = f"/v1alpha/projects/{self.project_number}/locations/{self.location}/instances/{self.customer_id}/views"
        params: Dict[str, Any] = {"pageSize": page_size}
        if page_token:
            params["pageToken"] = page_token
        return self._request("GET", path, params=params)

    def get_view(self, view_id: str) -> Dict[str, Any]:
        """Retrieves deep inspection of a specific layout view template and widgets."""
        clean_id = view_id.split("/")[-1]
        path = f"/v1alpha/projects/{self.project_number}/locations/{self.location}/instances/{self.customer_id}/views/{clean_id}"
        return self._request("GET", path)

    def list_custom_fields(
        self,
        page_size: int = 1000,
        page_token: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Lists custom typed fields across Case and Alert scopes."""
        path = f"/v1alpha/projects/{self.project_number}/locations/{self.location}/instances/{self.customer_id}/customFields"
        params: Dict[str, Any] = {"pageSize": page_size}
        if page_token:
            params["pageToken"] = page_token
        return self._request("GET", path, params=params)

    def get_custom_field(self, field_id: str) -> Dict[str, Any]:
        """Retrieves deep inspection of a single custom field definition."""
        clean_id = field_id.split("/")[-1]
        path = f"/v1alpha/projects/{self.project_number}/locations/{self.location}/instances/{self.customer_id}/customFields/{clean_id}"
        return self._request("GET", path)

    def list_calculated_fields(
        self,
        page_size: int = 1000,
        page_token: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Lists calculated field formula definitions."""
        path = f"/v1alpha/projects/{self.project_number}/locations/{self.location}/instances/{self.customer_id}/calculatedFieldDefinitions"
        params: Dict[str, Any] = {"pageSize": page_size}
        if page_token:
            params["pageToken"] = page_token
        return self._request("GET", path, params=params)

    def get_calculated_field(self, definition_id: str) -> Dict[str, Any]:
        """Retrieves deep inspection of a single calculated field definition."""
        clean_id = definition_id.split("/")[-1]
        path = f"/v1alpha/projects/{self.project_number}/locations/{self.location}/instances/{self.customer_id}/calculatedFieldDefinitions/{clean_id}"
        return self._request("GET", path)

    # --- Milestone 6.3: Alert Grouping & General SOAR Settings ---

    def list_alert_grouping_rules(
        self,
        page_size: int = 1000,
        page_token: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Lists alert grouping rules."""
        path = f"/v1alpha/projects/{self.project_number}/locations/{self.location}/instances/{self.customer_id}/alertGroupingRules"
        params: Dict[str, Any] = {"pageSize": page_size}
        if page_token:
            params["pageToken"] = page_token
        return self._request("GET", path, params=params)

    def get_alert_grouping_rule(self, rule_id: str) -> Dict[str, Any]:
        """Retrieves deep inspection of a single alert grouping rule."""
        clean_id = rule_id.split("/")[-1]
        path = f"/v1alpha/projects/{self.project_number}/locations/{self.location}/instances/{self.customer_id}/alertGroupingRules/{clean_id}"
        return self._request("GET", path)

    def get_alert_grouping_settings(self) -> Dict[str, Any]:
        """Retrieves global alert grouping module settings properties."""
        path = f"/v1alpha/projects/{self.project_number}/locations/{self.location}/instances/{self.customer_id}/moduleSettings/AlertGroupingSettings/properties"
        return self._request("GET", path)

    def get_data_retention_settings(self) -> Dict[str, Any]:
        """Retrieves SOAR data retention module settings properties."""
        path = f"/v1alpha/projects/{self.project_number}/locations/{self.location}/instances/{self.customer_id}/moduleSettings/DataRetention/properties"
        return self._request("GET", path)

    def list_environments(
        self,
        page_size: int = 1000,
        page_token: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Discovers multi-tenancy environments in the SOAR tenant."""
        path = f"/v1alpha/projects/{self.project_number}/locations/{self.location}/instances/{self.customer_id}/environments"
        params: Dict[str, Any] = {"pageSize": page_size}
        if page_token:
            params["pageToken"] = page_token
        return self._request("GET", path, params=params)

    def get_environment(self, env_id: str) -> Dict[str, Any]:
        """Retrieves deep configuration of a single multi-tenancy environment."""
        clean_id = env_id.split("/")[-1]
        path = f"/v1alpha/projects/{self.project_number}/locations/{self.location}/instances/{self.customer_id}/environments/{clean_id}"
        return self._request("GET", path)

    def list_environment_groups(
        self,
        page_size: int = 1000,
        page_token: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Discovers environment group collections."""
        path = f"/v1alpha/projects/{self.project_number}/locations/{self.location}/instances/{self.customer_id}/environmentGroups"
        params: Dict[str, Any] = {"pageSize": page_size}
        if page_token:
            params["pageToken"] = page_token
        return self._request("GET", path, params=params)

    def list_remote_agents(
        self,
        page_size: int = 1000,
        page_token: Optional[str] = None,
        filter_expr: Optional[str] = None,
        state_filter: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Discovers remote SOAR execution agents and bindings."""
        path = f"/v1alpha/projects/{self.project_number}/locations/{self.location}/instances/{self.customer_id}/remoteAgents"
        params: Dict[str, Any] = {"pageSize": page_size}
        if page_token:
            params["pageToken"] = page_token
        if filter_expr:
            params["filter"] = filter_expr
        elif state_filter:
            params["filter"] = f'agentState = "{state_filter}"'
        return self._request("GET", path, params=params)

    def get_remote_agent(self, agent_id: str) -> Dict[str, Any]:
        """Retrieves deep configuration of a single remote agent."""
        clean_id = agent_id.split("/")[-1]
        path = f"/v1alpha/projects/{self.project_number}/locations/{self.location}/instances/{self.customer_id}/remoteAgents/{clean_id}"
        return self._request("GET", path)

    def get_email_settings_type(self) -> Dict[str, Any]:
        """Retrieves email transport type (custom vs Google default SMTP)."""
        path = f"/v1alpha/projects/{self.project_number}/locations/{self.location}/instances/{self.customer_id}/moduleSettings/EmailSettingsType/properties"
        return self._request("GET", path)

    def get_email_settings(self) -> Dict[str, Any]:
        """Retrieves email SMTP server and credential configuration properties."""
        path = f"/v1alpha/projects/{self.project_number}/locations/{self.location}/instances/{self.customer_id}/moduleSettings/EmailSettings/properties"
        return self._request("GET", path)

    def get_support_settings(self) -> Dict[str, Any]:
        """Retrieves Google Support access delegation properties."""
        path = f"/v1alpha/projects/{self.project_number}/locations/{self.location}/instances/{self.customer_id}/moduleSettings/Support/properties"
        return self._request("GET", path)

    def list_soar_networks(
        self,
        page_size: int = 50,
        page_token: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Discovers customer-defined CIDR network address ranges."""
        path = f"/v1alpha/projects/{self.project_number}/locations/{self.location}/instances/{self.customer_id}/soarNetworks"
        params: Dict[str, Any] = {"pageSize": page_size}
        if page_token:
            params["pageToken"] = page_token
        return self._request("GET", path, params=params)

    def get_soar_network(self, network_id: str) -> Dict[str, Any]:
        """Retrieves configuration of a single customer-defined CIDR network."""
        clean_id = network_id.split("/")[-1]
        path = f"/v1alpha/projects/{self.project_number}/locations/{self.location}/instances/{self.customer_id}/soarNetworks/{clean_id}"
        return self._request("GET", path)

    def list_soar_domains(
        self,
        page_size: int = 50,
        page_token: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Discovers approved customer domain names."""
        path = f"/v1alpha/projects/{self.project_number}/locations/{self.location}/instances/{self.customer_id}/soarDomains"
        params: Dict[str, Any] = {"pageSize": page_size}
        if page_token:
            params["pageToken"] = page_token
        return self._request("GET", path, params=params)

    def get_soar_domain(self, domain_id: str) -> Dict[str, Any]:
        """Retrieves configuration of a single approved customer domain."""
        clean_id = domain_id.split("/")[-1]
        path = f"/v1alpha/projects/{self.project_number}/locations/{self.location}/instances/{self.customer_id}/soarDomains/{clean_id}"
        return self._request("GET", path)

    def list_soar_custom_lists(
        self,
        page_size: int = 1000,
        page_token: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Discovers SOAR custom list key-value retention entries."""
        path = f"/v1alpha/projects/{self.project_number}/locations/{self.location}/instances/{self.customer_id}/customLists"
        params: Dict[str, Any] = {"pageSize": page_size}
        if page_token:
            params["pageToken"] = page_token
        return self._request("GET", path, params=params)

    def get_soar_custom_list(self, list_id: str) -> Dict[str, Any]:
        """Retrieves configuration of a single SOAR custom list entry."""
        clean_id = list_id.split("/")[-1]
        path = f"/v1alpha/projects/{self.project_number}/locations/{self.location}/instances/{self.customer_id}/customLists/{clean_id}"
        return self._request("GET", path)

    def list_email_templates(
        self,
        page_size: int = 1000,
        page_token: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Discovers email templates (plain text and HTML)."""
        path = f"/v1alpha/projects/{self.project_number}/locations/{self.location}/instances/{self.customer_id}/emailTemplates"
        params: Dict[str, Any] = {"pageSize": page_size}
        if page_token:
            params["pageToken"] = page_token
        return self._request("GET", path, params=params)

    def get_email_template(self, template_id: str) -> Dict[str, Any]:
        """Retrieves complete email template content and parameters."""
        clean_id = template_id.split("/")[-1]
        path = f"/v1alpha/projects/{self.project_number}/locations/{self.location}/instances/{self.customer_id}/emailTemplates/{clean_id}"
        return self._request("GET", path)

    def list_entities_blocklists(
        self,
        page_size: int = 50,
        page_token: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Discovers entity noise-reduction blocklist rules."""
        path = f"/v1alpha/projects/{self.project_number}/locations/{self.location}/instances/{self.customer_id}/entitiesBlocklists"
        params: Dict[str, Any] = {"pageSize": page_size}
        if page_token:
            params["pageToken"] = page_token
        return self._request("GET", path, params=params)

    def get_entities_blocklist(self, blocklist_id: str) -> Dict[str, Any]:
        """Retrieves configuration of a single entity blocklist rule."""
        clean_id = blocklist_id.split("/")[-1]
        path = f"/v1alpha/projects/{self.project_number}/locations/{self.location}/instances/{self.customer_id}/entitiesBlocklists/{clean_id}"
        return self._request("GET", path)

    def list_sla_definitions(
        self,
        page_size: int = 50,
        page_token: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Discovers Service Level Agreement definitions."""
        path = f"/v1alpha/projects/{self.project_number}/locations/{self.location}/instances/{self.customer_id}/slaDefinitions"
        params: Dict[str, Any] = {"pageSize": page_size}
        if page_token:
            params["pageToken"] = page_token
        return self._request("GET", path, params=params)

    def get_sla_definition(self, sla_id: str) -> Dict[str, Any]:
        """Retrieves configuration of a single SLA definition."""
        clean_id = sla_id.split("/")[-1]
        path = f"/v1alpha/projects/{self.project_number}/locations/{self.location}/instances/{self.customer_id}/slaDefinitions/{clean_id}"
        return self._request("GET", path)

    def list_request_templates(
        self,
        page_size: int = 50,
        page_token: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Discovers manual case request form templates."""
        path = f"/v1alpha/projects/{self.project_number}/locations/{self.location}/instances/{self.customer_id}/requestTemplates"
        params: Dict[str, Any] = {"pageSize": page_size}
        if page_token:
            params["pageToken"] = page_token
        return self._request("GET", path, params=params)

    def get_request_template(self, template_id: str) -> Dict[str, Any]:
        """Retrieves configuration of a single manual case request form template."""
        clean_id = template_id.split("/")[-1]
        path = f"/v1alpha/projects/{self.project_number}/locations/{self.location}/instances/{self.customer_id}/requestTemplates/{clean_id}"
        return self._request("GET", path)

    # -------------------------------------------------------------------------
    # Milestone 6.6: SOAR Ingestion Connectors & Webhooks
    # -------------------------------------------------------------------------

    def list_soar_ingestion_connectors(
        self,
        integration: str = "-",
        connector_id: str = "-",
        page_size: int = 1000,
        page_token: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Discovers configured SOAR ingestion connector instances across integrations."""
        path = (
            f"/v1alpha/projects/{self.project_number}/locations/{self.location}/"
            f"instances/{self.customer_id}/integrations/{integration}/connectors/{connector_id}/connectorInstances"
        )
        params: Dict[str, Any] = {"pageSize": page_size}
        if page_token:
            params["pageToken"] = page_token
        return self._request("GET", path, params=params)

    def get_soar_ingestion_connector(
        self,
        instance_id: str,
        integration: str = "-",
        connector_id: str = "-",
    ) -> Dict[str, Any]:
        """Retrieves configuration of a single SOAR ingestion connector instance."""
        clean_id = instance_id.split("/")[-1]
        path = (
            f"/v1alpha/projects/{self.project_number}/locations/{self.location}/"
            f"instances/{self.customer_id}/integrations/{integration}/connectors/{connector_id}/connectorInstances/{clean_id}"
        )
        return self._request("GET", path)

    def list_soar_webhooks(
        self,
        page_size: int = 1000,
        page_token: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Discovers configured SOAR event ingestion webhooks."""
        path = f"/v1alpha/projects/{self.project_number}/locations/{self.location}/instances/{self.customer_id}/webhooks"
        params: Dict[str, Any] = {"pageSize": page_size}
        if page_token:
            params["pageToken"] = page_token
        return self._request("GET", path, params=params)

    def get_soar_webhook(self, webhook_id: str) -> Dict[str, Any]:
        """Retrieves configuration and JSON schema mapping for a single SOAR webhook."""
        clean_id = webhook_id.split("/")[-1]
        path = f"/v1alpha/projects/{self.project_number}/locations/{self.location}/instances/{self.customer_id}/webhooks/{clean_id}"
        return self._request("GET", path)















