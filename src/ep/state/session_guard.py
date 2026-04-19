from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping


@dataclass(frozen=True)
class SessionDecision:
    should_process: bool
    session_changed: bool
    out_of_order: bool
    session_uid: int
    overall_frame_identifier: int


class SessionGuard:
    def __init__(self) -> None:
        self.session_uid: int | None = None
        self.last_overall_frame_identifier: int = -1
        self.last_session_time: float | None = None

    def reset(self) -> None:
        self.session_uid = None
        self.last_overall_frame_identifier = -1
        self.last_session_time = None

    def evaluate(self, event: Mapping[str, object]) -> SessionDecision:
        session_uid = event.get("session_uid")
        overall_frame_identifier = event.get("overall_frame_identifier")
        session_time = event.get("session_time")

        if not isinstance(session_uid, int):
            raise ValueError("event.session_uid must be int")
        if not isinstance(overall_frame_identifier, int):
            raise ValueError("event.overall_frame_identifier must be int")
        if not isinstance(session_time, (int, float)):
            raise ValueError("event.session_time must be int|float")

        if self.session_uid is None:
            self.session_uid = session_uid
            self.last_overall_frame_identifier = overall_frame_identifier
            self.last_session_time = float(session_time)
            return SessionDecision(
                should_process=True,
                session_changed=True,
                out_of_order=False,
                session_uid=session_uid,
                overall_frame_identifier=overall_frame_identifier,
            )

        if session_uid != self.session_uid:
            self.session_uid = session_uid
            self.last_overall_frame_identifier = overall_frame_identifier
            self.last_session_time = float(session_time)
            return SessionDecision(
                should_process=True,
                session_changed=True,
                out_of_order=False,
                session_uid=session_uid,
                overall_frame_identifier=overall_frame_identifier,
            )

        if overall_frame_identifier <= self.last_overall_frame_identifier:
            return SessionDecision(
                should_process=False,
                session_changed=False,
                out_of_order=True,
                session_uid=session_uid,
                overall_frame_identifier=overall_frame_identifier,
            )

        self.last_overall_frame_identifier = overall_frame_identifier
        self.last_session_time = float(session_time)
        return SessionDecision(
            should_process=True,
            session_changed=False,
            out_of_order=False,
            session_uid=session_uid,
            overall_frame_identifier=overall_frame_identifier,
        )
