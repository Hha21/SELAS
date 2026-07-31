# POLARIS Knowledge Base - Interface Documentation

## Overview

The POLARIS Knowledge Base provides telemetry storage, aggregation, and querying capabilities. It operates as a standalone service that receives telemetry events via NATS and maintains intelligent observations with trend analysis.

## Core Models

### KBEntry - Knowledge Base Entry

```python
from polaris.knowledge_base.models import KBEntry, KBDataType

# Basic entry
entry = KBEntry(
    data_type=KBDataType.OBSERVATION,
    summary="CPU usage observation",
    content={"cpu_usage": 85.5, "trend": "increasing"},
    metric_name="cpu.usage",
    metric_value=85.5,
    source="server-001"
)

# Telemetry event entry
telemetry = KBEntry(
    data_type=KBDataType.RAW_TELEMETRY_EVENT,
    metric_name="swim.server.utilization",
    metric_value=95.0,
    source="swim_monitor",
    content={"timestamp": "2025-08-21T10:00:00Z"}
)
```

### KBQuery - Query Interface

```python
from polaris.knowledge_base.models import KBQuery, QueryType

# Structured query
query = KBQuery(
    query_type=QueryType.STRUCTURED,
    data_types=["observation"],
    filters={"metric_name": "cpu.usage"},
    limit=10
)

# Natural language search
query = KBQuery(
    query_type=QueryType.NATURAL_LANGUAGE,
    query_text="high cpu usage server performance",
    limit=20
)
```

## Knowledge Base Service

### Starting the Service

```bash
# Start Knowledge Base Service
python src/scripts/start_component.py knowledge-base

# Service connects to NATS and subscribes to:
# - polaris.telemetry.events (individual events)
# - polaris.telemetry.events.batch (batch events)
# - polaris.knowledge.query (query requests)
# - polaris.knowledge.stats (statistics requests)
```

### Service Architecture

The service automatically:

- **Buffers** raw telemetry events (50 events per metric/source)
- **Aggregates** when buffers are full into OBSERVATION entries
- **Tracks trends** (stable/increasing/decreasing) between aggregations
- **Updates** existing observations instead of creating duplicates
- **Indexes** content for fast queries

## Query Client Interface

### Command Line Usage

```bash
# Get service statistics
python src/scripts/kb_query_client.py stats

# Query recent observations (aggregated telemetry)
python src/scripts/kb_query_client.py observations --limit 5

# Query raw telemetry events
python src/scripts/kb_query_client.py telemetry --limit 10

# Search by keyword
python src/scripts/kb_query_client.py search --keyword "response"

# Interactive mode
python src/scripts/kb_query_client.py interactive
```

### Programmatic Interface

```python
from polaris.services.knowledge_base_service import KnowledgeBaseService
from polaris.knowledge_base.models import KBQuery, QueryType

# Direct service usage (for integration)
kb_service = KnowledgeBaseService()
await kb_service.start()

# NATS-based client (for external components)
import nats

async def query_kb():
    nc = await nats.connect("nats://localhost:4222")

    # Get statistics
    stats_response = await nc.request("polaris.knowledge.stats", b"")
    stats = json.loads(stats_response.data.decode())

    # Execute query
    query = {
        "query_type": "structured",
        "data_types": ["observation"],
        "limit": 5
    }
    response = await nc.request(
        "polaris.knowledge.query",
        json.dumps(query).encode()
    )
    result = json.loads(response.data.decode())
```

## Telemetry Processing

### Automatic Aggregation

The system automatically processes telemetry:

1. **Raw Events** → Buffered (50 events per metric/source)
2. **Buffer Full** → Statistical aggregation + trend analysis
3. **Observation Created/Updated** with:
   - Average, min, max values
   - Trend direction (stable/increasing/decreasing)
   - Update count and timestamps

### Trend Analysis

```python
# Observations include trend information
{
    "statistic": "aggregation",
    "count": 50,
    "average_value": 87.3,
    "previous_average": 85.1,
    "trend": "increasing",  # stable/increasing/decreasing
    "total_updates": 5,
    "min_value": 82.0,
    "max_value": 94.5
}
```

### Example Observation Entry

