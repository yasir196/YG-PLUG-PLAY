from __future__ import annotations

import sys
import zipfile
from pathlib import Path

REQUIRED = [
    "dashboard/__init__.py",
    "dashboard/app.py",
    "dashboard/routes.py",
    "dashboard/server.py",
    "dashboard/templates/approvals.html",
    "dashboard/templates/base.html",
    "dashboard/templates/channel.html",
    "dashboard/templates/channels.html",
    "dashboard/templates/login.html",
    "dashboard/templates/plugins.html",
    "dashboard/templates/project.html",
    "dashboard/templates/projects.html",
    "dashboard/templates/routing.html",
    "dashboard/templates/run.html",
    "core/__init__.py",
]


def main() -> None:
    wheel_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("dist")
    wheels = sorted(wheel_dir.glob("*.whl"))
    if len(wheels) != 1:
        raise SystemExit(f"expected exactly one wheel in {wheel_dir}, found {len(wheels)}")

    with zipfile.ZipFile(wheels[0]) as wheel:
        names = set(wheel.namelist())

    missing = [name for name in REQUIRED if name not in names]
    if missing:
        print("missing wheel members:")
        for name in missing:
            print(f"- {name}")
        raise SystemExit(1)

    print(f"wheel ok: {len(REQUIRED)} required members verified")
    for name in REQUIRED:
        print(f"- {name}")


if __name__ == "__main__":
    main()
