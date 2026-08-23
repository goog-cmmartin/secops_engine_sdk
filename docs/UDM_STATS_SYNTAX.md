# UDM Stats Search Query Language Reference

Google SecOps UDM Stats Search provides analytical grouping, aggregations, and metrics calculations over historical UDM events, entity graphs, and detection records.

Unlike standard UDM Search (which streams raw event logs sequentially), **Stats Search** uses **`match`** and **`outcome`** blocks to group, aggregate, sort, and project calculated fields.

---

## 📐 Query Structure & Clauses

A UDM Stats query consists of four primary sections:

```
[UDM Filter Expression]
match:
    $[variable1] [, $[variable2] ...]
outcome:
    $[out_metric1] = [aggregation_function]([udm_field])
    $[out_metric2] = [aggregation_function]([udm_field])
[order:
    $[out_metric1] [asc | desc]]
[limit:
    [integer]]
```

### Clauses Explained

| Clause | Purpose | Example |
| :--- | :--- | :--- |
| **Filter Expression** | Standard UDM conditions defining the event scope. | `metadata.event_type = $et` or `metadata.base_labels.namespaces = "SDL"` |
| **`match:`** | Defines the grouping dimensions / variables. | `match: $logType` or `match: $user, $ip` |
| **`outcome:`** | Defines computed metric variables using aggregation functions. | `outcome: $total = count(metadata.id)` |
| **`order:`** | *(Optional)* Specifies ordering column and direction. | `order: $total desc` |
| **`limit:`** | *(Optional)* Maximum number of aggregated groups to return. | `limit: 10` |

---

## 📊 Supported Aggregation Functions

The compiler supports the following outcome aggregations:

- **`count(field)`**: Total number of matching events. Example: `$total = count(metadata.id)`
- **`count_distinct(field)`**: Number of distinct values for a field. Example: `$unique_users = count_distinct(principal.user.userid)`
- **`sum(field)`**: Arithmetic sum of a numeric field. Example: `$total_bytes = sum(network.sent_bytes)`
- **`avg(field)`**: Arithmetic mean of a numeric field. Example: `$avg_latency = avg(network.session_duration.seconds)`
- **`min(field)`**: Minimum value observed. Example: `$earliest = min(metadata.event_timestamp.seconds)`
- **`max(field)`**: Maximum value observed. Example: `$peak_bytes = max(network.sent_bytes)`

---

## 💡 Canonical Query Examples

### 1. UDM Events Aggregation by Log Type & Namespace

Aggregate ingested logs in the `"SDL"` namespace grouped by `log_type`:

```udm
metadata.base_labels.namespaces = "SDL"
metadata.log_type = $logType
match:
    $logType
outcome:
    $total = count(metadata.id)
order:
    $total desc
limit: 20
```

### 2. UDM Event Type Distribution

Group and count events across all event types:

```udm
metadata.event_type = $et
match:
    $et
outcome:
    $total = count(metadata.id)
limit: 25
```

### 3. UDM Entity Graph Distribution

Aggregate entity records in the UDM graph grouped by `entity_type`:

```udm
graph.metadata.entity_type = $et
match:
    $et
outcome:
    $total = count(graph.metadata.product_entity_id)
order:
    $total desc
limit: 10
```

### 4. Detections Breakdown by Rule Name

Group detection alerts by rule name to identify high-volume alert rules:

```udm
detection.detection.rule_name = $rn
match:
    $rn
outcome:
    $total = count(detection.id)
order:
    $total desc
limit: 10
```

### 5. Multi-Variable Network Activity Grouping

Group network traffic by target hostname and compute both total count and sent bytes:

```udm
target.hostname = $host
principal.ip = $src_ip
match:
    $host, $src_ip
outcome:
    $connection_count = count(metadata.id)
    $total_bytes = sum(network.sent_bytes)
order:
    $total_bytes desc
limit: 50
```

---

## 💻 CLI Usage

### Basic Execution (Rich Table)
```bash
python3 clients/cli/secops.py search-stats \
  --query 'metadata.event_type = $et match: $et outcome: $total = count(metadata.id)' \
  --start "2026-08-22T00:00:00Z" \
  --end "2026-08-23T00:00:00Z"
```

### Export to CSV
```bash
python3 clients/cli/secops.py search-stats \
  --query 'detection.detection.rule_name = $rn match: $rn outcome: $total = count(detection.id) order: $total desc limit: 10' \
  --format csv
```

### Export to JSON
```bash
python3 clients/cli/secops.py search-stats \
  --query 'graph.metadata.entity_type = $et match: $et outcome: $total = count(graph.metadata.product_entity_id) limit: 10' \
  --format json
```

---

## 🐍 Python SDK Usage

```python
from engine import SecOpsEngine, StatsSearchRequest

engine = SecOpsEngine()

# Direct convenience invocation
session = engine.search_udm_stats(
    query='metadata.log_type = $logType match: $logType outcome: $total = count(metadata.id) order: $total desc limit: 10',
    start_time="2026-08-22T00:00:00Z",
    end_time="2026-08-23T00:00:00Z",
)

if session.result:
    print(f"Total Groups: {session.result.total_results}")
    for row in session.result.rows:
        print(f"LogType: {row.get('logType')} -> Total: {row.get('total')}")
```
