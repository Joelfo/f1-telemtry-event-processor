from ep.pipeline.router import (
    DERIVED_CAR_CHANNEL,
    DERIVED_TYRE_CHANNEL,
    STATE_PATCH_CHANNEL,
    Router,
)


def _car_event() -> dict:
    return {
        "packet_type": 6,
        "payload": {
            "speed_kph": 300,
            "throttle": 0.7,
            "brake": 0.1,
            "steer": 0.0,
            "gear": 7,
            "engine_rpm": 12000,
            "drs": False,
            "tyres_surface_temp": [80, 81, 82, 83],
            "tyres_inner_temp": [90, 91, 92, 93],
        },
    }


def _status_event() -> dict:
    return {
        "packet_type": 7,
        "payload": {
            "ers_store_energy": 2500000.0,
            "ers_deploy_mode": 2,
            "ers_harvested_this_lap_mguk": 12000.0,
            "ers_deployed_this_lap": 8000.0,
        },
    }


def test_router_emits_derived_and_patch_messages_for_car_telemetry() -> None:
    router = Router()
    router.route("car_status", _status_event())

    messages = router.route("car_telemetry", _car_event())
    channels = [message.channel for message in messages]

    assert DERIVED_CAR_CHANNEL in channels
    assert DERIVED_TYRE_CHANNEL in channels
    assert STATE_PATCH_CHANNEL in channels
