"""
Unit tests for Digital Twin event models.

Tests validation, serialization, and integration with existing POLARIS patterns.
"""

import json
import sys
from pathlib import Path
import pytest
from datetime import datetime, timezone
from pydantic import ValidationError

# Add parent directory to path to import from polaris
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
from polaris.models.digital_twin_events import KnowledgeEvent, CalibrationEvent
from polaris.models.telemetry import TelemetryEvent
from polaris.models.actions import ExecutionResult, ActionStatus


class TestKnowledgeEvent:
    """Test cases for KnowledgeEvent model."""
    
    def test_knowledge_event_with_telemetry_data(self):
        """Test KnowledgeEvent with TelemetryEvent data."""
        telemetry = TelemetryEvent(
            name="cpu.usage",
            value=85.3,
            unit="percent",
            source="swim_monitor"
        )
        
        event = KnowledgeEvent(
            source="monitor_adapter",
            event_type="telemetry",
            data=telemetry
        )
        
        assert event.source == "monitor_adapter"
        assert event.event_type == "telemetry"
        assert isinstance(event.data, TelemetryEvent)
        assert event.data.name == "cpu.usage"
        assert event.data.value == 85.3
        assert event.event_id is not None
        assert event.timestamp is not None
    
    def test_knowledge_event_with_execution_result_data(self):
        """Test KnowledgeEvent with ExecutionResult data."""
        execution_result = ExecutionResult(
            action_id="test-action-123",
            action_type="ADD_SERVER",
            status=ActionStatus.SUCCESS,
            started_at=datetime.now(timezone.utc).isoformat(),
            finished_at=datetime.now(timezone.utc).isoformat(),
            duration_sec=5.0,
            message="Successfully added server"
        )
        
        event = KnowledgeEvent(
            source="execution_adapter",
            event_type="execution_status",
            data=execution_result
        )
        
        assert event.source == "execution_adapter"
        assert event.event_type == "execution_status"
        assert isinstance(event.data, ExecutionResult)
        assert event.data.action_id == "test-action-123"
        assert event.data.status == ActionStatus.SUCCESS
    
    def test_knowledge_event_with_anomaly_data(self):
        """Test KnowledgeEvent with custom anomaly data."""
        anomaly_data = {
            "anomaly_type": "performance_degradation",
            "severity": "high",
            "affected_metrics": ["cpu.usage", "response.time"],
            "confidence": 0.95
        }
        
        event = KnowledgeEvent(
            source="anomaly_detector",
            event_type="anomaly",
            data=anomaly_data
        )
        
        assert event.source == "anomaly_detector"
        assert event.event_type == "anomaly"
        assert isinstance(event.data, dict)
        assert event.data["anomaly_type"] == "performance_degradation"
        assert event.data["confidence"] == 0.95
    
    def test_knowledge_event_validation(self):
        """Test KnowledgeEvent validation rules."""
        # Test invalid event_type
        with pytest.raises(ValidationError) as exc_info:
            KnowledgeEvent(
                source="test",
                event_type="invalid_type",
                data={"test": "data"}
            )
        assert "event_type must be one of" in str(exc_info.value)
        
        # Test empty source
        with pytest.raises(ValidationError) as exc_info:
            KnowledgeEvent(
                source="",
                event_type="telemetry",
                data={"test": "data"}
            )
        assert "source cannot be empty" in str(exc_info.value)
    
    def test_knowledge_event_serialization(self):
        """Test KnowledgeEvent serialization methods."""
        event = KnowledgeEvent(
            source="test_source",
            event_type="telemetry",
            data={"metric": "test", "value": 42},
            metadata={"system": "test"}
        )
        
        # Test to_dict
        event_dict = event.to_dict()
        assert isinstance(event_dict, dict)
        assert event_dict["source"] == "test_source"
        assert event_dict["event_type"] == "telemetry"
        assert event_dict["data"]["metric"] == "test"
        assert event_dict["metadata"]["system"] == "test"
        
        # Test to_json
        event_json = event.to_json()
        assert isinstance(event_json, str)
        parsed = json.loads(event_json)
        assert parsed["source"] == "test_source"
        
        # Test to_nats_bytes
        event_bytes = event.to_nats_bytes()
        assert isinstance(event_bytes, bytes)
        parsed_from_bytes = json.loads(event_bytes.decode('utf-8'))
        assert parsed_from_bytes["source"] == "test_source"
    
    def test_knowledge_event_case_normalization(self):
        """Test that event_type is normalized to lowercase."""
        event = KnowledgeEvent(
            source="test",
            event_type="TELEMETRY",
            data={"test": "data"}
        )
        assert event.event_type == "telemetry"


