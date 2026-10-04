from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from core.artifacts import ArtifactError, ScratchJob


def test_large_input_is_handle_not_json_payload(tmp_path: Path) -> None:
    source = tmp_path / "large.bin"
    source.write_bytes(b"x" * (2 * 1024 * 1024))
    scratch = ScratchJob(tmp_path / "scratch", "job-1")
    handle = scratch.materialize_input(source, "large.bin")
    assert handle.relative_path == "inputs/large.bin"
    assert handle.size == source.stat().st_size
    assert not hasattr(handle, "data")


def test_mutated_input_is_detected(tmp_path: Path) -> None:
    source = tmp_path / "input.bin"
    source.write_bytes(b"original")
    scratch = ScratchJob(tmp_path / "scratch", "job-2")
    handle = scratch.materialize_input(source, "input.bin")
    materialized = scratch.root / handle.relative_path
    materialized.write_bytes(b"mutated")
    with pytest.raises(ArtifactError, match="mutated input"):
        scratch.verify_inputs()


def test_parent_escape_is_rejected(tmp_path: Path) -> None:
    scratch = ScratchJob(tmp_path / "scratch", "job-3")
    with pytest.raises(ArtifactError, match="escape"):
        scratch.validate_output("../escape.bin", expected_sha256="0" * 64)


def test_output_hash_size_and_contract_are_validated(tmp_path: Path) -> None:
    scratch = ScratchJob(tmp_path / "scratch", "job-4")
    output = scratch.outputs / "result.bin"
    output.write_bytes(b"result")
    digest = hashlib.sha256(b"result").hexdigest()
    schema = {
        "type": "object",
        "required": ["media_type"],
        "properties": {"media_type": {"const": "application/octet-stream"}},
        "additionalProperties": False,
    }
    handle = scratch.validate_output(
        "result.bin",
        expected_sha256=digest,
        contract_schema=schema,
        metadata={"media_type": "application/octet-stream"},
        max_bytes=100,
    )
    assert handle.sha256 == digest
    with pytest.raises(ArtifactError, match="size"):
        scratch.validate_output("result.bin", expected_sha256=digest, max_bytes=1)
