from __future__ import annotations


class PatchEmitter:
    def build_patch(self, path: str, value: object, source_type: str) -> dict:
        return {"path": path, "value": value, "source_type": source_type}
