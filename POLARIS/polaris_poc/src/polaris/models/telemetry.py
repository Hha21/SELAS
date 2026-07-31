"""
Telemetry data models for POLARIS framework.

This module defines the structured telemetry events used for monitoring
and metric collection across the POLARIS adaptation system.
"""

from datetime import datetime, timezone
from typing import Any, Dict, Optional, Union
from pydantic import BaseModel, Field, field_validator, model_validator


class TelemetryEvent(BaseModel):
    """
    Structured telemetry event for POLARIS.
    
    This model represents a single metric measurement from a managed system,
    including metadata about the source, timestamp, and unit of measurement.
    """
    
    name: str = Field(
        ...,
        description="Name of the metric",
        pattern="^[a-zA-Z_][a-zA-Z0-9_.]*$"
    )
    
    value: Union[float, int, bool, str] = Field(
        ...,
        description="The metric value"
    )
    
    unit: str = Field(
        default="unknown",
        description="Unit of measurement"
    )
    
    timestamp: Optional[str] = Field(
        default=None,
        description="ISO 8601 timestamp of when the metric was collected"
    )
    
    source: str = Field(
        default="unknown",
        description="Source system or component that generated this metric"
    )
    
    tags: Optional[Dict[str, str]] = Field(
        default=None,
        description="Additional tags for categorization and filtering"
    )
    
    metadata: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Additional metadata associated with the metric"
    )
    
    @field_validator('timestamp', mode='before')
    def set_timestamp(cls, v):
        """Set timestamp to current UTC time if not provided."""
        if v is None:
            return datetime.now(timezone.utc).isoformat()
        return v
    
    @field_validator('name')
    def normalize_name(cls, v):
        """Normalize metric name to lowercase with dots."""
        return v.lower().replace('_', '.')
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return self.model_dump(exclude_none=True)
    
    def to_json(self) -> str:
        """Convert to JSON string."""
        return self.model_dump_json(exclude_none=True)
    
    model_config = {
        "json_schema_extra": {
            "example": {
                "name": "cpu.usage",
                "value": 85.3,
                "unit": "percent",
                "timestamp": "2025-08-14T10:30:00Z",
                "source": "swim_monitor",
                "tags": {
                    "host": "server-01",
                    "region": "us-east"
                }
            }
        }
    }

class TelemetryBatch(BaseModel):
    """
    Batch of telemetry events for efficient transmission.
    """
    
    batch_id: Optional[str] = Field(
        default=None,
        description="Unique identifier for this batch"
    )
    
    batch_timestamp: Optional[str] = Field(
        default=None,
        description="Timestamp when the batch was created"
    )
    
    count: Optional[int] = Field(
        default=None,
        description="Number of events in this batch"
    )
    
    events: list[TelemetryEvent] = Field(
        ...,
        description="List of telemetry events"
    )
    
    @field_validator('batch_timestamp', mode='before')
    def set_batch_timestamp(cls, v):
        """Set batch timestamp if not provided."""
        if v is None:
            return datetime.now(timezone.utc).isoformat()
        return v

    @field_validator('batch_id', mode='before')
    def set_batch_id(cls, v):
        """Generate batch ID if not provided."""
        if v is None:
            import uuid
            return str(uuid.uuid4())
        return v

    @model_validator(mode='before')
    def set_count(cls, values):
        """Set count based on events list if not provided."""
        if values.get('count') is None and 'events' in values:
            values['count'] = len(values['events'])
        return values
