"""Channel package identity primitives shared by routing and run snapshots."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from core.database.models import ChannelPluginAssignment, PluginVersion


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
