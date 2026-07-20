"""Instance-level settings for metaseed, persisted as a small JSON file.

Currently holds the per-adapter enable/disable feature switch. Follows the same
JSON-under-the-user-data-dir pattern as ``FilesystemDatasetRepository``: only
explicit overrides are stored, so an adapter with no stored value falls back to
its default (enabled when its pip extra is installed).
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

from metaseed import adapters
from metaseed.paths import get_user_config_path

if TYPE_CHECKING:
    from pathlib import Path


class Settings:
    """Read/write instance settings backed by a JSON file.

    The file is created lazily on the first write. Unknown adapter keys are
    rejected so a caller cannot persist arbitrary data (and keys are never used
    as filesystem paths).
    """

    def __init__(self, path: Path | None = None) -> None:
        """Initialize the store.

        Args:
            path: Settings file path; defaults to :func:`get_user_config_path`.
        """
        self._path = path or get_user_config_path()
        self._data = self._load()

    def _load(self) -> dict[str, Any]:
        if not self._path.exists():
            return {}
        try:
            loaded = json.loads(self._path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}
        return loaded if isinstance(loaded, dict) else {}

    def _save(self) -> None:
        # Write atomically: a crash mid-write must not corrupt settings.json.
        self._path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self._path.with_name(self._path.name + ".tmp")
        tmp.write_text(
            json.dumps(self._data, indent=2, sort_keys=True), encoding="utf-8"
        )
        tmp.replace(self._path)

    def adapter_enabled(self, key: str) -> bool:
        """Return whether adapter ``key`` is enabled *and usable*.

        An adapter is enabled when its pip extra is installed AND it is not
        explicitly disabled (default is enabled-when-available). A stored ``True``
        for an adapter whose extra is no longer installed still reads as disabled,
        so callers can trust this without a separate availability check.
        """
        if not adapters.is_known(key):
            return False
        if not adapters.is_available(adapters.get_adapter(key)):
            return False
        override = self._data.get("adapters", {}).get(key)
        if isinstance(override, bool):
            return override
        return True

    def set_adapter_enabled(self, key: str, enabled: bool) -> None:
        """Persist an enable/disable choice for adapter ``key``.

        Raises:
            KeyError: If ``key`` is not a registered adapter.
            ValueError: If enabling an adapter whose extra is not installed.
        """
        info = adapters.get_adapter(key)  # raises KeyError for unknown keys
        if enabled and not adapters.is_available(info):
            raise ValueError(
                f"cannot enable {key!r}: install it with 'pip install metaseed[{info.extra}]'"
            )
        self._data.setdefault("adapters", {})[key] = enabled
        self._save()
