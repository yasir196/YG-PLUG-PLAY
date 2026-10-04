from __future__ import annotations

import pytest

from core.plugin_data import PluginDataError, PluginDataService
from core.plugin_runtime.permissions import ExecutionContext, RPCPermissionError, RPCPermissionLayer


def ctx(channel: str):
    return ExecutionContext.create(
        plugin_id="demo-plugin",
        plugin_version="1.0.0",
        channel_id=channel,
        package_sha256="a" * 64,
        grants={"plugin-data.read", "plugin-data.write"},
    )


def test_channel_a_cannot_read_or_list_channel_b_data(tmp_path) -> None:
    service = PluginDataService(tmp_path / "plugin-data")
    service.set(ctx("channel-a"), "token", {"owner": "A"})
    service.set(ctx("channel-b"), "token", {"owner": "B"})
    assert service.get(ctx("channel-a"), "token") == {"owner": "A"}
    assert service.get(ctx("channel-b"), "token") == {"owner": "B"}
    assert service.list_keys(ctx("channel-a")) == ("token",)
    assert service.list_keys(ctx("channel-b")) == ("token",)


def test_supported_rpc_cannot_switch_to_other_channel(tmp_path) -> None:
    service = PluginDataService(tmp_path / "plugin-data")
    service.set(ctx("channel-b"), "private", "B-only")
    layer = RPCPermissionLayer(service.rpc_handlers())
    with pytest.raises(RPCPermissionError, match="switch channel"):
        layer.dispatch(
            ctx("channel-a"),
            "plugin-data.read",
            {"key": "private", "channel_id": "channel-b"},
        )
    assert layer.dispatch(ctx("channel-a"), "plugin-data.read", {"key": "private"}) is None


def test_key_path_escape_is_rejected(tmp_path) -> None:
    service = PluginDataService(tmp_path / "plugin-data")
    with pytest.raises(PluginDataError, match="unsafe"):
        service.set(ctx("channel-a"), "../channel-b/private", "attack")


def test_delete_is_confined_to_context_channel(tmp_path) -> None:
    service = PluginDataService(tmp_path / "plugin-data")
    service.set(ctx("channel-a"), "same", "A")
    service.set(ctx("channel-b"), "same", "B")
    assert service.delete(ctx("channel-a"), "same")
    assert service.get(ctx("channel-a"), "same") is None
    assert service.get(ctx("channel-b"), "same") == "B"
