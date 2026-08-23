# Discovery Observation: UDM Stats Search (Aggregation & Analytics)

**Status:** `VERIFIED`  
**Endpoint Base:** `https://us-chronicle.googleapis.com/v1alpha`  
**Workflows:** `search.udm.stats`

---

## 1. Query Validation

```http
POST /v1alpha/projects/{project_number}/locations/{location}/instances/{customer_id}:validateQuery?allowUnreplacedPlaceholders=false&dialect=DIALECT_UDM_SEARCH&rawQuery={encoded_query}
```

### Response
```json
{
  "queryType": "QUERY_TYPE_UDM_QUERY"
}
```

---

## 2. Operation Initiation

```http
POST /v1alpha/projects/{project_number}/locations/{location}/instances/{customer_id}/legacy:legacyFetchUdmSearchView
Content-Type: application/json

{
  "baselineQuery": "metadata.event_type = $et\nmatch: $et\noutcome: $total = count(metadata.id)\nlimit: 2",
  "baselineTimeRange": {
    "startTime": "2026-08-21T15:34:59.063Z",
    "endTime": "2026-08-23T15:34:59.063Z"
  },
  "snapshotQuery": null,
  "eventList": {"maxReturnedEvents": 10000},
  "fieldAggregations": {"maxValuesPerField": 60},
  "detectionOptions": {
    "detectionList": {"maxReturnedDetections": 1000},
    "fieldAggregations": {"maxValuesPerField": 60},
    "fetchNonAlertingDetections": true
  },
  "prevalence": {
    "bucketSize": {"resolutionInSeconds": 1800},
    "getPrevalence": true
  },
  "caseInsensitive": true,
  "generateAiOverview": true,
  "returnOperationIdOnly": true
}
```

### Response
```json
[
  {
    "operation": "projects/{project_number}/locations/{location}/instances/{customer_id}/operations/s-udm-..."
  }
]
```

---

## 3. Streaming and Progress Retrieval

```http
GET /v1alpha/{operation_name}:streamSearch?eventIndexEnd=2000&eventIndexStart=1&pageRequest=false&paginationEnabled=true
```

### Response Shape (Stats Payload)
```json
[
  {
    "operation": {
      "name": "projects/.../operations/s-udm-...",
      "metadata": {
        "@type": "type.googleapis.com/google.cloud.chronicle.v1main.UdmSearchOperationMetadata",
        "startTime": "...",
        "endTime": "...",
        "progress": 1,
        "statsRowsCount": 2,
        "baselineQuery": "..."
      },
      "done": true,
      "response": {
        "@type": "type.googleapis.com/google.cloud.chronicle.v1main.LegacyFetchUdmSearchViewResponse",
        "progress": 1,
        "complete": true,
        "stats": {
          "results": [
            {
              "column": "et",
              "values": [{"value": {"stringVal": "USER_RESOURCE_ACCESS"}}, {"value": {"stringVal": "USER_LOGIN"}}],
              "filterable": true,
              "filterExpression": "metadata.event_type",
              "columnMetadata": {
                "column": "MATCH_PLACEHOLDER_et",
                "fieldPath": "udm.metadata.event_type",
                "dataType": "STRING"
              }
            },
            {
              "column": "total",
              "values": [{"value": {"int64Val": "1385218"}}, {"value": {"int64Val": "1304205"}}],
              "columnMetadata": {
                "column": "OUTCOME_total",
                "fieldPath": "udm.metadata.id",
                "functionNameUsed": "COUNT",
                "dataType": "NUMBER"
              }
            }
          ],
          "dataQueryExpression": "metadata.event_type = $et",
          "totalResults": 2,
          "filteredResultCount": 2
        },
        "statsResultAggregation": {
          "fields": [
            {
              "fieldName": "et",
              "baselineEventCount": 2,
              "eventCount": 2,
              "valueCount": 2,
              "allValues": [
                {"value": {"stringValue": "USER_LOGIN"}, "eventCount": 1},
                {"value": {"stringValue": "USER_RESOURCE_ACCESS"}, "eventCount": 1}
              ]
            }
          ],
          "complete": true
        }
      }
    }
  }
]
```
