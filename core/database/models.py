"""Phase-1a Core persistence model.

The model intentionally stores versioned/configuration payloads as JSON text in v0.
Secrets store ciphertext only; trust is bound to exact package identity.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class TimestampMixin:
    created_at: Mapped[str] = mapped_column(String(40), default=lambda: datetime.utcnow().isoformat())


class User(TimestampMixin, Base):
    __tablename__ = "users"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    username: Mapped[str] = mapped_column(String(200), unique=True)


class Session(TimestampMixin, Base):
    __tablename__ = "sessions"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    expires_at: Mapped[str] = mapped_column(String(40))


class Niche(TimestampMixin, Base):
    __tablename__ = "niches"
    id: Mapped[str] = mapped_column(String(128), primary_key=True)
    version: Mapped[str] = mapped_column(String(64))


class Channel(TimestampMixin, Base):
    __tablename__ = "channels"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    niche_id: Mapped[str | None] = mapped_column(ForeignKey("niches.id"), nullable=True)
    niche_version: Mapped[str | None] = mapped_column(String(64), nullable=True)


class Project(TimestampMixin, Base):
    __tablename__ = "projects"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    channel_id: Mapped[str] = mapped_column(ForeignKey("channels.id"))
    title: Mapped[str] = mapped_column(String(500))
    status: Mapped[str] = mapped_column(String(40), default="active")


class ProjectBrief(TimestampMixin, Base):
    __tablename__ = "project_briefs"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"))
    generation: Mapped[int] = mapped_column(Integer, default=1)
    contract_version: Mapped[str] = mapped_column(String(64), default="1.0.0")
    data_json: Mapped[str] = mapped_column(Text)
    __table_args__ = (UniqueConstraint("project_id", "generation"),)


class Plugin(TimestampMixin, Base):
    __tablename__ = "plugins"
    id: Mapped[str] = mapped_column(String(128), primary_key=True)
    kind: Mapped[str] = mapped_column(String(40), default="plugin")


class PluginVersion(TimestampMixin, Base):
    __tablename__ = "plugin_versions"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    plugin_id: Mapped[str] = mapped_column(ForeignKey("plugins.id"))
    version: Mapped[str] = mapped_column(String(64))
    package_sha256: Mapped[str] = mapped_column(String(64))
    manifest_json: Mapped[str] = mapped_column(Text)
    __table_args__ = (UniqueConstraint("plugin_id", "version", "package_sha256"),)


class PluginTrustGrant(TimestampMixin, Base):
    __tablename__ = "plugin_trust_grants"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    plugin_id: Mapped[str] = mapped_column(ForeignKey("plugins.id"))
    plugin_version: Mapped[str] = mapped_column(String(64))
    package_sha256: Mapped[str] = mapped_column(String(64))
    trust_level: Mapped[str] = mapped_column(String(40))
    granted_by: Mapped[str] = mapped_column(ForeignKey("users.id"))
    __table_args__ = (UniqueConstraint("plugin_id", "plugin_version", "package_sha256"),)


class ChannelPluginAssignment(TimestampMixin, Base):
    __tablename__ = "channel_plugin_assignments"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    channel_id: Mapped[str] = mapped_column(ForeignKey("channels.id"))
    plugin_id: Mapped[str] = mapped_column(ForeignKey("plugins.id"))
    plugin_version: Mapped[str] = mapped_column(String(64))
    enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    __table_args__ = (UniqueConstraint("channel_id", "plugin_id"),)


class PluginSetting(TimestampMixin, Base):
    __tablename__ = "plugin_settings"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    plugin_id: Mapped[str] = mapped_column(ForeignKey("plugins.id"))
    scope: Mapped[str] = mapped_column(String(40))
    scope_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    key: Mapped[str] = mapped_column(String(200))
    value_json: Mapped[str] = mapped_column(Text)
    settings_schema_version: Mapped[int] = mapped_column(Integer, default=1)


class EncryptedSecret(TimestampMixin, Base):
    __tablename__ = "encrypted_secrets"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    channel_id: Mapped[str | None] = mapped_column(ForeignKey("channels.id"), nullable=True)
    name: Mapped[str] = mapped_column(String(200))
    ciphertext: Mapped[str] = mapped_column(Text)


class Capability(TimestampMixin, Base):
    __tablename__ = "capabilities"
    id: Mapped[str] = mapped_column(String(200), primary_key=True)
    version: Mapped[str] = mapped_column(String(64))
    schema_json: Mapped[str] = mapped_column(Text)


class Contract(TimestampMixin, Base):
    __tablename__ = "contracts"
    id: Mapped[str] = mapped_column(String(200), primary_key=True)
    version: Mapped[str] = mapped_column(String(64))
    schema_json: Mapped[str] = mapped_column(Text)


class NamespaceRegistry(TimestampMixin, Base):
    __tablename__ = "namespace_registry"
    namespace: Mapped[str] = mapped_column(String(128), primary_key=True)
    owner_type: Mapped[str] = mapped_column(String(40))
    owner_id: Mapped[str] = mapped_column(String(128))


class Workflow(TimestampMixin, Base):
    __tablename__ = "workflows"
    id: Mapped[str] = mapped_column(String(128), primary_key=True)
    name: Mapped[str] = mapped_column(String(200))


class WorkflowVersion(TimestampMixin, Base):
    __tablename__ = "workflow_versions"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    workflow_id: Mapped[str] = mapped_column(ForeignKey("workflows.id"))
    version: Mapped[int] = mapped_column(Integer)
    definition_json: Mapped[str] = mapped_column(Text)
    __table_args__ = (UniqueConstraint("workflow_id", "version"),)


class ChannelRoute(TimestampMixin, Base):
    __tablename__ = "channel_routes"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    channel_id: Mapped[str] = mapped_column(ForeignKey("channels.id"))
    capability: Mapped[str] = mapped_column(String(200))
    purpose: Mapped[str | None] = mapped_column(String(200), nullable=True)
    variant: Mapped[str | None] = mapped_column(String(128), nullable=True)
    primary_plugin_id: Mapped[str] = mapped_column(ForeignKey("plugins.id"))
    options_json: Mapped[str] = mapped_column(Text, default="{}")


class WorkflowRun(TimestampMixin, Base):
    __tablename__ = "workflow_runs"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"))
    workflow_version_id: Mapped[int] = mapped_column(ForeignKey("workflow_versions.id"))
    status: Mapped[str] = mapped_column(String(40), default="pending")
    mode: Mapped[str] = mapped_column(String(20), default="live")
    current_node_id: Mapped[str | None] = mapped_column(String(128), nullable=True)


class RunSnapshot(TimestampMixin, Base):
    __tablename__ = "run_snapshots"
    run_id: Mapped[str] = mapped_column(ForeignKey("workflow_runs.id"), primary_key=True)
    snapshot_json: Mapped[str] = mapped_column(Text)


class WorkflowNodeRun(TimestampMixin, Base):
    __tablename__ = "workflow_node_runs"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("workflow_runs.id"))
    node_id: Mapped[str] = mapped_column(String(128))
    attempt: Mapped[int] = mapped_column(Integer, default=1)
    status: Mapped[str] = mapped_column(String(40), default="pending")
    provider_plugin_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    model: Mapped[str | None] = mapped_column(String(200), nullable=True)
    options_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    __table_args__ = (UniqueConstraint("run_id", "node_id", "attempt"),)


class ApprovalQueue(TimestampMixin, Base):
    __tablename__ = "approval_queue"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("workflow_runs.id"))
    node_id: Mapped[str] = mapped_column(String(128))
    status: Mapped[str] = mapped_column(String(40), default="waiting")
    artifact_generation_id: Mapped[int | None] = mapped_column(Integer, nullable=True)


class ApprovalDecision(TimestampMixin, Base):
    __tablename__ = "approval_decisions"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    approval_queue_id: Mapped[int] = mapped_column(ForeignKey("approval_queue.id"))
    action: Mapped[str] = mapped_column(String(80))
    actor_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    target_artifact_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    target_generation: Mapped[int | None] = mapped_column(Integer, nullable=True)
    feedback: Mapped[str | None] = mapped_column(Text, nullable=True)


class Artifact(TimestampMixin, Base):
    __tablename__ = "artifacts"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("workflow_runs.id"))
    contract_id: Mapped[str] = mapped_column(String(200))
    logical_name: Mapped[str] = mapped_column(String(200))


class ArtifactGeneration(TimestampMixin, Base):
    __tablename__ = "artifact_generations"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    artifact_id: Mapped[str] = mapped_column(ForeignKey("artifacts.id"))
    generation: Mapped[int] = mapped_column(Integer)
    actor: Mapped[str] = mapped_column(String(80))
    content_path: Mapped[str] = mapped_column(Text)
    sha256: Mapped[str] = mapped_column(String(64))
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")
    __table_args__ = (UniqueConstraint("artifact_id", "generation"),)


class Job(TimestampMixin, Base):
    __tablename__ = "jobs"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    run_id: Mapped[str | None] = mapped_column(ForeignKey("workflow_runs.id"), nullable=True)
    kind: Mapped[str] = mapped_column(String(80))
    status: Mapped[str] = mapped_column(String(40), default="pending")
    payload_json: Mapped[str] = mapped_column(Text, default="{}")


class AuditLog(TimestampMixin, Base):
    __tablename__ = "audit_log"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    actor_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    action: Mapped[str] = mapped_column(String(200))
    entity_type: Mapped[str] = mapped_column(String(100))
    entity_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    details_json: Mapped[str] = mapped_column(Text, default="{}")
