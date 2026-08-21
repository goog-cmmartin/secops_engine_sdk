# Discovery Report 001: UDM Search Validation and Execution Flow

**Status:** `VERIFIED`  
**Target:** Google SecOps (Chronicle) SIEM Search UI & Backend API  
**Environment:**
- **Customer ID:** `a556547c-1cff-43ef-a2e4-cf5b12a865df`
- **Project ID:** `sdl-preview-americas` (`37679061640`)
- **Location/Region:** `us`

---

## 1. Overview of the Observed Flow

Executing a UDM Search in Google SecOps consists of a multi-stage flow:
1. **Interactive Query Validation (`:validateQuery`)**: As the user types in the Monaco editor or initiates a search, the syntax is validated in real-time.
2. **Search Job Initiation (`:legacyFetchUdmSearchView` or direct Search LRO)**: A search job is started on the server, generating an asynchronous Long-Running Operation (`operationId`, e.g. `s-udm-0d54b0e8-bff3-49d0-ab24-c6a26ae876ce`).
3. **Streamed Event Retrieval (`:streamSearch`)**: The frontend reads chunks of events progressively via `:streamSearch` using index pagination (`eventIndexStart`, `eventIndexEnd`, `paginationEnabled=true`).

---

## 2. API Operation 1: Query Validation

* **Method & Path:**  
  `GET https://us-chronicle.googleapis.com/v1alpha/projects/{project_number}/locations/{location}/instances/{customer_id}:validateQuery`
* **Query Parameters:**
  * `dialect`: `DIALECT_UDM_SEARCH`
  * `allowUnreplacedPlaceholders`: `false`
  * `rawQuery`: URL-encoded query string (e.g., `metadata.event_type%20%3D%20%22USER_LOGIN%22`)
* **Headers:**
  * `Authorization`: `Bearer <token>`
* **Status:** `200 OK`
* **Observed Response Payload:**
  ```json
  {
    "queryType": "QUERY_TYPE_UDM_QUERY"
  }
  ```

---

## 3. API Operation 2: Search Job Initiation (LRO Creation)

* **Method & Path:**  
  `POST https://us-chronicle.googleapis.com/v1alpha/projects/{project_number}/locations/{location}/instances/{customer_id}/legacy:legacyFetchUdmSearchView`
* **Observed Request Payload:**
  ```json
  {
    "baselineQuery": "metadata.event_type = \"USER_LOGIN\"",
    "baselineTimeRange": {
      "startTime": "2026-08-16T11:03:00.000Z",
      "endTime": "2026-08-17T11:03:00.000Z"
    },
    "snapshotQuery": null,
    "eventList": {
      "maxReturnedEvents": 10000
    },
    "fieldAggregations": {
      "maxValuesPerField": 60
    },
    "detectionOptions": {
      "detectionList": {
        "maxReturnedDetections": 1000
      },
      "snapshotQuery": "feedback_summary.status != \"CLOSED\"",
      "fieldAggregations": {
        "maxValuesPerField": 60
      },
      "fetchNonAlertingDetections": true
    },
    "prevalence": {
      "bucketSize": {
        "resolutionInSeconds": 900
      },
      "getPrevalence": true
    },
    "caseInsensitive": true,
    "generateAiOverview": true,
    "returnOperationIdOnly": true
  }
  ```
* **Observed Response Payload:**
  ```json
  [
    {
      "operation": "projects/37679061640/locations/us/instances/a556547c-1cff-43ef-a2e4-cf5b12a865df/operations/s-udm-0d54b0e8-bff3-49d0-ab24-c6a26ae876ce"
    }
  ]
  ```

---

## 4. API Operation 3: Incremental Stream Retrieval (`:streamSearch`)

* **Method & Path:**  
  `GET https://us-chronicle.googleapis.com/v1alpha/projects/{project_number}/locations/{location}/instances/{customer_id}/operations/{operation_id}:streamSearch`
* **Query Parameters:**
  * `eventIndexStart`: integer (1-based index, e.g. `1`)
  * `eventIndexEnd`: integer (e.g. `2000`)
  * `pageRequest`: `false`
  * `paginationEnabled`: `true`
* **Response Content:**
  * Chunked JSON stream returning events array, UDM structure (`metadata`, `principal`, `target`, `securityResult`, etc.) and `moreDataAvailable: true/false`.

---

## 5. Mapping to Engine Workflow Architecture

In the SecOps Engine:
```
[Client (CLI / UI / MCP)]
          │
          ▼
   validate_query()   ──> GET :validateQuery (Synchronous pre-check)
          │
          ▼
   start_search()     ──> POST legacy:legacyFetchUdmSearchView -> returns operation_id
          │
          ▼
   stream_events()    ──> GET /operations/{operation_id}:streamSearch (async worker / chunked iterator)
          │
          ▼
   cancel_search()    ──> POST /operations/{operation_id}:cancel (optional cancellation)
```
