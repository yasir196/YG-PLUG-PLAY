import importlib
import sys

import pytest

import core.config


class _ImportSideEffect(RuntimeError):
    pass


def test_importing_dashboard_app_does_not_initialize_data_root(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def forbidden(*args: object, **kwargs: object) -> None:
        raise _ImportSideEffect("initialize_data_root called at import time")

    monkeypatch.setattr(core.config, "initialize_data_root", forbidden)
    monkeypatch.delitem(sys.modules, "dashboard.app", raising=False)

    module = importlib.import_module("dashboard.app")

    assert hasattr(module, "create_dashboard_app")
