from __future__ import annotations

from collections.abc import Callable

import pytest

from core.naming import (
    is_valid_capability_id,
    is_valid_contract_id,
    is_valid_event_id,
    is_valid_niche_id,
    is_valid_plugin_id,
)

Validator = Callable[[str], bool]


@pytest.mark.parametrize(
    ("validator", "value"),
    [
        # V5 §3.1 official valid Plugin/Niche examples.
        (is_valid_plugin_id, "claude"),
        (is_valid_plugin_id, "senior-health"),
        (is_valid_plugin_id, "capcut-export"),
        (is_valid_niche_id, "claude"),
        (is_valid_niche_id, "senior-health"),
        (is_valid_niche_id, "capcut-export"),
        # V5 §3.2 official capability examples.
        (is_valid_capability_id, "text-generation"),
        (is_valid_capability_id, "deep-research"),
        (is_valid_capability_id, "script-generation"),
        (is_valid_capability_id, "image-generation"),
        (is_valid_capability_id, "senior-health/medical-review"),
        # V5 §3.3 official contract examples.
        (is_valid_contract_id, "project.brief"),
        (is_valid_contract_id, "voice.request"),
        (is_valid_contract_id, "audio.asset"),
        (is_valid_contract_id, "image.request.collection"),
        (is_valid_contract_id, "senior-health/medical-review"),
        (is_valid_contract_id, "video.performance"),
        (is_valid_contract_id, "script"),
        # V5 §3.4 non-reserved official event example.
        (is_valid_event_id, "elevenlabs.voice-completed"),
    ],
)
def test_official_v5_examples_pass(validator: Validator, value: str) -> None:
    assert validator(value)


@pytest.mark.parametrize(
    "value",
    ["core.run-started", "project.published"],
)
def test_official_reserved_event_examples_pass_for_core(value: str) -> None:
    assert is_valid_event_id(value, core_emitter=True)


@pytest.mark.parametrize(
    ("validator", "value"),
    [
        # Official §3.1 invalid examples.
        (is_valid_plugin_id, "SeniorHealth"),
        (is_valid_plugin_id, "senior_health"),
        (is_valid_plugin_id, "project.brief"),
        # Generic malformed names.
        (is_valid_plugin_id, "bad_name"),
        (is_valid_niche_id, "Bad-Niche"),
        (is_valid_capability_id, "script_generation"),
        (is_valid_capability_id, "Senior-health/medical-review"),
        (is_valid_contract_id, "Voice.request"),
        (is_valid_contract_id, "voice_request"),
        (is_valid_event_id, "voice_completed"),
        (is_valid_event_id, "Voice.completed"),
        # Reserved IDs / yg-*.
        (is_valid_plugin_id, "core"),
        (is_valid_plugin_id, "system"),
        (is_valid_plugin_id, "project"),
        (is_valid_plugin_id, "channel"),
        (is_valid_plugin_id, "yg"),
        (is_valid_plugin_id, "yg-provider"),
        (is_valid_niche_id, "yg-senior-health"),
        # Reserved owner namespaces.
        (is_valid_capability_id, "core/run-started"),
        (is_valid_capability_id, "yg/text-generation"),
        (is_valid_capability_id, "yg-standard-contracts/text-generation"),
        (is_valid_contract_id, "system/audit.record"),
        (is_valid_contract_id, "yg-standard-contracts/project.brief"),
        # Reserved event namespaces are Core-only; yg-* is first-party-only.
        (is_valid_event_id, "core.run-started"),
        (is_valid_event_id, "system.started"),
        (is_valid_event_id, "project.published"),
        (is_valid_event_id, "channel.updated"),
        (is_valid_event_id, "yg-platform.started"),
    ],
)
def test_invalid_or_reserved_public_names_fail(validator: Validator, value: str) -> None:
    assert not validator(value)


@pytest.mark.parametrize(
    ("validator", "value"),
    [
        (lambda value: is_valid_capability_id(value, allow_reserved_namespace=True), "yg/text-generation"),
        (
            lambda value: is_valid_contract_id(value, allow_reserved_namespace=True),
            "yg-standard-contracts/project.brief",
        ),
    ],
)
def test_platform_can_explicitly_use_reserved_owner_namespaces(
    validator: Validator, value: str
) -> None:
    assert validator(value)
