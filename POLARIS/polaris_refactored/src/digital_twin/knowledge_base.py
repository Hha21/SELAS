"""
Knowledge Base Implementation

Implements the digital twin's knowledge management capabilities for the POLARIS framework.
The knowledge base serves as the central repository for system state, relationships,
and learned patterns to support decision-making and adaptation.

Key Features:
- State persistence and querying
- Relationship management between system components
- Pattern recognition and storage
- Historical data analysis
"""

from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta, timezone

from ..domain.models import SystemState, SystemDependency, LearnedPattern
from ..framework.events import TelemetryEvent
from ..infrastructure.di import Injectable
from ..infrastructure.observability.factory import get_digital_twin_logger
from ..infrastructure.data_storage import (
    PolarisDataStore,
    SystemStateRepository,
    SystemDependencyRepository,
    LearnedPatternRepository,
    AdaptationActionRepository,
    ExecutionResultRepository
)


class PolarisKnowledgeBase(Injectable):
    """
    POLARIS Knowledge Base using Repository and CQRS patterns.
    
    The knowledge base provides a unified interface for storing and retrieving
    system knowledge, including:
    - Current and historical system states
    - Component relationships and dependencies
    - Learned patterns and behaviors
    - Adaptation history and outcomes
    
    It follows the Command Query Responsibility Segregation (CQRS) pattern to
    separate read and write operations for better scalability and performance.
    """
    
    def __init__(self, data_store: PolarisDataStore):
        # Repositories are resolved from the data store for CQRS-style access
        self._data_store = data_store
        # Lazily resolved to allow data_store.start() to run before access
        self._states_repo: Optional[SystemStateRepository] = None
        self._deps_repo: Optional[SystemDependencyRepository] = None
        self._patterns_repo: Optional[LearnedPatternRepository] = None
        self._actions_repo: Optional[AdaptationActionRepository] = None
        self._exec_results_repo: Optional[ExecutionResultRepository] = None
        
        # Use POLARIS logging
        self.logger = get_digital_twin_logger("knowledge_base")

    def _states(self) -> SystemStateRepository:
        if self._states_repo is None:
            self._states_repo = self._data_store.get_repository("system_states")  # type: ignore[assignment]
        return self._states_repo  # type: ignore[return-value]

    def _deps(self) -> SystemDependencyRepository:
        if self._deps_repo is None:
            self._deps_repo = self._data_store.get_repository("system_dependencies")  # type: ignore[assignment]
        return self._deps_repo  # type: ignore[return-value]

    def _patterns(self) -> LearnedPatternRepository:
        if self._patterns_repo is None:
            self._patterns_repo = self._data_store.get_repository("learned_patterns")  # type: ignore[assignment]
        return self._patterns_repo  # type: ignore[return-value]
    
    def _actions(self) -> AdaptationActionRepository:
        if self._actions_repo is None:
            self._actions_repo = self._data_store.get_repository("adaptation_actions")  # type: ignore[assignment]
        return self._actions_repo  # type: ignore[return-value]
    
    def _exec_results(self):
        if self._exec_results_repo is None:
            # Delayed import typing to avoid circulars in type checking
            self._exec_results_repo = self._data_store.get_repository("execution_results")  # type: ignore[assignment]
        return self._exec_results_repo  # type: ignore[return-value]
    
    # Telemetry and State Management
    
    async def store_telemetry(self, telemetry: TelemetryEvent) -> None:
        """Store telemetry data by persisting the included SystemState."""
        state: SystemState = telemetry.system_state
        await self._states().save(state)
    
    async def get_current_state(self, system_id: str) -> Optional[SystemState]:
        """Get the current state of a system."""
        return await self._states().get_current_state(system_id)
    
    async def get_historical_states(
        self, 
        system_id: str, 
        start_time: datetime, 
        end_time: datetime
    ) -> List[SystemState]:
        """Get historical states for a system within a time range."""
        return await self._states().get_states_in_range(system_id, start_time, end_time)
    
    # System Relationships (Graph-based)
    
    async def add_system_relationship(
        self, 
        source_system: str, 
        target_system: str, 
        relationship_type: str,
        strength: float = 1.0,
        metadata: Optional[Dict[str, Any]] = None
    ) -> None:
        """Add a relationship between systems."""
        dep = SystemDependency(
            source_system=source_system,
            target_system=target_system,
            dependency_type=relationship_type,
            strength=strength,
            metadata=metadata or {},
        )
        await self._deps().save(dep)
    
    async def query_system_dependencies(self, system_id: str) -> List[SystemDependency]:
        """Query outgoing dependencies for a system."""
        return await self._deps().get_neighbors(system_id, direction="out")
    
    async def get_dependent_systems(self, system_id: str) -> List[str]:
        """Get systems that depend on the given system (incoming neighbors)."""
        incoming = await self._deps().get_neighbors(system_id, direction="in")
        return [d.source_system for d in incoming]
    
    async def get_dependency_chain(self, system_id: str, max_depth: int = 3) -> Dict[str, Any]:
        """Get the full dependency chain for a system using graph traversal."""
        return await self._deps().get_dependency_chain(system_id, max_depth=max_depth, direction="out")
    
    # Learned Patterns
    
    async def store_learned_pattern(self, pattern: LearnedPattern) -> None:
        """Store a learned pattern."""
        await self._patterns().save(pattern)
    
    async def store_adaptation_actions(self, actions: List["AdaptationAction"]) -> None:
        """Persist planned adaptation actions to the knowledge base.
        
        Uses the document-backed AdaptationActionRepository to store actions for later
        querying via get_adaptation_history(). Best-effort; errors are not raised.
        """
        try:
            repo = self._actions()
        except Exception:
            return
        for a in actions:
            try:
                await repo.save(a)
            except Exception:
                # Best-effort persistence; continue on error
                continue
    
    async def store_execution_result(self, result: "ExecutionResult") -> None:
        """Persist an execution result for an adaptation action (best-effort)."""
        try:
            repo = self._exec_results()
        except Exception:
            return
        try:
            await repo.save(result)
        except Exception:
            return
    
    async def query_patterns(
        self, 
        pattern_type: str, 
        conditions: Dict[str, Any]
    ) -> List[LearnedPattern]:
        """Query learned patterns by type and conditions."""
        # First, filter by pattern_type at the storage layer if provided
        base_filters: Dict[str, Any] = {}
        if pattern_type:
            base_filters["pattern_type"] = pattern_type
        candidates = await self._patterns().query(base_filters)
        if not conditions:
            return candidates
        # Post-filter for conditions subset match
        def _subset(d: Dict[str, Any], cond: Dict[str, Any]) -> bool:
            for k, v in cond.items():
                if k not in d:
                    return False
                if d[k] != v:
                    return False
            return True
        return [p for p in candidates if _subset(p.conditions, conditions)]
    
    async def get_similar_patterns(
        self, 
        current_conditions: Dict[str, Any], 
        similarity_threshold: float = 0.8
    ) -> List[LearnedPattern]:
        """Find patterns similar to current conditions."""
        all_patterns = await self._patterns().list_all()
        if not current_conditions:
            # Return top by confidence if no condition provided
            return sorted(all_patterns, key=lambda p: p.confidence, reverse=True)
        # Simple similarity over condition key/value pairs
        def _similarity(a: Dict[str, Any], b: Dict[str, Any]) -> float:
            if not a and not b:
                return 1.0
            a_items = set(a.items())
            b_items = set(b.items())
            inter = len(a_items & b_items)
            union = len(a_items | b_items)
            return inter / union if union else 0.0
        scored = [(p, _similarity(current_conditions, p.conditions)) for p in all_patterns]
        filtered = [p for (p, s) in scored if s >= similarity_threshold]
        # Sort primarily by similarity (desc), then by confidence (desc)
        filtered.sort(key=lambda p: (_similarity(current_conditions, p.conditions), p.confidence), reverse=True)
        return filtered
    
    # Knowledge Queries
    
    async def query_system_behavior(
        self, 
        system_id: str, 
        behavior_type: str
    ) -> Dict[str, Any]:
        """Query historical behavior patterns for a system."""
        # Simple behavior analysis over recent history (last 24h)
        end_time = datetime.now(timezone.utc)
        start_time = end_time - timedelta(hours=24)
        states = await self.get_historical_states(system_id, start_time, end_time)
        if not states:
            return {"system_id": system_id, "behavior_type": behavior_type, "summary": {}, "samples": 0}
        
        # Aggregate numeric metrics across states
        metric_sums: Dict[str, float] = {}
        metric_counts: Dict[str, int] = {}
        health_counts: Dict[str, int] = {}
        first_ts = states[0].timestamp
        last_ts = states[-1].timestamp
        first_metrics = states[0].metrics
        last_metrics = states[-1].metrics
        
        for st in states:
            hs = getattr(st.health_status, "value", str(st.health_status))
            health_counts[hs] = health_counts.get(hs, 0) + 1
            for k, v in (st.metrics or {}).items():
                try:
                    val = float(getattr(v, "value", v))
                except Exception:
                    continue
                metric_sums[k] = metric_sums.get(k, 0.0) + val
                metric_counts[k] = metric_counts.get(k, 0) + 1
        
        metric_avgs = {k: (metric_sums[k] / metric_counts[k]) for k in metric_sums.keys() if metric_counts.get(k, 0) > 0}
        
        # Compute crude trend for common metrics (delta last-first)
        def _num(m: Any) -> Optional[float]:
            try:
                return float(getattr(m, "value", m))
            except Exception:
                return None
        trend: Dict[str, Any] = {}
        for key in set(list(first_metrics.keys()) + list(last_metrics.keys())):
            a = _num(first_metrics.get(key)) if key in first_metrics else None
            b = _num(last_metrics.get(key)) if key in last_metrics else None
            if a is not None and b is not None:
                trend[key] = {"delta": b - a, "start": a, "end": b}
        
        summary: Dict[str, Any] = {
            "window": {"start": start_time.isoformat(), "end": end_time.isoformat(), "samples": len(states)},
            "health_distribution": health_counts,
            "metric_averages": metric_avgs,
            "metric_trends": trend,
        }
        
        # Behavior-specific notes (extensible)
        notes: List[str] = []
        bt = behavior_type.lower()
        if bt in ("anomaly", "spike"):
            # flag metrics with large delta
            for k, t in trend.items():
                if abs(t.get("delta", 0.0)) >= 0.25:
                    notes.append(f"significant_change:{k}")
        elif bt in ("stability", "stable"):
            unstable = [k for k, t in trend.items() if abs(t.get("delta", 0.0)) >= 0.1]
            if unstable:
                notes.append("not_stable")
            else:
                notes.append("stable_window")
        elif bt in ("trend", "degradation", "improvement"):
            # summarize cpu/latency trends if present
            for focus in ("cpu", "latency"):
                deltas = [t.get("delta", 0.0) for k, t in trend.items() if focus in k.lower()]
                if deltas:
                    avg_delta = sum(deltas) / len(deltas)
                    notes.append(f"{focus}_avg_delta:{avg_delta:.3f}")
        summary["notes"] = notes
        return {"system_id": system_id, "behavior_type": behavior_type, "summary": summary, "samples": len(states)}
    
    async def get_adaptation_history(
        self, 
        system_id: str, 
        action_type: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Get adaptation history for a system."""
        try:
            actions_repo = self._actions()
        except Exception:
            return []
        actions = await actions_repo.list_by_target_system(system_id, action_type=action_type)
        # Sort by created_at descending if available
        actions.sort(key=lambda a: a.created_at or datetime.min, reverse=True)
        # Try to load execution results to enrich history
        exec_repo = None
        try:
            exec_repo = self._exec_results()
        except Exception:
            exec_repo = None
        history: List[Dict[str, Any]] = []
        for a in actions:
            entry: Dict[str, Any] = {
                "action_id": a.action_id,
                "action_type": a.action_type,
                "target_system": a.target_system,
                "parameters": a.parameters,
                "priority": a.priority,
                "timeout_seconds": a.timeout_seconds,
                "created_at": a.created_at.isoformat() if a.created_at else None,
            }
            if exec_repo:
                try:
                    res = await exec_repo.get_by_id(a.action_id)
                    if res:
                        entry["execution_result"] = {
                            "status": getattr(res.status, "value", str(res.status)),
                            "result_data": res.result_data,
                            "error_message": res.error_message,
                            "execution_time_ms": res.execution_time_ms,
                            "completed_at": res.completed_at.isoformat() if res.completed_at else None,
                        }
                except Exception:
                    pass
            history.append(entry)
        return history