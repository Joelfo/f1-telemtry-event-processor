from ep.processors.patch_emitter import PatchEmitter


def test_build_patch() -> None:
    emitter = PatchEmitter()
    patch = emitter.build_patch(
        path="player.car.speed_kph",
        value=320,
        source_type="car_metrics",
    )
    assert patch == {
        "path": "player.car.speed_kph",
        "value": 320,
        "source_type": "car_metrics",
    }


def test_patches_from_payload() -> None:
    emitter = PatchEmitter()
    patches = emitter.patches_from_payload(
        base_path="player.car",
        payload={"speed_kph": 300, "gear": 8},
        source_type="car_metrics",
    )
    assert patches == [
        {"path": "player.car.speed_kph", "value": 300, "source_type": "car_metrics"},
        {"path": "player.car.gear", "value": 8, "source_type": "car_metrics"},
    ]
