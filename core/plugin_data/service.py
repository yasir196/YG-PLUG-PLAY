"""Channel-isolated plugin key/value storage."""

from __future__ import annotations

import json
import os
import re
import tempfile
from pathlib import Path
from typing import Any

from core.plugin_runtime.permissions import ExecutionContext

_SAFE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9._-]{0,127}$")


class PluginDataError(ValueError):
    pass


class PluginDataService:
    def __init__(self, root: Path) -> None:
        self.root = root.resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def get(self, context: ExecutionContext, key: str, default: Any = None) -> Any:
        path = self._path(context, key)
        if not path.exists():
            return default
        return json.loads(path.read_text(encoding="utf-8"))

    def set(self, context: ExecutionContext, key: str, value: Any) -> None:
        path = self._path(context, key)
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
        fd, temp_name = tempfile.mkstemp(prefix=".write-", dir=path.parent)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as stream:
                stream.write(payload)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temp_name, path)
        finally:
            Path(temp_name).unlink(missing_ok=True)

    def delete(self, context: ExecutionContext, key: str) -> bool:
        path = self._path(context, key)
        if not path.exists():
            return False
        path.unlink()
        return True

    def list_keys(self, context: ExecutionContext) -> tuple[str, ...]:
        base = self._scope(context)
        if not base.exists():
            return ()
        return tuple(sorted(path.stem for path in base.glob("*.json") if path.is_file()))

    def rpc_handlers(self):
        return {
            "plugin-data.read": lambda ctx, params: self.get(ctx, str(params["key"])),
            "plugin-data.write": lambda ctx, params: self._rpc_write(ctx, params),
        }

    def _rpc_write(self, context: ExecutionContext, params: dict[str, Any]) -> bool:
        self.set(context, str(params["key"]), params.get("value"))
        return True

    def _scope(self, context: ExecutionContext) -> Path:
        # The caller never supplies these path components; they come only from the
        # immutable Core execution context.
        for value in (context.plugin_id, context.plugin_version, context.channel_id):
            if not _SAFE.fullmatch(value):
                raise PluginDataError("unsafe plugin-data identity")
        path = (
            self.root
            / context.plugin_id
            / context.plugin_version
            / context.channel_id
        ).resolve()
        if not path.is_relative_to(self.root):
            raise PluginDataError("plugin-data scope escapes root")
        return path

    def _path(self, context: ExecutionContext, key: str) -> Path:
        if not _SAFE.fullmatch(key):
            raise PluginDataError("unsafe plugin-data key")
        base = self._scope(context)
        path = (base / f"{key}.json").resolve()
        if not path.is_relative_to(base):
            raise PluginDataError("plugin-data key escapes scope")
        return path