class TestCalibrationEvent:
    """Test cases for CalibrationEvent model."""
    
    def test_calibration_event_creation(self):
        """Test basic CalibrationEvent creation."""
        event = CalibrationEvent(
            prediction_id="pred-123",
            actual_outcome={"cpu": 75.0, "memory": 60.0},
            predicted_outcome={"cpu": 80.0, "memory": 65.0},
            accuracy_metrics={"mse": 0.1, "mae": 0.08, "accuracy_score": 0.92}
        )
        
        assert event.prediction_id == "pred-123"
        assert event.actual_outcome["cpu"] == 75.0
        assert event.predicted_outcome["memory"] == 65.0
        assert event.accuracy_metrics["accuracy_score"] == 0.92
        assert event.source == "meta_learning"  # default value
        assert event.calibration_id is not None
        assert event.timestamp is not None
    
    def test_calibration_event_validation(self):
        """Test CalibrationEvent validation rules."""
        # Test empty prediction_id
        with pytest.raises(ValidationError) as exc_info:
            CalibrationEvent(
                prediction_id="",
                actual_outcome={"cpu": 75.0},
                predicted_outcome={"cpu": 80.0},
                accuracy_metrics={"mse": 0.1}
            )
        assert "prediction_id cannot be empty" in str(exc_info.value)
        
        # Test empty accuracy_metrics
        with pytest.raises(ValidationError) as exc_info:
            CalibrationEvent(
                prediction_id="pred-123",
                actual_outcome={"cpu": 75.0},
                predicted_outcome={"cpu": 80.0},
                accuracy_metrics={}
            )
        assert "accuracy_metrics cannot be empty" in str(exc_info.value)
        
        # Test non-numeric accuracy metrics
        with pytest.raises(ValidationError) as exc_info:
            CalibrationEvent(
                prediction_id="pred-123",
                actual_outcome={"cpu": 75.0},
                predicted_outcome={"cpu": 80.0},
                accuracy_metrics={"mse": "invalid"}
            )
        assert "Input should be a valid number" in str(exc_info.value)
        
        # Test empty outcomes
        with pytest.raises(ValidationError) as exc_info:
            CalibrationEvent(
                prediction_id="pred-123",
                actual_outcome={},
                predicted_outcome={"cpu": 80.0},
                accuracy_metrics={"mse": 0.1}
            )
        assert "actual_outcome cannot be empty" in str(exc_info.value)
    
    def test_calibration_event_accuracy_score_calculation(self):
        """Test accuracy score calculation method."""
        event = CalibrationEvent(
            prediction_id="pred-123",
            actual_outcome={"cpu": 75.0},
            predicted_outcome={"cpu": 80.0},
            accuracy_metrics={"score1": 0.8, "score2": 0.9, "score3": 0.7}
        )
        
        accuracy = event.calculate_accuracy_score()
        expected = (0.8 + 0.9 + 0.7) / 3
        assert abs(accuracy - expected) < 0.001
        
        # Test with empty metrics
        event_empty = CalibrationEvent(
            prediction_id="pred-123",
            actual_outcome={"cpu": 75.0},
            predicted_outcome={"cpu": 80.0},
            accuracy_metrics={"invalid": 2.0}  # out of range, should be ignored
        )
        accuracy_empty = event_empty.calculate_accuracy_score()
        assert accuracy_empty == 0.0
    
    def test_calibration_event_serialization(self):
        """Test CalibrationEvent serialization methods."""
        event = CalibrationEvent(
            prediction_id="pred-123",
            actual_outcome={"cpu": 75.0, "memory": 60.0},
            predicted_outcome={"cpu": 80.0, "memory": 65.0},
            accuracy_metrics={"mse": 0.1, "accuracy_score": 0.92},
            metadata={"model_version": "1.0"}
        )
        
        # Test to_dict
        event_dict = event.to_dict()
        assert isinstance(event_dict, dict)
        assert event_dict["prediction_id"] == "pred-123"
        assert event_dict["actual_outcome"]["cpu"] == 75.0
        assert event_dict["metadata"]["model_version"] == "1.0"
        
        # Test to_json
        event_json = event.to_json()
        assert isinstance(event_json, str)
        parsed = json.loads(event_json)
        assert parsed["prediction_id"] == "pred-123"
        
        # Test to_nats_bytes
        event_bytes = event.to_nats_bytes()
        assert isinstance(event_bytes, bytes)
        parsed_from_bytes = json.loads(event_bytes.decode('utf-8'))
        assert parsed_from_bytes["prediction_id"] == "pred-123"
    
    def test_calibration_event_with_metadata(self):
        """Test CalibrationEvent with metadata."""
        metadata = {
            "model_version": "1.2.3",
            "prediction_type": "forecast",
            "horizon_minutes": 30
        }
        
        event = CalibrationEvent(
            prediction_id="pred-456",
            actual_outcome={"response_time": 150.0},
            predicted_outcome={"response_time": 140.0},
            accuracy_metrics={"mae": 10.0, "mape": 0.07},
            metadata=metadata
        )
        
        assert event.metadata == metadata
        assert event.metadata["model_version"] == "1.2.3"
        assert event.metadata["horizon_minutes"] == 30


