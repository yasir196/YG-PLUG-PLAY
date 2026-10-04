"""Content-addressed artifact storage and safe worker scratch exchange."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from core.database.models import Artifact, ArtifactGeneration

MAX_OUTPUT_BYTES = 2 * 1024 * 1024 * 1024


class ArtifactError(ValueError):
    pass


@dataclass(frozen=True)
class InputHandle:
    relative_path: str
    sha256: str
    size: int


@dataclass(frozen=True)
class OutputHandle:
    relative_path: str
    sha256: str
    size: int


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


class ArtifactStore:
    def __init__(self, root: Path, session: Session) -> None:
        self.root = root.resolve()
        self.session = session
        self.objects = self.root / "objects"
        self.objects.mkdir(parents=True, exist_ok=True)

    def import_file(
        self,
        source: Path,
        *,
        run_id: str,
        contract_id: str,
        logical_name: str,
        actor: str,
        metadata: dict[str, Any] | None = None,
        artifact_id: str | None = None,
    ) -> ArtifactGeneration:
        digest = sha256_file(source)
        destination = self.objects / digest[:2] / digest
        destination.parent.mkdir(parents=True, exist_ok=True)
        if not destination.exists():
            fd, temp_name = tempfile.mkstemp(prefix=".import-", dir=destination.parent)
            os.close(fd)
            temp = Path(temp_name)
            try:
                shutil.copyfile(source, temp)
                if sha256_file(temp) != digest:
                    raise ArtifactError("source changed during atomic import")
                os.replace(temp, destination)
            finally:
                temp.unlink(missing_ok=True)
        artifact = self.session.get(Artifact, artifact_id) if artifact_id else None
        if artifact is None:
            artifact = Artifact(
                id=artifact_id or uuid.uuid4().hex,
                run_id=run_id,
                contract_id=contract_id,
                logical_name=logical_name,
            )
            self.session.add(artifact)
            self.session.flush()
        generation = self.session.scalar(
            select(func.max(ArtifactGeneration.generation)).where(
                ArtifactGeneration.artifact_id == artifact.id
            )
        )
        row = ArtifactGeneration(
            artifact_id=artifact.id,
            generation=(generation or 0) + 1,
            actor=actor,
            content_path=str(destination.relative_to(self.root)),
            sha256=digest,
            metadata_json=json.dumps(metadata or {}, sort_keys=True),
        )
        self.session.add(row)
        self.session.flush()
        return row

    def content_path(self, generation: ArtifactGeneration) -> Path:
        path = (self.root / generation.content_path).resolve()
        if not path.is_relative_to(self.root):
            raise ArtifactError("artifact path escapes store")
        return path


class ScratchJob:
    def __init__(self, root: Path, job_id: str) -> None:
        self.root = (root / job_id).resolve()
        self.inputs = self.root / "inputs"
        self.outputs = self.root / "outputs"
        self.inputs.mkdir(parents=True, exist_ok=True)
        self.outputs.mkdir(parents=True, exist_ok=True)
        self._input_hashes: dict[Path, str] = {}

    def materialize_input(self, source: Path, name: str) -> InputHandle:
        target = self._contained(self.inputs, name)
        target.parent.mkdir(parents=True, exist_ok=True)
        digest = sha256_file(source)
        try:
            os.link(source, target)
        except OSError:
            shutil.copy2(source, target)
        if sha256_file(target) != digest:
            raise ArtifactError("input hash mismatch during materialization")
        self._input_hashes[target] = digest
        return InputHandle(target.relative_to(self.root).as_posix(), digest, target.stat().st_size)

    def verify_inputs(self) -> None:
        for path, expected in self._input_hashes.items():
            if not path.is_file() or sha256_file(path) != expected:
                raise ArtifactError(f"worker mutated input: {path.name}")

    def validate_output(
        self,
        relative_path: str,
        *,
        expected_sha256: str,
        contract_schema: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
        max_bytes: int = MAX_OUTPUT_BYTES,
    ) -> OutputHandle:
        path = self._contained(self.outputs, relative_path)
        if not path.is_file():
            raise ArtifactError("output file missing")
        size = path.stat().st_size
        if size > max_bytes:
            raise ArtifactError("output exceeds size limit")
        digest = sha256_file(path)
        if digest != expected_sha256:
            raise ArtifactError("output hash mismatch")
        if contract_schema is not None:
            Draft202012Validator(contract_schema).validate(metadata or {})
        return OutputHandle(path.relative_to(self.root).as_posix(), digest, size)

    @staticmethod
    def _contained(base: Path, relative: str) -> Path:
        candidate = Path(relative)
        if candidate.is_absolute() or candidate.drive or ".." in candidate.parts:
            raise ArtifactError("path escape rejected")
        target = (base / candidate).resolve()
        if not target.is_relative_to(base.resolve()):
            raise ArtifactError("path escape rejected")
        return target
