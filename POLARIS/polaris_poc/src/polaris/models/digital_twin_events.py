"""
Digital Twin event data models for POLARIS framework.

This module defines the structured event models used for Digital Twin
communication, extending existing POLARIS patterns for telemetry and actions.
"""

import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Union
from pydantic import BaseModel, Field, field_validator, model_validator, ConfigDict

from .telemetry import TelemetryEvent
from .actions import ExecutionResult


class KnowledgeEvent(BaseModel):
    """
    Knowledge event for Digital Twin updates via NATS.
    
    This model represents system state updates sent to the Digital Twin,
    including telemetry data, execution results, and anomaly information.
    Extends existing POLARIS patterns for consistency.
    """
    
    event_id: str = Field(
        default_factory=lambda: str(uuid.uuid4()),
        description="Unique identifier for this knowledge event"
    )
    
    timestamp: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(),
        description="ISO 8601 timestamp when the event was created"
    )
    
    source: str = Field(
        ...,
        description="Source component that generated this event (e.g., 'monitor_adapter', 'execution_adapter')"
    )
    
    event_type: str = Field(
        ...,
        description="Type of knowledge event: 'telemetry', 'execution_status', 'anomaly'"
    )
    
    data: Union[TelemetryEvent, ExecutionResult, Dict[str, Any]] = Field(
        ...,
        description="Event data - can be TelemetryEvent, ExecutionResult, or custom anomaly data"
    )
    
    metadata: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Additional metadata associated with the event"
    )
    
    @field_validator('event_type')
    def validate_event_type(cls, v):
        """Validate event type is one of the supported types."""
        valid_types = {'telemetry', 'execution_status', 'anomaly'}
        if v.lower() not in valid_types:
            raise ValueError(f"event_type must be one of: {valid_types}")
        return v.lower()
    
    @field_validator('source')
    def validate_source(cls, v):
        """Ensure source is not empty."""
        if not v or not v.strip():
            raise ValueError("source cannot be empty")
        return v.strip()
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return self.model_dump(exclude_none=True)
    
    def to_json(self) -> str:
        """Convert to JSON string."""
        return self.model_dump_json(exclude_none=True)
    
    def to_nats_bytes(self) -> bytes:
        """Convert to bytes for NATS publishing."""
        return self.model_dump_json(exclude_none=True).encode('utf-8')
    
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "event_id": "123e4567-e89b-12d3-a456-426614174000",
                "timestamp": "2025-08-15T10:30:00Z",
                "source": "monitor_adapter",
                "event_type": "telemetry",
                "data": {
                    "name": "cpu.usage",
                    "value": 85.3,
                    "unit": "percent",
                    "timestamp": "2025-08-15T10:30:00Z",
                    "source": "swim_monitor"
                },
                "metadata": {
                    "system_id": "swim-cluster-01",
                    "region": "us-east"
                }
            }
        }
    )


class CalibrationEvent(BaseModel):
    """
    Calibration event for Digital Twin model accuracy feedback.
    
    This model represents feedback about prediction accuracy, allowing the
    Digital Twin to calibrate and improve its world model over time.
    """
    
    calibration_id: str = Field(
        default_factory=lambda: str(uuid.uuid4()),
        description="Unique identifier for this calibration event"
    )
    
    timestamp: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(),
        description="ISO 8601 timestamp when the calibration was created"
    )
    
    prediction_id: str = Field(
        ...,
        description="ID of the original prediction being calibrated"
    )
    
    actual_outcome: Dict[str, Any] = Field(
        ...,
        description="The actual observed outcome"
    )
    
    predicted_outcome: Dict[str, Any] = Field(
        ...,
        description="The originally predicted outcome"
    )
    
    accuracy_metrics: Dict[str, float] = Field(
        ...,
        description="Calculated accuracy metrics (e.g., 'mse', 'mae', 'accuracy_score')"
    )
    
    source: str = Field(
        default="meta_learning",
        description="Source component that generated this calibration"
    )
    
    metadata: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Additional metadata about the calibration"
    )
    
    @field_validator('prediction_id')
    def validate_prediction_id(cls, v):
        """Ensure prediction_id is not empty."""
        if not v or not v.strip():
            raise ValueError("prediction_id cannot be empty")
        return v.strip()
    
    @field_validator('accuracy_metrics')
    def validate_accuracy_metrics(cls, v):
        """Ensure accuracy metrics are not empty."""
        if not v:
            raise ValueError("accuracy_metrics cannot be empty")
        return v
    
    @model_validator(mode='after')
    def validate_outcomes(self) -> 'CalibrationEvent':
        """Validate that actual and predicted outcomes have compatible structure."""
        if not self.actual_outcome:
            raise ValueError("actual_outcome cannot be empty")
        if not self.predicted_outcome:
            raise ValueError("predicted_outcome cannot be empty")
        
        return self
    
    def calculate_accuracy_score(self) -> float:
        """
        Calculate a simple overall accuracy score from metrics.
        Returns a value between 0.0 and 1.0.
        """
        if not self.accuracy_metrics:
            return 0.0
        
        # Simple average of all metrics (assuming they're normalized 0-1)
        scores = [v for v in self.accuracy_metrics.values() if 0 <= v <= 1]
        return sum(scores) / len(scores) if scores else 0.0
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return self.model_dump(exclude_none=True)
    
    def to_json(self) -> str:
        """Convert to JSON string."""
        return self.model_dump_json(exclude_none=True)
    
    def to_nats_bytes(self) -> bytes:
        """Convert to bytes for NATS publishing."""
        return self.model_dump_json(exclude_none=True).encode('utf-8')
    
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "calibration_id": "456e7890-e89b-12d3-a456-426614174001",
                "timestamp": "2025-08-15T10:35:00Z",
                "prediction_id": "pred_123e4567-e89b-12d3-a456-426614174000",
                "actual_outcome": {
                    "cpu_usage": 78.5,
                    "response_time": 120.3,
                    "error_rate": 0.02
                },
                "predicted_outcome": {
                    "cpu_usage": 82.1,
                    "response_time": 115.0,
                    "error_rate": 0.01
                },
                "accuracy_metrics": {
                    "mse": 0.15,
                    "mae": 0.12,
                    "accuracy_score": 0.88
                },
                "source": "meta_learning",
                "metadata": {
                    "prediction_type": "forecast",
                    "horizon_minutes": 15
                }
            }
        }
    )