class TestEventIntegration:
    """Test integration between Digital Twin events and existing POLARIS models."""
    
    def test_knowledge_event_with_real_telemetry(self):
        """Test KnowledgeEvent integration with real TelemetryEvent."""
        # Create a real TelemetryEvent following POLARIS patterns
        telemetry = TelemetryEvent(
            name="system.cpu.usage",
            value=78.5,
            unit="percent",
            source="swim_monitor",
            tags={"host": "server-01", "region": "us-east"},
            metadata={"collection_method": "prometheus"}
        )
        
        # Wrap in KnowledgeEvent
        knowledge_event = KnowledgeEvent(
            source="monitor_adapter",
            event_type="telemetry",
            data=telemetry,
            metadata={"system_id": "swim-cluster-01"}
        )
        
        # Verify integration
        assert isinstance(knowledge_event.data, TelemetryEvent)
        assert knowledge_event.data.name == "system.cpu.usage"  # normalized by TelemetryEvent
        assert knowledge_event.data.tags["host"] == "server-01"
        assert knowledge_event.metadata["system_id"] == "swim-cluster-01"
        
        # Test serialization preserves nested structure
        serialized = knowledge_event.to_dict()
        assert serialized["data"]["name"] == "system.cpu.usage"
        assert serialized["data"]["tags"]["host"] == "server-01"
    
    def test_knowledge_event_with_real_execution_result(self):
        """Test KnowledgeEvent integration with real ExecutionResult."""
        # Create a real ExecutionResult following POLARIS patterns
        execution_result = ExecutionResult(
            action_id="action-789",
            action_type="SCALE_UP",
            status=ActionStatus.SUCCESS,
            started_at="2025-08-15T10:30:00Z",
            finished_at="2025-08-15T10:30:05Z",
            duration_sec=5.0,
            message="Successfully scaled up cluster",
            output={"new_instances": 3, "total_instances": 5}
        )
        
        # Wrap in KnowledgeEvent
        knowledge_event = KnowledgeEvent(
            source="execution_adapter",
            event_type="execution_status",
            data=execution_result,
            metadata={"cluster_id": "prod-cluster-01"}
        )
        
        # Verify integration
        assert isinstance(knowledge_event.data, ExecutionResult)
        assert knowledge_event.data.action_type == "SCALE_UP"
        assert knowledge_event.data.success is True  # derived from status
        assert knowledge_event.data.output["new_instances"] == 3
        
        # Test serialization preserves nested structure
        serialized = knowledge_event.to_dict()
        assert serialized["data"]["action_type"] == "SCALE_UP"
        assert serialized["data"]["output"]["total_instances"] == 5