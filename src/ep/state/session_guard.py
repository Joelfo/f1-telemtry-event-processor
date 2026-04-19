from __future__ import annotations


class SessionGuard:
    def __init__(self) -> None:
        self.session_uid: int | None = None
        self.last_overall_frame_identifier: int = -1
