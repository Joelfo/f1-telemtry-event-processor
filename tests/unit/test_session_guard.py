from ep.state.session_guard import SessionGuard


def _event(*, session_uid: int, overall_frame_identifier: int, session_time: float = 0.0) -> dict:
    return {
        "session_uid": session_uid,
        "overall_frame_identifier": overall_frame_identifier,
        "session_time": session_time,
    }


def test_first_event_is_processed_and_marks_session_change() -> None:
    guard = SessionGuard()
    decision = guard.evaluate(_event(session_uid=1, overall_frame_identifier=10, session_time=1.0))
    assert decision.should_process is True
    assert decision.session_changed is True
    assert decision.out_of_order is False


def test_out_of_order_event_is_dropped() -> None:
    guard = SessionGuard()
    guard.evaluate(_event(session_uid=1, overall_frame_identifier=10, session_time=1.0))
    decision = guard.evaluate(_event(session_uid=1, overall_frame_identifier=9, session_time=1.1))
    assert decision.should_process is False
    assert decision.out_of_order is True


def test_session_change_accepts_event_and_resets_ordering() -> None:
    guard = SessionGuard()
    guard.evaluate(_event(session_uid=1, overall_frame_identifier=100, session_time=10.0))

    decision = guard.evaluate(_event(session_uid=2, overall_frame_identifier=1, session_time=0.1))
    assert decision.should_process is True
    assert decision.session_changed is True
    assert decision.out_of_order is False

    next_decision = guard.evaluate(_event(session_uid=2, overall_frame_identifier=2, session_time=0.2))
    assert next_decision.should_process is True
    assert next_decision.out_of_order is False
