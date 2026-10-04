"""Development server entrypoint; deliberately loopback-bound."""

import uvicorn


def main() -> None:
    uvicorn.run("core.auth.app:app", host="127.0.0.1", port=8765)


if __name__ == "__main__":
    main()
