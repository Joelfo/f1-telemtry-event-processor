from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Counters:
    messages_in: int = 0
    messages_out: int = 0
    dropped_invalid: int = 0
    dropped_out_of_order: int = 0
    session_resets: int = 0
