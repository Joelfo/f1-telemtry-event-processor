from ep.processors.car_metrics_processor import CarMetricsProcessor


def _car_telemetry_event() -> dict:
    return {
        "packet_type": 6,
        "payload": {
            "speed_kph": 311,
            "throttle": 0.82,
            "brake": 0.13,
            "steer": -0.25,
            "gear": 7,
            "engine_rpm": 11850,
            "drs": True,
        },
    }


def _car_status_event() -> dict:
    return {
        "packet_type": 7,
        "payload": {
            "ers_store_energy": 3210000.5,
            "ers_deploy_mode": 2,
            "ers_harvested_this_lap_mguk": 14500.0,
            "ers_deployed_this_lap": 8900.0,
        },
    }


def test_car_metrics_field_mapping_and_types() -> None:
    processor = CarMetricsProcessor()

    assert processor.process(_car_status_event()) is None

    metrics = processor.process(_car_telemetry_event())
    assert metrics is not None
    assert metrics == {
        "speed_kph": 311,
        "throttle_pct": 82.0,
        "brake_pct": 13.0,
        "steer_pct": -25.0,
        "gear": 7,
        "engine_rpm": 11850,
        "drs_enabled": True,
        "ers_store_energy_j": 3210000.5,
        "ers_deploy_mode": 2,
        "ers_harvest_mguk_j": 14500.0,
        "ers_deployed_this_lap_j": 8900.0,
    }


def test_car_metrics_no_output_for_invalid_payload() -> None:
    processor = CarMetricsProcessor()
    invalid_event = {
        "packet_type": 6,
        "payload": {
            "speed_kph": "fast",
        },
    }
    assert processor.process(invalid_event) is None
