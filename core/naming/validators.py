"""V5 §3 canonical public-name validation.

Syntax and platform reservation are deliberately separate concerns internally,
but public validators enforce both. Reserved event namespaces are valid only
when the caller explicitly identifies Core as the emitter.
"""

from __future__ import annotations

import re
from collections.abc import Callable

PLUGIN_NICHE_PATTERN = re.compile(r"^[a-z][a-z0-9]*(?:-[a-z0-9]+)*$")
CAPABILITY_PATTERN = re.compile(
    r"^(?:[a-z][a-z0-9]*(?:-[a-z0-9]+)*/)?[a-z][a-z0-9]*(?:-[a-z0-9]+)*$"
)
CONTRACT_PATTERN = re.compile(
    r"^(?:[a-z][a-z0-9]*(?:-[a-z0-9]+)*/)?"
    r"[a-z][a-z0-9]*(?:-[a-z0-9]+)*(?:\.[a-z][a-z0-9]*(?:-[a-z0-9]+)*)*$"
)
EVENT_PATTERN = re.compile(r"^[a-z][a-z0-9]*(?:-[a-z0-9]+)*(?:\.[a-z][a-z0-9]*(?:-[a-z0-9]+)*)+$")

RESERVED_IDS = frozenset({"core", "system", "project", "channel", "yg"})
RESERVED_EVENT_NAMESPACES = frozenset({"core", "system", "project", "channel"})
RESERVED_FIRST_PARTY_PREFIX = "yg-"


class NamingError(ValueError):
    """Raised when a public identifier violates V5 naming rules."""


def _reject_reserved_id(value: str) -> None:
    if value in RESERVED_IDS or value.startswith(RESERVED_FIRST_PARTY_PREFIX):
        raise NamingError(f"{value!r} is reserved by the platform")


def _validate_regex(value: str, pattern: re.Pattern[str], kind: str) -> None:
    if pattern.fullmatch(value) is None:
        raise NamingError(f"invalid {kind}: {value!r}")


def validate_plugin_id(value: str) -> str:
    _validate_regex(value, PLUGIN_NICHE_PATTERN, "plugin ID")
    _reject_reserved_id(value)
    return value


def validate_niche_id(value: str) -> str:
    _validate_regex(value, PLUGIN_NICHE_PATTERN, "niche ID")
    _reject_reserved_id(value)
    return value


def _owner_namespace(value: str) -> str | None:
    return value.split("/", 1)[0] if "/" in value else None


def _reject_reserved_owner_namespace(value: str) -> None:
    owner = _owner_namespace(value)
    if owner is not None and (
        owner in RESERVED_IDS or owner.startswith(RESERVED_FIRST_PARTY_PREFIX)
    ):
        raise NamingError(f"namespace {owner!r} is reserved by the platform")


def validate_capability_id(value: str, *, allow_reserved_namespace: bool = False) -> str:
    _validate_regex(value, CAPABILITY_PATTERN, "capability ID")
    if not allow_reserved_namespace:
        _reject_reserved_owner_namespace(value)
    return value


def validate_contract_id(value: str, *, allow_reserved_namespace: bool = False) -> str:
    _validate_regex(value, CONTRACT_PATTERN, "contract ID")
    if not allow_reserved_namespace:
        _reject_reserved_owner_namespace(value)
    return value


def validate_event_id(value: str, *, core_emitter: bool = False) -> str:
    _validate_regex(value, EVENT_PATTERN, "event ID")
    namespace = value.split(".", 1)[0]
    if namespace in RESERVED_EVENT_NAMESPACES and not core_emitter:
        raise NamingError(f"event namespace {namespace!r} is Core-only")
    if namespace == "yg" or namespace.startswith(RESERVED_FIRST_PARTY_PREFIX):
        raise NamingError(f"event namespace {namespace!r} is reserved by the platform")
    return value


def _is_valid(validator: Callable[..., str], value: str, **kwargs: bool) -> bool:
    try:
        validator(value, **kwargs)
    except NamingError:
        return False
    return True


def is_valid_plugin_id(value: str) -> bool:
    return _is_valid(validate_plugin_id, value)


def is_valid_niche_id(value: str) -> bool:
    return _is_valid(validate_niche_id, value)


def is_valid_capability_id(value: str, *, allow_reserved_namespace: bool = False) -> bool:
    return _is_valid(
        validate_capability_id, value, allow_reserved_namespace=allow_reserved_namespace
    )


def is_valid_contract_id(value: str, *, allow_reserved_namespace: bool = False) -> bool:
    return _is_valid(validate_contract_id, value, allow_reserved_namespace=allow_reserved_namespace)


def is_valid_event_id(value: str, *, core_emitter: bool = False) -> bool:
    return _is_valid(validate_event_id, value, core_emitter=core_emitter)
