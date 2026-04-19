from __future__ import annotations

from collections.abc import Mapping


class PatchEmitter:
    def build_patch(self, path: str, value: object, source_type: str) -> dict:
        if not path:
            raise ValueError("path is required")
        if not source_type:
            raise ValueError("source_type is required")
        return {"path": path, "value": value, "source_type": source_type}

    def patches_from_payload(
        self,
        *,
        base_path: str,
        payload: Mapping[str, object],
        source_type: str,
    ) -> list[dict]:
        if not base_path:
            raise ValueError("base_path is required")
        if not isinstance(payload, Mapping):
            raise TypeError("payload must be a mapping")

        patches: list[dict] = []
        for key, value in payload.items():
            path = f"{base_path}.{key}"
            patches.append(self.build_patch(path=path, value=value, source_type=source_type))
        return patches
