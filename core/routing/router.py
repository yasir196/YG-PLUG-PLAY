"""Purpose-aware Channel router with provider eligibility validation."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from core.database.models import ChannelRoute, PluginSetting, PluginVersion
from core.plugin_registry.manifest import PluginManifest
from core.plugin_registry.registry import PluginRegistry


class RouteError(ValueError):
    pass


@dataclass(frozen=True)
class ResolvedRoute:
    route_id: int
    plugin_id: str
    plugin_version: str
    package_sha256: str
    model: str | None
    options: dict[str, Any]


class PurposeRouter:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.plugins = PluginRegistry(session)

    def resolve(
        self,
        *,
        channel_id: str,
        capability: str,
        purpose: str | None = None,
        variant: str | None = None,
        required_features: dict[str, Any] | None = None,
        input_contract: str | None = None,
        output_contract: str | None = None,
        explicit_options: dict[str, Any] | None = None,
    ) -> ResolvedRoute:
        routes = list(
            self.session.scalars(
                select(ChannelRoute).where(
                    ChannelRoute.channel_id == channel_id,
                    ChannelRoute.capability == capability,
                )
            )
        )
        route = self._select(routes, purpose, variant)
        if route is None:
            raise RouteError("route missing")
        version = self._assigned_version(channel_id, route.primary_plugin_id)
        item = self.session.scalar(
            select(PluginVersion)
            .where(
                PluginVersion.plugin_id == route.primary_plugin_id,
                PluginVersion.version == version,
            )
            .order_by(PluginVersion.id.desc())
        )
        if item is None:
            raise RouteError("provider package is not installed")
        availability = self.plugins.effective_availability(
            channel_id, item.plugin_id, item.version, item.package_sha256
        )
        if not availability.available:
            raise RouteError("provider unavailable: " + ",".join(availability.reasons))
        manifest = PluginManifest.model_validate(json.loads(item.manifest_json))
        provided = next((p for p in manifest.provides if p.capability == capability), None)
        if provided is None:
            raise RouteError("provider does not supply routed capability")
        self._validate_contracts(provided, input_contract, output_contract)
        self._validate_features(provided.features or {}, required_features or {})
        defaults = self._plugin_defaults(manifest)
        channel_settings = self._channel_settings(channel_id, item.plugin_id)
        route_options = json.loads(route.options_json or "{}")
        options = defaults | channel_settings | route_options | (explicit_options or {})
        return ResolvedRoute(
            route_id=route.id,
            plugin_id=item.plugin_id,
            plugin_version=item.version,
            package_sha256=item.package_sha256,
            model=options.get("model"),
            options=options,
        )

    @staticmethod
    def _select(routes, purpose: str | None, variant: str | None):
        if purpose is not None:
            found = next((r for r in routes if r.purpose == purpose), None)
            if found is not None:
                return found
        if variant is not None:
            found = next(
                (r for r in routes if r.purpose is None and r.variant == variant), None
            )
            if found is not None:
                return found
        return next((r for r in routes if r.purpose is None and r.variant is None), None)

    def _assigned_version(self, channel_id: str, plugin_id: str) -> str:
        from core.database.models import ChannelPluginAssignment

        assignment = self.session.scalar(
            select(ChannelPluginAssignment).where(
                ChannelPluginAssignment.channel_id == channel_id,
                ChannelPluginAssignment.plugin_id == plugin_id,
                ChannelPluginAssignment.enabled.is_(True),
            )
        )
        if assignment is None:
            raise RouteError("provider is not enabled for Channel")
        return assignment.plugin_version

    def _channel_settings(self, channel_id: str, plugin_id: str) -> dict[str, Any]:
        rows = self.session.scalars(
            select(PluginSetting).where(
                PluginSetting.plugin_id == plugin_id,
                PluginSetting.scope == "channel",
                PluginSetting.scope_id == channel_id,
            )
        )
        return {row.key: json.loads(row.value_json) for row in rows}

    @staticmethod
    def _plugin_defaults(manifest: PluginManifest) -> dict[str, Any]:
        # Manifest v0 has no arbitrary defaults object; capability feature defaults
        # are therefore empty until a settings schema/default resource supplies them.
        return {}

    @staticmethod
    def _validate_contracts(provided, wanted_in: str | None, wanted_out: str | None) -> None:
        if wanted_in is not None and provided.input.contract != wanted_in:
            raise RouteError("input contract incompatible")
        if wanted_out is not None and provided.output.contract != wanted_out:
            raise RouteError("output contract incompatible")

    @staticmethod
    def _validate_features(supported: Any, required: dict[str, Any]) -> None:
        data = supported.model_dump(exclude_none=True) if hasattr(supported, "model_dump") else dict(supported)
        for key, wanted in required.items():
            actual = data.get(key)
            if isinstance(wanted, bool) and wanted and actual is not True:
                raise RouteError(f"required feature unsupported: {key}")
            if key == "max_context_tokens" and actual is not None and actual < wanted:
                raise RouteError("required context window unsupported")
