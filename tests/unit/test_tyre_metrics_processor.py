from ep.processors.tyre_metrics_processor import TyreMetricsProcessor


def _event(surface: list[int], inner: list[int]) -> dict:
    return {
        "packet_type": 6,
        "payload": {
            "tyres_surface_temp": surface,
            "tyres_inner_temp": inner,
        },
    }


def test_tyre_metrics_field_mapping_and_defaults() -> None:
    processor = TyreMetricsProcessor()
    metrics = processor.process(_event([80, 82, 84, 86], [90, 91, 92, 93]))
    assert metrics is not None
    assert metrics["surface_temp_c"] == {"rl": 80, "rr": 82, "fl": 84, "fr": 86}
    assert metrics["inner_temp_c"] == {"rl": 90, "rr": 91, "fl": 92, "fr": 93}
    assert metrics["wear_pct"] == {"rl": 0, "rr": 0, "fl": 0, "fr": 0}
    assert metrics["avg_surface_temp_c"] == 83.0
    assert metrics["avg_wear_pct"] == 0.0
    assert metrics["wear_rate_pct_per_min"] is None


def test_tyre_metrics_no_output_for_invalid_arrays() -> None:
    processor = TyreMetricsProcessor()
    assert processor.process(_event([1, 2, 3], [4, 5, 6, 7])) is None
