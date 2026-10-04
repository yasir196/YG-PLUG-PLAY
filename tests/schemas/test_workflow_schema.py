from __future__ import annotations

import json
from pathlib import Path

from jsonschema import Draft202012Validator

SCHEMA = json.loads(Path("schemas/workflow.schema.json").read_text(encoding="utf-8"))
Draft202012Validator.check_schema(SCHEMA)
VALIDATOR = Draft202012Validator(SCHEMA)


def corrected_v5_workflow() -> dict[str, object]:
    return {
        "id": "main-production",
        "version": 10,
        "start": "research",
        "nodes": [
            {
                "id": "research",
                "type": "capability",
                "capability": "deep-research",
                "inputs": {"brief": {"from": "$run.project-brief"}},
                "outputs": {"research": {"contract": "research", "version": "^1.0"}},
                "next": "script",
            },
            {
                "id": "script",
                "type": "capability",
                "capability": "script-generation",
                "inputs": {
                    "brief": {"from": "$run.project-brief"},
                    "research": {"from": "research.research"},
                },
                "outputs": {"script": {"contract": "script", "version": "^1.0"}},
                "next": "medical-review",
            },
            {
                "id": "medical-review",
                "type": "capability",
                "capability": "senior-health/medical-review",
                "inputs": {
                    "script": {"latest": "script", "among": ["script.script", "revision.script"]}
                },
                "outputs": {
                    "review": {"contract": "senior-health/medical-review", "version": "^1.0"}
                },
                "next": "review-decision",
            },
            {
                "id": "review-decision",
                "type": "condition",
                "inputs": {"review": {"from": "medical-review.review"}},
                "expression": {"==": [{"var": "review.passed"}, True]},
                "true_next": "final-approval",
                "false_next": "revision",
            },
            {
                "id": "revision",
                "type": "capability",
                "capability": "script-revision",
                "inputs": {
                    "script": {"latest": "script", "among": ["script.script", "revision.script"]},
                    "review": {"from": "medical-review.review"},
                    "feedback": {"latest": "approval.decision", "optional": True},
                },
                "outputs": {"script": {"contract": "script", "version": "^1.0"}},
                "loop_control": {
                    "counter": "medical-auto-revisions",
                    "max_attempts": 3,
                    "on_exhausted": "manual-review",
                    "reset_on": ["human-request-revision"],
                },
                "next": "medical-review",
            },
            {
                "id": "manual-review",
                "type": "human-approval",
                "inputs": {
                    "script": {"latest": "script", "among": ["script.script", "revision.script"]},
                    "review": {"from": "medical-review.review"},
                },
                "approval": {
                    "roles": ["channel-manager"],
                    "artifact": {"latest": "script", "among": ["script.script", "revision.script"]},
                    "actions": {
                        "approve": "media-planning",
                        "edit": "$self",
                        "request-revision": "revision",
                        "reject": "end-rejected",
                    },
                },
                "outputs": {"approved-script": {"contract": "script", "version": "^1.0"}},
            },
            {
                "id": "final-approval",
                "type": "human-approval",
                "inputs": {
                    "script": {"latest": "script", "among": ["script.script", "revision.script"]}
                },
                "approval": {
                    "roles": ["channel-manager", "producer"],
                    "artifact": {"latest": "script", "among": ["script.script", "revision.script"]},
                    "actions": {
                        "approve": "media-planning",
                        "edit": "$self",
                        "request-revision": "revision",
                        "reject": "end-rejected",
                    },
                },
                "outputs": {"approved-script": {"contract": "script", "version": "^1.0"}},
            },
            {
                "id": "media-planning",
                "type": "capability",
                "capability": "media-planning",
                "inputs": {"script": {"approved": "script"}},
                "outputs": {
                    "image-requests": {"contract": "image.request.collection", "version": "^1.0"},
                    "voice-request": {"contract": "voice.request", "version": "^1.0"},
                },
                "next": "media-stage",
            },
            {
                "id": "media-stage",
                "type": "parallel",
                "branches": ["generate-images", "generate-voice"],
                "join": "media-join",
            },
            {
                "id": "generate-images",
                "type": "map",
                "inputs": {"requests": {"from": "media-planning.image-requests"}},
                "items_from": "requests.items",
                "capability": "image-generation",
                "concurrency": 4,
                "failure_policy": {
                    "mode": "retry-failed-items",
                    "max_attempts": 3,
                    "on_exhausted": "media-failure-review",
                },
                "outputs": {
                    "images": {
                        "contract": "image.asset",
                        "version": "^1.0",
                        "collection": {"allow_partial": True, "min_success_ratio": 0.95},
                    }
                },
            },
            {
                "id": "generate-voice",
                "type": "capability",
                "capability": "voice-generation",
                "inputs": {"request": {"from": "media-planning.voice-request"}},
                "outputs": {"audio": {"contract": "audio.asset", "version": "^1.0"}},
            },
            {
                "id": "media-failure-review",
                "type": "human-approval",
                "inputs": {
                    "failed-items": {"from": "generate-images.failed-items"},
                    "successful-items": {"from": "generate-images.images"},
                },
                "branch_context": "generate-images",
                "approval": {
                    "roles": ["producer", "channel-manager"],
                    "actions": {
                        "retry-failed": "generate-images",
                        "accept-partial": "media-join",
                        "reject": "end-rejected",
                    },
                },
            },
            {
                "id": "media-join",
                "type": "join",
                "branches": ["generate-images", "generate-voice"],
                "policy": {
                    "require": "all-successful-or-approved-partial",
                    "on_terminal_reject": "cancel-other-branches",
                },
                "next": "timeline",
            },
            {
                "id": "timeline",
                "type": "capability",
                "capability": "timeline-build",
                "inputs": {
                    "script": {"approved": "script"},
                    "images": {"from": "generate-images.images"},
                    "audio": {"from": "generate-voice.audio"},
                },
                "outputs": {"timeline": {"contract": "timeline", "version": "^1.0"}},
                "next": "pre-publish-check",
            },
            {
                "id": "pre-publish-check",
                "type": "capability",
                "capability": "pre-publish-check",
                "inputs": {
                    "timeline": {"from": "timeline.timeline"},
                    "brief": {"from": "$run.project-brief"},
                },
                "outputs": {"checklist": {"contract": "publish.checklist", "version": "^1.0"}},
                "next": "pre-publish-decision",
            },
            {
                "id": "pre-publish-decision",
                "type": "condition",
                "inputs": {"checklist": {"from": "pre-publish-check.checklist"}},
                "expression": {"==": [{"var": "checklist.passed"}, True]},
                "true_next": "end-success",
                "false_next": "pre-publish-review",
            },
            {
                "id": "pre-publish-review",
                "type": "human-approval",
                "inputs": {"checklist": {"from": "pre-publish-check.checklist"}},
                "approval": {
                    "roles": ["producer", "channel-manager"],
                    "actions": {"override": "end-success", "reject": "end-rejected"},
                },
            },
            {"id": "end-success", "type": "end", "status": "success"},
            {"id": "end-rejected", "type": "end", "status": "rejected"},
        ],
    }


def test_corrected_v5_section_35_workflow_validates() -> None:
    VALIDATOR.validate(corrected_v5_workflow())


def test_stay_is_not_a_valid_action_target() -> None:
    workflow = corrected_v5_workflow()
    manual = next(node for node in workflow["nodes"] if node["id"] == "manual-review")  # type: ignore[index]
    manual["approval"]["actions"]["edit"] = "stay"  # type: ignore[index]
    assert list(VALIDATOR.iter_errors(workflow))


def test_old_items_from_envelope_path_fails() -> None:
    workflow = corrected_v5_workflow()
    image_map = next(node for node in workflow["nodes"] if node["id"] == "generate-images")  # type: ignore[index]
    image_map["items_from"] = "inputs.requests.items"  # type: ignore[index]
    assert list(VALIDATOR.iter_errors(workflow))
