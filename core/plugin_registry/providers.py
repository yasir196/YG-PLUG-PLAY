"""Channel package identity primitives shared by routing and run snapshots."""

from __future__ import annotations

import json
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from core.database.models import Channel, ChannelPluginAssignment, PluginVersion
from core.plugin_registry.manifest import PluginManifest, ProvidedCapability


class ProviderResolutionError(ValueError):
    pass


@dataclass(frozen=True)
class CapabilityProvider:
    plugin_id: str
    version: str
    package_sha256: str
    provided: ProvidedCapability


def latest_package(session: Session, plugin_id: str, version: str) -> PluginVersion | None:
    # Single source of the "current package" rule: assignments pin a version only,
    # so the most recently installed package of that version is the live identity.
    return session.scalar(
        select(PluginVersion)
        .where(
            PluginVersion.plugin_id == plugin_id,
            PluginVersion.version == version,
        )
        .order_by(PluginVersion.id.desc())
    )


def current_provider_package(
    session: Session, channel_id: str, plugin_id: str
) -> PluginVersion | None:
    """Enabled Channel assignment resolved to its current package, or None."""
    assignment = session.scalar(
        select(ChannelPluginAssignment).where(
            ChannelPluginAssignment.channel_id == channel_id,
            ChannelPluginAssignment.plugin_id == plugin_id,
            ChannelPluginAssignment.enabled.is_(True),
        )
    )
    if assignment is None:
        return None
    return latest_package(session, plugin_id, assignment.plugin_version)


def _channel_packages(session: Session, channel: Channel) -> list[PluginVersion]:
    # Candidates: pinned niche package + enabled assignments, each resolved to its
    # current package. Deduplicated by identity and sorted so no DB/install order leaks.
    found: dict[tuple[str, str, str], PluginVersion] = {}

    def add(item: PluginVersion | None) -> None:
        if item is not None:
            found.setdefault((item.plugin_id, item.version, item.package_sha256), item)

    if channel.niche_id is not None and channel.niche_version is not None:
        add(latest_package(session, channel.niche_id, channel.niche_version))
    assignments = session.scalars(
        select(ChannelPluginAssignment).where(
            ChannelPluginAssignment.channel_id == channel.id,
            ChannelPluginAssignment.enabled.is_(True),
        )
    )
    for assignment in assignments:
        add(latest_package(session, assignment.plugin_id, assignment.plugin_version))
    return [found[key] for key in sorted(found)]


def resolve_capability_provider(
    session: Session, channel_id: str, capability: str
) -> CapabilityProvider:
    """Resolve the single package providing a capability for a Channel, or fail closed.

    Route selection (purpose/variant) and trust are not decided here; routing does that.
    """
    channel = session.get(Channel, channel_id)
    if channel is None:
        raise ProviderResolutionError("channel not found")
    matches: list[CapabilityProvider] = []
    for item in _channel_packages(session, channel):
        manifest = PluginManifest.model_validate(json.loads(item.manifest_json))
        declared = [p for p in manifest.provides if p.capability == capability]
        if len(declared) > 1:
            raise ProviderResolutionError(f"ambiguous capability declaration: {item.plugin_id}")
        if declared:
            matches.append(
                CapabilityProvider(item.plugin_id, item.version, item.package_sha256, declared[0])
            )
    if not matches:
        raise ProviderResolutionError("no capability provider")
    if len(matches) > 1:
        names = ", ".join(sorted(match.plugin_id for match in matches))
        raise ProviderResolutionError(f"ambiguous capability provider: {names}")
    return matches[0]
