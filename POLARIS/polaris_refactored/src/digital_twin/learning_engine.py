"""
Learning Engine Implementation

Implements the learning capabilities for the POLARIS digital twin framework.
The learning engine enables the system to improve its behavior over time through
various learning strategies and pattern recognition.

Key Features:
- Reinforcement learning for adaptation policies
- Pattern recognition for system behavior
- Knowledge extraction from system interactions
- Continuous improvement through feedback loops
"""

from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional
from datetime import datetime, timezone
import uuid

from ..domain.models import ExecutionResult, LearnedPattern
from ..infrastructure.di import Injectable
from ..infrastructure.observability.factory import get_digital_twin_logger
from .knowledge_base import PolarisKnowledgeBase
from .world_model import PolarisWorldModel


class LearningContext:
    """Context information for learning operations.
    
    Captures the complete context of an adaptation event, including:
    - System state before and after adaptation
    - Adaptation action and its result
    - Relevant system metrics and metadata
    
    This context is used by learning strategies to extract insights and
    improve future adaptations.
    """
    
    def __init__(
        self, 
        system_id: str, 
        adaptation_result: ExecutionResult,
        system_state_before: Dict[str, Any],
        system_state_after: Dict[str, Any]
    ):
        self.system_id = system_id
        self.adaptation_result = adaptation_result
        self.system_state_before = system_state_before
        self.system_state_after = system_state_after


class LearnedKnowledge:
    """Represents knowledge learned from an adaptation.
    
    Encapsulates insights gained from system adaptations, including:
    - Type of knowledge (pattern, rule, model update, etc.)
    - Confidence level in the learned knowledge
    - Metadata about the learning context
    - Application scope and constraints
    """
    
    def __init__(self, knowledge_type: str, data: Dict[str, Any], confidence: float):
        self.knowledge_type = knowledge_type
        self.data = data
        self.confidence = confidence


class LearningStrategy(ABC):
    """Abstract base class for learning strategies.
    
    Defines the interface for different learning approaches that can be
    composed by the learning engine. Concrete implementations should
    handle specific learning paradigms like reinforcement learning,
    pattern recognition, or statistical learning.
    """
    
    @abstractmethod
    def can_learn_from(self, context: LearningContext) -> bool:
        """Check if this strategy can learn from the given context."""
        pass
    
    @abstractmethod
    async def learn(self, context: LearningContext) -> LearnedKnowledge:
        """Learn from the given context."""
        pass


class ReinforcementLearningStrategy(LearningStrategy):
    """Reinforcement learning strategy."""
    
    def can_learn_from(self, context: LearningContext) -> bool:
        # Basic requirement: have an adaptation result and a system_id
        return bool(context.system_id and context.adaptation_result)
    
    async def learn(self, context: LearningContext) -> LearnedKnowledge:
        # Very simple reward: +1 for success, -1 for failed/timeout, +0.5 for partial
        status = context.adaptation_result.status.value if context.adaptation_result else "unknown"
        reward_map = {"success": 1.0, "partial": 0.5, "timeout": -1.0, "failed": -1.0}
        reward = reward_map.get(status, 0.0)
        data = {
            "estimated_reward": reward,
            "status": status,
        }
        confidence = 0.5 + 0.5 * max(0.0, reward)  # boost if positive reward
        return LearnedKnowledge("reinforcement", data, min(confidence, 1.0))


class PatternRecognitionStrategy(LearningStrategy):
    """Pattern recognition learning strategy."""
    
    def can_learn_from(self, context: LearningContext) -> bool:
        return bool(context.system_id)
    
    async def learn(self, context: LearningContext) -> LearnedKnowledge:
        # Minimal heuristic: compute simple diffs between after and before states
        diffs: Dict[str, Any] = {}
        before = context.system_state_before or {}
        after = context.system_state_after or {}
        try:
            for k, v in after.items():
                if k in before and isinstance(v, (int, float)) and isinstance(before[k], (int, float)):
                    diffs[f"delta_{k}"] = float(v) - float(before[k])
        except Exception:
            pass
        confidence = 0.6 if diffs else 0.3
        return LearnedKnowledge("pattern", {"diffs": diffs}, confidence)


