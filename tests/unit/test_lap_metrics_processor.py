from ep.processors.lap_metrics_processor import LapMetricsProcessor


def _lap_event(*, current_lap_time_ms: int, last_lap_time_ms: int, sector: int, pit_status: int) -> dict:
    return {
        "packet_type": 2,
        "payload": {
            "current_lap_num": 5,
            "current_lap_time_ms": current_lap_time_ms,
            "last_lap_time_ms": last_lap_time_ms,
            "sector": sector,
            "sector1_time_ms": 31234,
            "sector2_time_ms": 28999,
            "pit_status": pit_status,
        },
    }


def test_lap_metrics_maps_fields_and_enums() -> None:
    processor = LapMetricsProcessor()

    first = processor.process(_lap_event(current_lap_time_ms=45000, last_lap_time_ms=0, sector=0, pit_status=0))
    assert first is not None
    assert first["lap_number"] == 5
    assert first["current_lap_time_ms"] == 45000
    assert first["last_lap_time_ms"] is None
    assert first["best_lap_time_ms"] is None
    assert first["delta_to_best_ms"] is None
    assert first["delta_to_last_ms"] is None
    assert first["sector"] == 1
    assert first["pit_status"] == "none"

    second = processor.process(_lap_event(current_lap_time_ms=46000, last_lap_time_ms=90000, sector=2, pit_status=2))
    assert second is not None
    assert second["best_lap_time_ms"] == 90000
    assert second["delta_to_best_ms"] == -44000
    assert second["delta_to_last_ms"] == -44000
    assert second["sector"] == 3
    assert second["pit_status"] == "in_pit_area"


def test_lap_metrics_no_output_for_unsupported_values() -> None:
    processor = LapMetricsProcessor()
    invalid = _lap_event(current_lap_time_ms=46000, last_lap_time_ms=90000, sector=4, pit_status=0)
    assert processor.process(invalid) is None
