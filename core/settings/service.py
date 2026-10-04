"""Schema-driven plugin settings with scoped resolution and secret routing."""

from __future__ import annotations

import json
from typing import Any, cast

from jsonschema import Draft202012Validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from core.database.models import PluginSetting, Project
from core.secrets import SecretNotFound, SecretService

_MISSING = object()


class SettingsError(ValueError):
    pass


class SettingsService:
    def __init__(
        self,
        session: Session,
        secrets: SecretService,
        plugin_id: str,
        definition: dict[str, Any],
    ) -> None:
        self.session = session
        self.secrets = secrets
        self.plugin_id = plugin_id
        self.definition = definition
        self.schema_version = int(definition.get("version", 1))
        self.fields = {str(item["key"]): item for item in definition["fields"]}

    def set(self, key: str, value: Any, *, scope: str, scope_id: str | None = None) -> None:
        field = self._field(key)
        if scope not in field["allowed_scopes"]:
            raise SettingsError(f"{key} is not allowed at {scope} scope")
        if scope == "platform" and scope_id is not None:
            raise SettingsError("platform scope cannot have scope_id")
        if scope != "platform" and not scope_id:
            raise SettingsError(f"{scope} scope requires scope_id")
        self._validate_value(field, value)
        if field["type"] == "secret":
            channel_id = self._secret_channel_id(scope, scope_id)
            self.secrets.set(self._secret_name(key), str(value), channel_id=channel_id)
            return
        row = self.session.scalar(
            select(PluginSetting).where(
                PluginSetting.plugin_id == self.plugin_id,
                PluginSetting.scope == scope,
                PluginSetting.scope_id == scope_id,
                PluginSetting.key == key,
            )
        )
        payload = json.dumps(value, ensure_ascii=False)
        if row is None:
            row = PluginSetting(
                plugin_id=self.plugin_id,
                scope=scope,
                scope_id=scope_id,
                key=key,
                value_json=payload,
                settings_schema_version=self.schema_version,
            )
            self.session.add(row)
        else:
            row.value_json = payload
            row.settings_schema_version = self.schema_version
        self.session.flush()

    def resolve(
        self, key: str, *, project_id: str | None = None, channel_id: str | None = None
    ) -> Any:
        field = self._field(key)
        if project_id is not None:
            project = self.session.get(Project, project_id)
            if project is None:
                raise SettingsError("project not found")
            if channel_id is not None and project.channel_id != channel_id:
                raise SettingsError("project does not belong to Channel")
            channel_id = project.channel_id
        if field["type"] == "secret":
            try:
                return self.secrets.resolve(self._secret_name(key), channel_id=channel_id)
            except SecretNotFound:
                if "default" in field:
                    return field["default"]
                raise SettingsError(f"required secret setting {key} is unresolved") from None
        for scope, scope_id in (("project", project_id), ("channel", channel_id)):
            if scope_id is None:
                continue
            value = self._stored(key, scope, scope_id)
            if value is not _MISSING:
                return value
        value = self._stored(key, "platform", None)
        if value is not _MISSING:
            return value
        if "default" in field:
            return field["default"]
        if field.get("required", False):
            raise SettingsError(f"required setting {key} is unresolved")
        return None

    def resolve_all(
        self, *, project_id: str | None = None, channel_id: str | None = None
    ) -> dict[str, Any]:
        return {
            key: self.resolve(key, project_id=project_id, channel_id=channel_id)
            for key in self.fields
        }

    def _stored(self, key: str, scope: str, scope_id: str | None) -> Any:
        row = self.session.scalar(
            select(PluginSetting).where(
                PluginSetting.plugin_id == self.plugin_id,
                PluginSetting.scope == scope,
                PluginSetting.scope_id == scope_id,
                PluginSetting.key == key,
            )
        )
        return _MISSING if row is None else json.loads(row.value_json)

    def _field(self, key: str) -> dict[str, Any]:
        try:
            return cast(dict[str, Any], self.fields[key])
        except KeyError as exc:
            raise SettingsError(f"unknown setting: {key}") from exc

    def _secret_name(self, key: str) -> str:
        return f"plugin:{self.plugin_id}:{key}"

    def _secret_channel_id(self, scope: str, scope_id: str | None) -> str | None:
        if scope == "platform":
            return None
        if scope == "channel":
            return scope_id
        if scope == "project" and scope_id is not None:
            project = self.session.get(Project, scope_id)
            if project is None:
                raise SettingsError("project not found")
            return project.channel_id
        raise SettingsError("secret fields support platform/channel/project resolution only")

    @staticmethod
    def _validate_value(field: dict[str, Any], value: Any) -> None:
        kind = field["type"]
        schemas: dict[str, dict[str, Any]] = {
            "string": {"type": "string"},
            "secret": {"type": "string", "minLength": 1},
            "number": {"type": "number"},
            "bool": {"type": "boolean"},
        }
        if kind in ("select", "multiselect") and "options" in field:
            choices = [item["value"] for item in field["options"]]
            schemas[kind] = (
                {"enum": choices}
                if kind == "select"
                else {"type": "array", "uniqueItems": True, "items": {"enum": choices}}
            )
        schema = schemas.get(kind)
        if schema is not None:
            Draft202012Validator(schema).validate(value)