```python
# Aggregated observation from telemetry buffer
obs = KBEntry(
    entry_id="obs_swim_server_utilization_swim_monitor",
    data_type=KBDataType.OBSERVATION,
    summary="Updated metric 'swim.server.utilization' from 'swim_monitor' (#3). Avg: 98.50 (was 97.20, trend: increasing), Min: 97.0, Max: 100.0.",
    metric_name="swim.server.utilization",
    source="swim_monitor",
    content={
        "statistic": "aggregation",
        "count": 50,
        "average_value": 98.5,
        "previous_average": 97.2,
        "trend": "increasing",
        "total_updates": 3,
        "min_value": 97.0,
        "max_value": 100.0,
        "last_update": "2025-08-21T15:30:00.123456",
        "time_window_start": "2025-08-21T15:25:00.000000+00:00",
        "time_window_end": "2025-08-21T15:30:00.000000+00:00"
    },
    tags=["aggregated", "observation", "swim.server.utilization", "swim_monitor"]
)
```

## Integration Examples

### Monitor Adapter Integration

```python
# Monitor adapter automatically publishes to NATS
await self.nats_client.publish_json(
    "polaris.telemetry.events",
    {
        "name": "cpu.usage",
        "value": 85.5,
        "source": "system_monitor",
        "timestamp": datetime.now().isoformat()
    }
)
```

### Digital Twin Integration

```python
# Query KB for historical patterns
async def analyze_system_state():
    nc = await nats.connect("nats://localhost:4222")

    query = {
        "query_type": "structured",
        "data_types": ["observation"],
        "filters": {"trend": "increasing"},
        "limit": 10
    }

    response = await nc.request("polaris.knowledge.query", json.dumps(query).encode())
    results = json.loads(response.data.decode())

    # Analyze increasing trends for predictions
    return analyze_trends(results['results'])
```

## Performance & Statistics

### Service Statistics

```python
# Statistics available via polaris.knowledge.stats
{
    "service": {
        "events_processed": 3500,
        "queries_served": 15,
        "start_time": 1692614400.0
    },
    "knowledge_base": {
        "total_permanent_entries": 2500,
        "data_type_counts": {"observation": 2500},
        "active_telemetry_buffers": 11,
        "total_buffered_events": 450,
        "unique_tags": 14,
        "indexed_keywords": 5000
    },
    "uptime_seconds": 1800
}
```

### Query Response Format

```python
# Standard query response
{
    "query_id": "uuid-string",
    "success": true,
    "total_results": 25,
    "processing_time_ms": 15.2,
    "results": [
        {
            "entry_id": "obs_cpu_usage_server1",
            "data_type": "observation",
            "summary": "CPU trend analysis...",
            "content": {...},
            "timestamp": "2025-08-21T15:30:00.000000+00:00"
        }
    ]
}
```

## Data Types

### Available Data Types

- `RAW_TELEMETRY_EVENT` - Individual telemetry measurements (buffered)
- `OBSERVATION` - Aggregated telemetry with trend analysis (permanent)
- `ADAPTATION_DECISION` - System adaptation choices
- `SYSTEM_GOAL` - System objectives and targets
- `LEARNED_PATTERN` - Discovered behavioral patterns
- `SYSTEM_INFO` - Configuration and metadata
- `GENERIC_FACT` - General knowledge entries

### Query Types

- `STRUCTURED` - Filter-based queries with precise criteria
- `NATURAL_LANGUAGE` - Keyword-based content search

## Configuration

### Service Configuration

```yaml
# Default configuration for Knowledge Base Service
knowledge_base:
  nats_url: "nats://localhost:4222"
  telemetry_buffer_size: 50

  # NATS subjects
  subjects:
    telemetry_events: "polaris.telemetry.events"
    telemetry_batch: "polaris.telemetry.events.batch"
    query_requests: "polaris.knowledge.query"
    stats_requests: "polaris.knowledge.stats"
```

### Starting Components

```bash
# Required services
./bin/nats-server                                    # NATS message broker
python src/scripts/start_component.py monitor --plugin-dir extern  # Telemetry source
python src/scripts/start_component.py knowledge-base # KB service
```
