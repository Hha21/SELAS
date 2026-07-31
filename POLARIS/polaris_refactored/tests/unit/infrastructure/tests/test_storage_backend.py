import asyncio
from datetime import datetime, timedelta, timezone
import pytest

from polaris_refactored.src.infrastructure.data_storage.storage_backend import (
    InMemoryGraphStorageBackend,
    _match_filters,
)


@pytest.mark.asyncio
async def test_add_edge_and_neighbors_out_in_and_filter():
    be = InMemoryGraphStorageBackend()
    await be.connect()

    await be.add_edge("A", "B", "depends_on", strength=0.7, metadata={"k": "v"})
    await be.add_edge("A", "C", "depends_on", strength=0.9)
    await be.add_edge("B", "C", "relates_to", strength=0.5)

    # Outgoing neighbors from A (default direction out)
    out_A = await be.get_neighbors("A")
    assert {e["target"] for e in out_A} == {"B", "C"}
    assert all(e["source"] == "A" for e in out_A)

    # Incoming neighbors to C
    inc_C = await be.get_neighbors("C", direction="in")
    # Both A->C and B->C arrive
    assert {e["source"] for e in inc_C} == {"A", "B"}

    # Relationship type filter
    out_A_depends = await be.get_neighbors("A", relationship_type="depends_on")
    assert {e["target"] for e in out_A_depends} == {"B", "C"}
    out_A_relates = await be.get_neighbors("A", relationship_type="relates_to")
    assert out_A_relates == []

    await be.disconnect()


@pytest.mark.asyncio
async def test_remove_edge_with_and_without_type():
    be = InMemoryGraphStorageBackend()
    await be.connect()

    await be.add_edge("S", "T", "x", strength=1.0)
    await be.add_edge("S", "T", "y", strength=1.0)

    # Remove only type x
    removed = await be.remove_edge("S", "T", relationship_type="x")
    assert removed is True
    out_S = await be.get_neighbors("S")
    assert len(out_S) == 1 and out_S[0]["relationship_type"] == "y"

    # Remove remaining regardless of type
    removed2 = await be.remove_edge("S", "T")
    assert removed2 is True
    assert await be.get_neighbors("S") == []


@pytest.mark.asyncio
async def test_get_dependency_chain_bfs_depth_and_graph_shape():
    be = InMemoryGraphStorageBackend()
    await be.connect()

    # A -> B -> C ; A -> D
    await be.add_edge("A", "B", "depends_on")
    await be.add_edge("B", "C", "depends_on")
    await be.add_edge("A", "D", "depends_on")

    chain = await be.get_dependency_chain("A", max_depth=2, direction="out")
    assert chain["root"] == "A"
    assert chain["depth"] == 2
    graph = chain["graph"]
    # Depth 0: A -> [B, D]
    assert set(graph.get("A", [])) == {"B", "D"}
    # Depth 1: B -> [C], D -> [] (no outgoing)
    assert set(graph.get("B", [])) == {"C"}
    assert graph.get("D", []) == []


@pytest.mark.asyncio
async def test_invalid_direction_defaults_to_out():
    be = InMemoryGraphStorageBackend()
    await be.connect()
    await be.add_edge("X", "Y", "r")
    # invalid direction should be treated as out
    neigh = await be.get_neighbors("X", direction="sideways")
    assert len(neigh) == 1 and neigh[0]["target"] == "Y"


def test_match_filters_equality_and_ranges():
    now = datetime.now(timezone.utc)
    earlier = (now - timedelta(hours=1)).isoformat()
    later = (now + timedelta(hours=1)).isoformat()

    item = {
        "id": "42",
        "kind": "demo",
        "value": 10,
        "timestamp": now.isoformat(),
    }

    # Equality match positive/negative
    assert _match_filters(item, {"id": "42"}) is True
    assert _match_filters(item, {"id": "x"}) is False

    # Range on numeric
    assert _match_filters(item, {"value": {"$gte": 5, "$lte": 15}}) is True
    assert _match_filters(item, {"value": {"$gte": 11}}) is False

    # Range on ISO timestamp strings
    assert _match_filters(item, {"timestamp": {"$gte": earlier, "$lte": later}}) is True
    assert _match_filters(item, {"timestamp": {"$gte": later}}) is False
