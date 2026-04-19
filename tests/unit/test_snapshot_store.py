import pytest

from ep.state.snapshot_store import SnapshotStore


def test_reset_returns_default_snapshot_shape() -> None:
    store = SnapshotStore()
    snapshot = store.reset(session_uid=999, player_car_index=0, updated_at_ns=101)

    assert snapshot["v"] == 1
    assert snapshot["session_uid"] == 999
    assert snapshot["player_car_index"] == 0
    assert snapshot["updated_at_ns"] == 101
    assert snapshot["player"]["car"]["speed_kph"] == 0
    assert snapshot["player"]["lap"]["best_lap_time_ms"] is None
    assert snapshot["player"]["tyres"]["wear_rate_pct_per_min"] is None


def test_apply_patch_updates_nested_path_and_timestamp() -> None:
    store = SnapshotStore()
    store.reset(session_uid=1, player_car_index=0)

    patch = store.apply_patch(
        path="player.car.speed_kph",
        value=312,
        source_type="car_metrics",
        updated_at_ns=222,
    )

    snapshot = store.get_snapshot()
    assert patch == {
        "path": "player.car.speed_kph",
        "value": 312,
        "source_type": "car_metrics",
    }
    assert snapshot["player"]["car"]["speed_kph"] == 312
    assert snapshot["updated_at_ns"] == 222


def test_apply_patch_rejects_invalid_path() -> None:
    store = SnapshotStore()
    store.reset(session_uid=1, player_car_index=0)

    with pytest.raises(ValueError):
        store.apply_patch(path="", value=1, source_type="car_metrics")