class PolarisLearningEngine(Injectable):
    """POLARIS Learning Engine using Strategy pattern.
    
    Orchestrates multiple learning strategies to continuously improve
    system behavior. The learning engine is responsible for:
    - Coordinating different learning strategies
    - Managing the learning lifecycle
    - Integrating learned knowledge into the system
    - Providing insights and recommendations
    
    The engine follows the Strategy pattern to support multiple learning
    approaches that can be composed and extended.
    
    Attributes:
    - _learning_strategies (List[LearningStrategy]): List of learning strategies
    - _world_model (Optional[PolarisWorldModel]): World model instance
    - _kb (Optional[PolarisKnowledgeBase]): Knowledge base instance
    
    Methods:
    - learn_from_adaptation (ExecutionResult) -> None: Learn from an adaptation result
    - learn_from_system_behavior (str, Dict[str, Any]) -> None: Learn from observed system behavior
    - get_learning_insights (str) -> List[Dict[str, Any]]: Get insights learned about a system
    - recommend_adaptations (str, Dict[str, Any]) -> List[Dict[str, Any]]: Recommend adaptations based on learned knowledge
    """
    
    def __init__(self, learning_strategies: List[LearningStrategy] = None, knowledge_base: Optional[PolarisKnowledgeBase] = None, world_model: Optional[PolarisWorldModel] = None):
        self._learning_strategies = learning_strategies or [
            ReinforcementLearningStrategy(),
            PatternRecognitionStrategy()
        ]
        self._world_model: Optional[PolarisWorldModel] = world_model
        self._kb: Optional[PolarisKnowledgeBase] = knowledge_base
        
        # Use POLARIS logging
        self.logger = get_digital_twin_logger("learning_engine")
    
    async def learn_from_adaptation(self, adaptation_result: ExecutionResult) -> None:
        """Learn from an adaptation result.

        Best-effort extraction of context:
        - system_id is taken from result_data['system_id'] or ['target_system'] if available.
        - pre/post states are optional and may be empty if not retrievable.
        """
        system_id = None
        if adaptation_result and isinstance(adaptation_result.result_data, dict):
            system_id = adaptation_result.result_data.get("system_id") or adaptation_result.result_data.get("target_system")
        pre_state: Dict[str, Any] = {}
        post_state: Dict[str, Any] = {}
        if self._kb and system_id:
            # Get current state as post snapshot; pre snapshot unavailable in this minimal version
            current = await self._kb.get_current_state(system_id)
            if current:
                # Flatten a few numeric metrics for learning context
                post_state = {m: mv.value for m, mv in current.metrics.items() if isinstance(mv.value, (int, float))}
        context = LearningContext(system_id or "", adaptation_result, pre_state, post_state)
        # Run strategies and persist learned knowledge as patterns
        if not self._kb:
            return
        for strat in self._learning_strategies:
            try:
                if not strat.can_learn_from(context):
                    continue
                knowledge = await strat.learn(context)
                pattern = LearnedPattern(
                    pattern_id=str(uuid.uuid4()),
                    pattern_type=knowledge.knowledge_type,
                    conditions={"system_id": context.system_id},
                    outcomes=knowledge.data,
                    confidence=knowledge.confidence,
                    learned_at=datetime.now(timezone.utc),
                    usage_count=0,
                )
                await self._kb.store_learned_pattern(pattern)
            except Exception:
                continue
    
    async def learn_from_system_behavior(
        self, 
        system_id: str, 
        behavior_data: Dict[str, Any]
    ) -> None:
        """Learn from observed system behavior."""
        # Construct a synthetic ExecutionResult to reuse strategy pipeline
        dummy_result = ExecutionResult(
            action_id="behavior_observation",
            status=None,  # type: ignore[arg-type]
            result_data={"system_id": system_id, **behavior_data},
        )
        ctx = LearningContext(system_id, dummy_result, behavior_data, behavior_data)
        if not self._kb:
            return
        for strat in self._learning_strategies:
            try:
                if not strat.can_learn_from(ctx):
                    continue
                knowledge = await strat.learn(ctx)
                pattern = LearnedPattern(
                    pattern_id=str(uuid.uuid4()),
                    pattern_type=knowledge.knowledge_type,
                    conditions={"system_id": system_id},
                    outcomes=knowledge.data,
                    confidence=knowledge.confidence,
                    learned_at=datetime.now(timezone.utc),
                    usage_count=0,
                )
                await self._kb.store_learned_pattern(pattern)
            except Exception:
                continue
    
    async def get_learning_insights(self, system_id: str) -> List[Dict[str, Any]]:
        """Get insights learned about a system."""
        if not self._kb:
            return []
        patterns = await self._kb.query_patterns(pattern_type="", conditions={"system_id": system_id})
        return [
            {
                "pattern_id": p.pattern_id,
                "pattern_type": p.pattern_type,
                "confidence": p.confidence,
                "outcomes": p.outcomes,
                "usage_count": p.usage_count,
            }
            for p in patterns
        ]
    
    async def recommend_adaptations(
        self, 
        system_id: str, 
        current_state: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """Recommend adaptations based on learned knowledge."""
        if not self._kb:
            return []
        # Retrieve similar patterns and propose actions from outcomes map if present
        patterns = await self._kb.get_similar_patterns(current_conditions={"system_id": system_id, **current_state}, similarity_threshold=0.3)
        recommendations: List[Dict[str, Any]] = []
        for p in patterns:
            recs = p.outcomes.get("recommended_actions") if isinstance(p.outcomes, dict) else None
            if isinstance(recs, list):
                for r in recs:
                    recommendations.append({"action": r, "confidence": p.confidence, "source_pattern": p.pattern_id})
            else:
                # Fallback: synthesize a generic recommendation
                recommendations.append({
                    "action": {"action_type": "observe", "parameters": {}},
                    "confidence": p.confidence,
                    "source_pattern": p.pattern_id,
                })
        # Deduplicate by action_type if present
        seen = set()
        deduped = []
        for rec in recommendations:
            key = rec.get("action", {}).get("action_type") if isinstance(rec.get("action"), dict) else None
            if key and key in seen:
                continue
            if key:
                seen.add(key)
            deduped.append(rec)
        return deduped