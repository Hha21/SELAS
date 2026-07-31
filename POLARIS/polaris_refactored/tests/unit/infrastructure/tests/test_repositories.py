import asyncio
from datetime import datetime, timedelta, timezone
import pytest

from polaris_refactored.src.infrastructure.data_storage.repository import (
    SystemStateRepository,
    AdaptationActionRepository,
    LearnedPatternRepository,
    ExecutionResultRepository,
)
from polaris_refactored.src.infrastructure.data_storage.storage_backend import (
    InMemoryGraphStorageBackend,
)
from polaris_refactored.src.infrastructure.exceptions import DataStoreError
from polaris_refactored.src.domain.models import (
    MetricValue,
    SystemState,
    HealthStatus,
    AdaptationAction,
    LearnedPattern,
    ExecutionResult,
    ExecutionStatus,
)


@pytest.mark.asyncio
async def test_system_state_repository_current_and_range_and_delete():
    be = InMemoryGraphStorageBackend()
    await be.connect()
    repo = SystemStateRepository(be)

    sys_id = "sys-A"
    t1 = datetime(2023, 1, 1, 0, 0, 0)
    t2 = datetime(2023, 1, 1, 1, 0, 0)
    m = {"cpu": MetricValue(name="cpu", value=0.5, unit="pct", timestamp=t1)}

    s1 = SystemState(system_id=sys_id, timestamp=t1, metrics=m, health_status=HealthStatus.HEALTHY)
    s2 = SystemState(system_id=sys_id, timestamp=t2, metrics=m, health_status=HealthStatus.WARNING)

    await repo.save(s1)
    await repo.save(s2)

    # get_current_state should return s2
    cur = await repo.get_current_state(sys_id)
    assert cur is not None and cur.timestamp == t2 and cur.health_status == HealthStatus.WARNING

    # get_states_in_range covering both
    states = await repo.get_states_in_range(sys_id, t1 - timedelta(minutes=1), t2 + timedelta(minutes=1))
    assert {st.timestamp for st in states} == {t1, t2}

    # delete by key used in save
    key = f"{sys_id}_{t1.isoformat()}"
    assert await repo.delete(key) is True


@pytest.mark.asyncio
async def test_adaptation_action_repository_crud_and_query():
    be = InMemoryGraphStorageBackend()
    await be.connect()
    repo = AdaptationActionRepository(be)

    a1 = AdaptationAction(action_id="a1", action_type="scale", target_system="svc-1", parameters={"replicas": 3})
    a2 = AdaptationAction(action_id="a2", action_type="restart", target_system="svc-2", parameters={})

    await repo.save(a1)
    await repo.save(a2)

    loaded = await repo.get_by_id("a1")
    assert loaded and loaded.action_type == "scale" and loaded.target_system == "svc-1"

    # query by target_system
    svc1 = await repo.list_by_target_system("svc-1")
    assert len(svc1) == 1 and svc1[0].action_id == "a1"

    assert await repo.delete("a2") is True


@pytest.mark.asyncio
async def test_learned_pattern_repository_crud_list_query():
    be = InMemoryGraphStorageBackend()
    await be.connect()
    repo = LearnedPatternRepository(be)

    lp = LearnedPattern(
        pattern_id="p1",
        pattern_type="anomaly",
        conditions={"cpu": ">80"},
        outcomes={"scale": 2},
        confidence=0.9,
        learned_at=datetime(2023, 1, 2),
        usage_count=5,
    )

    await repo.save(lp)
    got = await repo.get_by_id("p1")
    assert got and got.confidence == 0.9 and got.usage_count == 5

    allp = await repo.list_all()
    assert len(allp) == 1

    q = await repo.query({"pattern_type": "anomaly"})
    assert len(q) == 1 and q[0].pattern_id == "p1"

    assert await repo.delete("p1") is True


@pytest.mark.asyncio
async def test_execution_result_repository_status_and_query():
    be = InMemoryGraphStorageBackend()
    await be.connect()
    repo = ExecutionResultRepository(be)

    r1 = ExecutionResult(
        action_id="a1",
        status=ExecutionStatus.SUCCESS,
        result_data={"ok": True},
        error_message=None,
        execution_time_ms=120,
        completed_at=datetime(2023, 1, 3),
    )
    await repo.save(r1)

    got = await repo.get_by_id("a1")
    assert got and got.status == ExecutionStatus.SUCCESS and got.execution_time_ms == 120

    # Save with unknown status string directly in backend to simulate unknown
    await be.store("execution_results", "a2", {
        "action_id": "a2",
        "status": "UNKNOWN",
        "result_data": {},
        "error_message": None,
        "execution_time_ms": 10,
        "completed_at": datetime(2023, 1, 4).isoformat(),
    })
    q = await repo.query({})
    # One known success and one defaulted to FAILED
    statuses = {res.status for res in q}
    assert ExecutionStatus.SUCCESS in statuses and ExecutionStatus.FAILED in statuses


@pytest.mark.asyncio
async def test_repository_error_wrapping_on_backend_exception(monkeypatch):
    be = InMemoryGraphStorageBackend()
    await be.connect()
    repo = AdaptationActionRepository(be)

    a = AdaptationAction(action_id="a1", action_type="scale", target_system="svc", parameters={})

    async def boom(*args, **kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(be, "store", boom)

    with pytest.raises(DataStoreError) as ex:
        await repo.save(a)

    assert ex.value.error_code == "DATA_STORE_ERROR"
    assert ex.value.context.get("operation") == "save"
    assert ex.value.context.get("entity_type") == "AdaptationAction"
