"""Deterministic demo text-generation provider.

This executable is intentionally offline: it performs no network access and returns
stable fake text/JSON for Phase-1a integration tests.
"""

from __future__ import annotations

import hashlib
import json
import sys
from typing import Any


def generate(request: dict[str, Any]) -> dict[str, Any]:
    messages = request.get("messages", [])
    seed = json.dumps(messages, sort_keys=True, ensure_ascii=False)
    digest = hashlib.sha256(seed.encode("utf-8")).hexdigest()[:12]
    response_schema = request.get("response_schema")
    if response_schema is not None:
        structured: dict[str, Any] = {"demo": True, "passed": True, "id": digest}
        content = json.dumps(structured, sort_keys=True)
    else:
        structured = {}
        content = f"DEMO[{digest}]: deterministic generated text"
    return {
        "content": content,
        "structured": structured,
        "finish_reason": "stop",
        "usage": {"input_tokens": len(seed.split()), "output_tokens": len(content.split())},
        "provider": "demo-text-provider",
        "model": "demo-deterministic",
        "metadata": {"deterministic": True},
    }


def main() -> None:
    request = json.load(sys.stdin)
    json.dump(generate(request), sys.stdout, ensure_ascii=False)


if __name__ == "__main__":
    main()
