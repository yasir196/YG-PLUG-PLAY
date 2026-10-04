"""RPC authorization bound to an immutable worker execution context."""

from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Callable, Mapping


class RPCPermissionError(PermissionError):
    pass


BASELINE_GRANTS = frozenset(
    {
        "rpc.invoke",
        "execution.identity.read",
        "scratch.read",
        "scratch.write",
    }
)

RPC_GRANTS: Mapping[str, str] = MappingProxyType(
    {
        "artifact.read": "artifact.read",
        "artifact.write": "artifact.write",
        "plugin-data.read": "plugin-data.read",
        "plugin-data.write": "plugin-data.write",
        "settings.read": "settings.read",
        "events.emit": "events.emit",
        "events.listen": "events.listen",
        "provider.jobs": "provider.jobs",
        "job.progress": "rpc.invoke",
        "credential.raw": "credential.raw",
    }
)


@dataclass(frozen=True)
class ExecutionContext:
    plugin_id: str
    plugin_version: str
    channel_id: str
    package_sha256: str
    grants: frozenset[str]

    @classmethod
    def create(
        cls,
        *,
        plugin_id: str,
        plugin_version: str,
        channel_id: str,
        package_sha256: str,
        grants: set[str] | frozenset[str] = frozenset(),
    ) -> "ExecutionContext":
        return cls(
            plugin_id=plugin_id,
            plugin_version=plugin_version,
            channel_id=channel_id,
            package_sha256=package_sha256,
            grants=frozenset(grants) | BASELINE_GRANTS,
        )


Handler = Callable[[ExecutionContext, dict[str, Any]], Any]


class RPCPermissionLayer:
    def __init__(self, handlers: Mapping[str, Handler]) -> None:
        self._handlers = MappingProxyType(dict(handlers))

    def dispatch(
        self, context: ExecutionContext, method: str, params: dict[str, Any]
    ) -> Any:
        self._assert_identity(context, params)
        handler = self._handlers.get(method)
        if handler is None:
            raise RPCPermissionError("RPC method is not allowlisted")
        required = RPC_GRANTS.get(method)
        if required is None:
            if method not in BASELINE_GRANTS:
                raise RPCPermissionError("RPC method has no permission mapping")
        elif required not in context.grants:
            raise RPCPermissionError(f"missing RPC grant: {required}")
        return handler(context, params)

    @staticmethod
    def _assert_identity(context: ExecutionContext, params: dict[str, Any]) -> None:
        requested_channel = params.get("channel_id")
        if requested_channel is not None and requested_channel != context.channel_id:
            raise RPCPermissionError("worker cannot switch channel_id")
        requested_plugin = params.get("plugin_id")
        if requested_plugin is not None and requested_plugin != context.plugin_id:
            raise RPCPermissionError("worker cannot switch plugin identity")
        requested_version = params.get("plugin_version")
        if requested_version is not None and requested_version != context.plugin_version:
            raise RPCPermissionError("worker cannot switch plugin version")
