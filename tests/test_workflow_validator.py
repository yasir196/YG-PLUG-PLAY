from __future__ import annotations

from copy import deepcopy
from typing import Any

import pytest

from core.workflow import WorkflowValidationError, validate_workflow
import importlib.util
from pathlib import Path

_fixture_path = Path(__file__).parent / "schemas" / "test_workflow_schema.py"
_spec = importlib.util.spec_from_file_location("workflow_schema_fixture", _fixture_path)
assert _spec is not None and _spec.loader is not None
_fixture_module = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_fixture_module)
corrected_v5_workflow = _fixture_module.corrected_v5_workflow


def node(workflow: dict[str, Any], node_id: str) -> dict[str, Any]:
    return next(item for item in workflow["nodes"] if item["id"] == node_id)


def duplicate_id(w: dict[str, Any]) -> None:
    node(w, "end-rejected")["id"] = "end-success"


def unreachable_node(w: dict[str, Any]) -> None:
    w["nodes"].append({"id": "orphan", "type": "end", "status": "failed"})


def dangling_from(w: dict[str, Any]) -> None:
    node(w, "timeline")["inputs"]["audio"]["from"] = "missing.audio"


def unbounded_cycle(w: dict[str, Any]) -> None:
    n = node(w, "timeline")
    n["next"] = "timeline"


def missing_on_exhausted(w: dict[str, Any]) -> None:
    node(w, "revision")["loop_control"]["on_exhausted"] = "missing-review"


def missing_approval_target(w: dict[str, Any]) -> None:
    node(w, "final-approval")["approval"]["actions"]["reject"] = "missing-end"


def incompatible_latest_contract(w: dict[str, Any]) -> None:
    node(w, "revision")["outputs"]["script"]["contract"] = "research"


def required_input_missing_on_branch(w: dict[str, Any]) -> None:
    # Both branches can reach media-join, but only generate-images produces images.
    join = node(w, "media-join")
    join["next"] = "branch-consumer"
    w["nodes"].append(
        {
            "id": "branch-consumer",
            "type": "capability",
            "capability": "timeline-build",
            "inputs": {"images": {"from": "generate-images.images"}},
            "outputs": {"timeline": {"contract": "timeline", "version": "^1.0"}},
            "next": "timeline",
        }
    )


def old_v4_manual_review_bug(w: dict[str, Any]) -> None:
    # Old bug: manual review routes straight to media planning while media planning
    # requires the final-approval output lineage, which that path never produces.
    manual = node(w, "manual-review")
    manual["outputs"] = {}
    manual["approval"]["actions"]["approve"] = "media-planning"
    media = node(w, "media-planning")
    media["inputs"]["script"] = {"from": "final-approval.approved-script"}


def producer_after_consumer(w: dict[str, Any]) -> None:
    node(w, "timeline")["inputs"]["audio"] = {"from": "late-audio.audio"}
    w["nodes"].append(
        {
            "id": "late-audio",
            "type": "capability",
            "capability": "voice-generation",
            "inputs": {"request": {"from": "media-planning.voice-request"}},
            "outputs": {"audio": {"contract": "audio.asset", "version": "^1.0"}},
            "next": "end-success",
        }
    )


@pytest.mark.parametrize(
    ("breaker", "message"),
    [
        (duplicate_id, "duplicate node"),
        (unreachable_node, "unreachable node"),
        (dangling_from, "dangling"),
        (unbounded_cycle, "unbounded cycle"),
        (missing_on_exhausted, "missing node"),
        (missing_approval_target, "missing node"),
        (incompatible_latest_contract, "expects contract"),
        (required_input_missing_on_branch, "unreachable on at least one path"),
        (old_v4_manual_review_bug, "unreachable on at least one path"),
        (producer_after_consumer, "unreachable on at least one path"),
    ],
)
def test_broken_workflows_fail(
    breaker: Any,
    message: str,
) -> None:
    workflow = deepcopy(corrected_v5_workflow())
    breaker(workflow)
    with pytest.raises(WorkflowValidationError, match=message):
        validate_workflow(workflow)


def test_corrected_v5_section_35_passes_static_validation() -> None:
    validate_workflow(corrected_v5_workflow())
