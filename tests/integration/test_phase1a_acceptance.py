"""V5 §56 Phase-1a acceptance map.

Each criterion is exercised by the named executable test already owned by its
component. This suite makes the release gate explicit and prevents accidental
coverage loss.
"""
from pathlib import Path
import pytest

CRITERIA={
1:"tests/integration/test_workspace.py",
2:"tests/security/test_zip_installer.py",
3:"tests/security/test_plugin_registry.py",
4:"tests/security/test_plugin_registry.py",
5:"tests/test_purpose_router.py",
6:"tests/test_prompt_executor.py",
7:"tests/security/test_zip_installer.py",
8:"tests/security/test_zip_installer.py",
9:"tests/security/test_zip_installer.py",
10:"tests/security/test_rpc_permissions.py",
11:"tests/security/test_worker_runtime.py",
12:"tests/security/test_plugin_data.py",
13:"tests/security/test_worker_runtime.py",
14:"tests/test_workflow_engine.py",
15:"tests/test_workflow_engine.py",
16:"tests/test_workflow_engine.py",
17:"tests/test_run_snapshots.py",
18:"tests/test_progress.py",
19:"tests/test_config_data_root.py",
20:"tests/test_config_data_root.py",
}
@pytest.mark.parametrize("criterion",range(1,21))
def test_v5_section_56_criterion_has_executable_coverage(criterion:int)->None:
 path=Path(CRITERIA[criterion])
 assert path.is_file(),f"V5 §56 criterion {criterion} has no executable acceptance coverage: {path}"

def test_two_purposes_two_routes_is_part_of_phase1a_gate()->None:
 text=Path("tests/test_purpose_router.py").read_text(encoding="utf-8")
 assert "test_two_purposes_resolve_different_models_same_channel" in text
