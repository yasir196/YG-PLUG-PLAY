"""Plugin registry, SHA-bound trust and effective availability."""

from __future__ import annotations

import json
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from core.database.models import (
    Channel,
    ChannelPluginAssignment,
    PluginTrustGrant,
    PluginVersion,
    User,
)
from core.plugin_registry.manifest import PluginManifest, PythonRuntime


class RegistryError(ValueError):
    pass


@dataclass(frozen=True)
class Availability:
    available: bool
    reasons: tuple[str, ...]


class PluginRegistry:
    def __init__(self, session: Session) -> None:
        self.session = session

    def _version(self, plugin_id: str, version: str, package_sha256: str) -> PluginVersion:
        item = self.session.scalar(
            select(PluginVersion).where(
                PluginVersion.plugin_id == plugin_id,
                PluginVersion.version == version,
                PluginVersion.package_sha256 == package_sha256,
            )
        )
        if item is None:
            raise RegistryError("installed package version not found")
        return item

    def _manifest(self, item: PluginVersion) -> PluginManifest:
        return PluginManifest.model_validate(json.loads(item.manifest_json))

    def grant_trust(
        self,
        plugin_id: str,
        version: str,
        package_sha256: str,
        *,
        actor_id: str,
        actor_is_admin: bool,
        trust_level: str = "trusted",
    ) -> PluginTrustGrant:
        if not actor_is_admin:
            raise RegistryError("admin required for trust grant")
        self._version(plugin_id, version, package_sha256)
        if self.session.get(User, actor_id) is None:
            raise RegistryError("granting admin user not found")
        existing = self.session.scalar(
            select(PluginTrustGrant).where(
                PluginTrustGrant.plugin_id == plugin_id,
                PluginTrustGrant.plugin_version == version,
                PluginTrustGrant.package_sha256 == package_sha256,
            )
        )
        if existing is not None:
            existing.trust_level = trust_level
            return existing
        grant = PluginTrustGrant(
            plugin_id=plugin_id,
            plugin_version=version,
            package_sha256=package_sha256,
            trust_level=trust_level,
            granted_by=actor_id,
        )
        self.session.add(grant)
        self.session.flush()
        return grant

    def has_executable_trust(self, item: PluginVersion) -> bool:
        manifest = self._manifest(item)
        if not isinstance(manifest.runtime, PythonRuntime):
            return True
        grant = self.session.scalar(
            select(PluginTrustGrant).where(
                PluginTrustGrant.plugin_id == item.plugin_id,
                PluginTrustGrant.plugin_version == item.version,
                PluginTrustGrant.package_sha256 == item.package_sha256,
                PluginTrustGrant.trust_level == "trusted",
            )
        )
        return grant is not None

    def platform_enable(self, plugin_id: str, version: str, package_sha256: str) -> PluginVersion:
        item = self._version(plugin_id, version, package_sha256)
        if not self.has_executable_trust(item):
            raise RegistryError("executable plugin requires SHA-bound trusted-code grant")
        # v0 has no separate platform-enable column: successful eligibility is the
        # platform-enable gate; Channel assignment remains disabled until requested.
        return item

    def compatible_with_channel(self, item: PluginVersion, channel: Channel) -> bool:
        manifest = self._manifest(item)
        if channel.niche_id is None:
            return "*" in manifest.compatible_niches
        for compatibility in manifest.compatible_niches:
            if isinstance(compatibility, str):
                if compatibility == "*":
                    return True
                continue
            if compatibility.id == channel.niche_id and self._version_matches(
                channel.niche_version or "", compatibility.version
            ):
                return True
        return False

    def assign(
        self,
        channel_id: str,
        plugin_id: str,
        version: str,
        package_sha256: str,
        *,
        enabled: bool = False,
    ) -> ChannelPluginAssignment:
        channel = self.session.get(Channel, channel_id)
        if channel is None:
            raise RegistryError("channel not found")
        item = self.platform_enable(plugin_id, version, package_sha256)
        if not self.compatible_with_channel(item, channel):
            raise RegistryError("plugin is incompatible with Channel niche pin")
        assignment = self.session.scalar(
            select(ChannelPluginAssignment).where(
                ChannelPluginAssignment.channel_id == channel_id,
                ChannelPluginAssignment.plugin_id == plugin_id,
            )
        )
        if assignment is None:
            assignment = ChannelPluginAssignment(
                channel_id=channel_id,
                plugin_id=plugin_id,
                plugin_version=version,
                enabled=enabled,
            )
            self.session.add(assignment)
        else:
            assignment.plugin_version = version
            assignment.enabled = enabled
        self.session.flush()
        return assignment

    def effective_availability(
        self,
        channel_id: str,
        plugin_id: str,
        version: str,
        package_sha256: str,
    ) -> Availability:
        reasons: list[str] = []
        try:
            item = self._version(plugin_id, version, package_sha256)
        except RegistryError:
            return Availability(False, ("package-not-installed",))
        channel = self.session.get(Channel, channel_id)
        if channel is None:
            return Availability(False, ("channel-not-found",))
        if not self.has_executable_trust(item):
            reasons.append("trust-missing")
        if not self.compatible_with_channel(item, channel):
            reasons.append("niche-incompatible")
        assignment = self.session.scalar(
            select(ChannelPluginAssignment).where(
                ChannelPluginAssignment.channel_id == channel_id,
                ChannelPluginAssignment.plugin_id == plugin_id,
                ChannelPluginAssignment.plugin_version == version,
            )
        )
        if assignment is None:
            reasons.append("not-assigned")
        elif not assignment.enabled:
            reasons.append("channel-disabled")
        return Availability(not reasons, tuple(reasons))

    @staticmethod
    def _version_matches(pinned: str, requirement: str) -> bool:
        if requirement == "*":
            return True
        if requirement.startswith("^"):
            wanted = requirement[1:].split(".")
            actual = pinned.split(".")
            return actual[: len(wanted)] == wanted
        return pinned == requirement
