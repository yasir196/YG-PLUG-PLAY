"""Minimal plugin SDK base class and stdio JSON-RPC worker loop."""

from __future__ import annotations

import json
import sys
from abc import ABC, abstractmethod
from typing import Any


class PluginSDK(ABC):
    @abstractmethod
    def invoke(self, method: str, params: dict[str, Any]) -> Any:
        """Handle one Core-authorized RPC request."""

    def serve_stdio(self) -> None:
        for line in sys.stdin:
            try:
                request = json.loads(line)
                if request.get("jsonrpc") != "2.0" or "id" not in request:
                    raise ValueError("invalid JSON-RPC request")
                result = self.invoke(str(request["method"]), dict(request.get("params", {})))
                response = {"jsonrpc": "2.0", "id": request["id"], "result": result}
            except Exception as exc:
                response = {
                    "jsonrpc": "2.0",
                    "id": request.get("id") if "request" in locals() else None,
                    "error": {"code": -32000, "message": str(exc)},
                }
            sys.stdout.write(json.dumps(response, separators=(",", ":")) + "\n")
            sys.stdout.flush()
