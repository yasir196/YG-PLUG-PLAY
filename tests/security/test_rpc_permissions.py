from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from core.plugin_runtime.permissions import ExecutionContext, RPCPermissionError, RPCPermissionLayer


def context(*grants: str) -> ExecutionContext:
    return ExecutionContext.create(
        plugin_id="demo-plugin",
        plugin_version="1.0.0",
        channel_id="channel-a",
        package_sha256="a" * 64,
        grants=set(grants),
    )


def test_execution_context_is_immutable_and_has_baseline_grants() -> None:
    ctx = context()
    assert "rpc.invoke" in ctx.grants
    assert "scratch.read" in ctx.grants
    with pytest.raises(FrozenInstanceError):
        ctx.channel_id = "channel-b"  # type: ignore[misc]
    with pytest.raises(AttributeError):
        ctx.grants.add("artifact.read")  # type: ignore[attr-defined]


def test_unauthorized_rpc_is_rejected() -> None:
    layer = RPCPermissionLayer({"artifact.read": lambda ctx, params: "secret"})
    with pytest.raises(RPCPermissionError, match="artifact.read"):
        layer.dispatch(context(), "artifact.read", {})


def test_authorized_rpc_is_dispatched() -> None:
    layer = RPCPermissionLayer({"artifact.read": lambda ctx, params: ctx.channel_id})
    assert layer.dispatch(context("artifact.read"), "artifact.read", {}) == "channel-a"


def test_attempt_to_switch_channel_is_rejected_even_with_grant() -> None:
    layer = RPCPermissionLayer({"artifact.read": lambda ctx, params: "bad"})
    with pytest.raises(RPCPermissionError, match="switch channel"):
        layer.dispatch(
            context("artifact.read"),
            "artifact.read",
            {"channel_id": "channel-b"},
        )


def test_unknown_rpc_is_rejected() -> None:
    with pytest.raises(RPCPermissionError, match="allowlisted"):
        RPCPermissionLayer({}).dispatch(context(), "core.database.open", {})
