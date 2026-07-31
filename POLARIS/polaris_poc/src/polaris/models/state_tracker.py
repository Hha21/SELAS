"""
Enhanced state tracking functionality for Gemini World Model.

This module provides sophisticated state tracking capabilities including
vector embeddings for historical state storage, metadata tracking,
and state consistency validation.
"""

import json
import logging
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional, Tuple
from collections import defaultdict, deque
import hashlib

from .digital_twin_events import KnowledgeEvent


class StateVector:
    """Represents a system state as a vector for similarity comparisons."""
    
    def __init__(self, state_data: Dict[str, Any], timestamp: str, event_id: str):
        """Initialize state vector.
        
        Args:
            state_data: Dictionary containing state information
            timestamp: ISO timestamp of the state
            event_id: ID of the event that created this state
        """
        self.state_data = state_data
        self.timestamp = timestamp
        self.event_id = event_id
        self.vector_hash = self._compute_hash()
        self.embedding = self._compute_simple_embedding()
    
    def _compute_hash(self) -> str:
        """Compute hash of state data for quick comparisons."""
        state_str = json.dumps(self.state_data, sort_keys=True)
        return hashlib.md5(state_str.encode()).hexdigest()
    
    def _compute_simple_embedding(self) -> List[float]:
        """Compute simple embedding vector for state similarity.
        
        In a real implementation, this would use proper vector embeddings.
        For now, we create a simple numerical representation.
        """
        embedding = [0.0] * 10  # 10-dimensional vector
        
        # Extract numerical features
        for key, value in self.state_data.items():
            if isinstance(value, (int, float)):
                # Map different metrics to different dimensions
                if "cpu" in key.lower():
                    embedding[0] = min(1.0, value / 100.0)
                elif "memory" in key.lower():
                    embedding[1] = min(1.0, value / 100.0)
                elif "response" in key.lower() or "latency" in key.lower():
                    embedding[2] = min(1.0, value / 1000.0)
                elif "error" in key.lower():
                    embedding[3] = min(1.0, value / 10.0)
                elif "throughput" in key.lower():
                    embedding[4] = min(1.0, value / 1000.0)
                else:
                    # Generic numerical feature
                    embedding[5] = min(1.0, abs(value) / 100.0)
        
        # Add temporal features
        try:
            dt = datetime.fromisoformat(self.timestamp.replace('Z', '+00:00'))
            embedding[6] = (dt.hour / 24.0)  # Hour of day
            embedding[7] = (dt.weekday() / 7.0)  # Day of week
        except:
            pass
        
        return embedding
    
    def similarity(self, other: 'StateVector') -> float:
        """Calculate similarity with another state vector.
        
        Args:
            other: Another StateVector to compare with
            
        Returns:
            Similarity score between 0.0 and 1.0
        """
        if len(self.embedding) != len(other.embedding):
            return 0.0
        
        # Simple cosine similarity
        dot_product = sum(a * b for a, b in zip(self.embedding, other.embedding))
        norm_a = sum(a * a for a in self.embedding) ** 0.5
        norm_b = sum(b * b for b in other.embedding) ** 0.5
        
        if norm_a == 0 or norm_b == 0:
            return 0.0
        
        return dot_product / (norm_a * norm_b)


class StateTracker:
    """Enhanced state tracking with vector embeddings and consistency validation."""
    
    def __init__(self, config: Dict[str, Any], logger: Optional[logging.Logger] = None):
        """Initialize state tracker.
        
        Args:
            config: Configuration dictionary
            logger: Logger instance
        """
        self.config = config
        self.logger = logger or logging.getLogger(self.__class__.__name__)
        
        # Configuration
        self.