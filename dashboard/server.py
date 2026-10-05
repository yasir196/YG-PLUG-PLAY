"""Development dashboard server; loopback only."""

import uvicorn


def main() -> None:
    uvicorn.run(
        "dashboard.app:create_dashboard_app",
        factory=True,
        host="127.0.0.1",
        port=8765,
    )


if __name__ == "__main__":
    main()
