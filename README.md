# YG-PLUG-PLAY

Plugin-first, Windows local-first content production platform.

Architecture authority:

- `docs/ARCHITECTURE_V5.md`
- `docs/ERRATA_V5.md`
- `AGENTS.md`

## Development

Requires Python 3.12+ and [uv].

```powershell
uv sync --dev
uv run ruff check .
uv run ruff format --check .
uv run mypy core
uv run pytest
```

Mutable application data must live outside the repository. The Windows default is
`%LOCALAPPDATA%\YG-PLUG-PLAY\`.

[uv]: https://docs.astral.sh/uv/
