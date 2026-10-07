import importlib


def test_dashboard_routes_importable() -> None:
    module = importlib.import_module("dashboard.routes")
    assert hasattr(module, "build_dashboard_router")
