"""Materialize declarative niche defaults into Channel-owned DB records."""

from __future__ import annotations

import json
from pathlib import Path

from sqlalchemy.orm import Session

from core.database.models import ChannelRoute, Plugin, Workflow, WorkflowVersion


def materialize_demo_defaults(session: Session, channel_id: str, root: Path) -> None:
    workflow_data = json.loads(
        (root / "niches/demo/workflows/default.workflow.json").read_text(encoding="utf-8")
    )
    routes_data = json.loads(
        (root / "niches/demo/routing/default.routes.json").read_text(encoding="utf-8")
    )
    workflow_id = f"{channel_id}:demo-production"
    # Routes may reference the bundled demo provider before its executable
    # version is installed/trusted. Keep the registry identity present so
    # SQLite foreign keys remain valid; availability still requires version,
    # trust and an enabled Channel assignment.
    if session.get(Plugin, "demo-text-provider") is None:
        session.add(Plugin(id="demo-text-provider", kind="general"))
        session.flush()
    session.add(Workflow(id=workflow_id, name="Demo Production"))
    session.flush()
    session.add(
        WorkflowVersion(
            workflow_id=workflow_id,
            version=int(workflow_data["version"]),
            definition_json=json.dumps(workflow_data, sort_keys=True),
        )
    )
    for route in routes_data["routes"]:
        session.add(
            ChannelRoute(
                channel_id=channel_id,
                capability=route["capability"],
                purpose=route.get("purpose"),
                variant=route.get("variant"),
                primary_plugin_id=route["primary_plugin_id"],
                options_json=json.dumps(route.get("options", {}), sort_keys=True),
            )
        )
