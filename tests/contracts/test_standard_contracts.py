from __future__ import annotations

import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator, RefResolver

ROOT = Path("contracts/standard")
MANIFEST = json.loads((ROOT / "manifest.json").read_text(encoding="utf-8"))


@pytest.mark.parametrize("entry", MANIFEST["contracts"], ids=lambda entry: entry["id"])
def test_standard_contract_schema_and_sample(entry: dict[str, str]) -> None:
    schema_path = ROOT / entry["schema"]
    sample_path = ROOT / entry["sample"]
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    sample = json.loads(sample_path.read_text(encoding="utf-8"))

    Draft202012Validator.check_schema(schema)
    resolver = RefResolver(base_uri=schema_path.resolve().as_uri(), referrer=schema)
    Draft202012Validator(schema, resolver=resolver).validate(sample)


def test_manifest_has_unique_contract_ids() -> None:
    ids = [entry["id"] for entry in MANIFEST["contracts"]]
    assert len(ids) == len(set(ids))
    assert MANIFEST["id"] == "yg-standard-contracts"
    assert MANIFEST["version"] == "1.0.0"
