# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Build & Development Commands

```bash
poetry install                          # Install dependencies
poetry run netskope --help              # Run the CLI
poetry run ntsk --help                   # Short alias

# Testing
poetry run pytest                       # All tests
poetry run pytest tests/unit/           # Unit tests only
poetry run pytest tests/integration/    # Integration tests only
poetry run pytest tests/unit/test_client.py::TestClassName  # Single test class
poetry run pytest --cov=src/netskope_cli tests/             # With coverage

# Linting & Formatting (run before commits/PRs)
poetry run ruff check .                 # Lint
poetry run ruff check . --fix           # Auto-fix lint issues
poetry run black .                      # Format
poetry run mypy src/                    # Type check
```

## Architecture

**Netskope CLI** — a Typer-based CLI for the Netskope platform, installable as `netskope` or `ntsk`.

### Core Modules (`src/netskope_cli/core/`)

- **`config.py`** — XDG-compliant config (`~/.config/netskope/config.toml`). Resolution order: CLI flags > env vars (`NETSKOPE_TENANT`, `NETSKOPE_API_TOKEN`, `NETSKOPE_PROFILE`) > profile config > defaults. Credentials stored in system keyring with plaintext fallback.
- **`client.py`** — Async `httpx`-based HTTP client (`NetskopeClient`). Supports token and session auth, pagination via `paginate()`, and maps HTTP status codes to typed exceptions.
- **`output.py`** — `OutputFormatter` handles json/table/csv/yaml/jsonl output. Auto-unwraps API response envelopes (checks `result`, `data`, `Resources` keys). Auto-detects TTY for human-friendly defaults. Handles timestamp conversion, field selection, wide-table column auto-selection, and `--count` mode.
- **`exceptions.py`** — `NetskopeError` base with typed subclasses (`AuthError`, `NotFoundError`, `RateLimitError`, etc.), each carrying `message`, `suggestion`, and `exit_code`.
- **`browser_auth.py`** — Playwright-based SSO login with session cookie capture.

### Command Modules (`src/netskope_cli/commands/`)

25+ command modules (alerts, events, incidents, policy, users, etc.) following a consistent pattern:

```python
@some_app.command()
def list(ctx: typer.Context, ...):
    state = ctx.obj                    # Global State dataclass
    client = _build_client(ctx)        # Create NetskopeClient
    data = client.request("GET", "/api/v2/...")
    formatter = _get_formatter(ctx)
    formatter.format_output(data, fmt=state.output.value, ...)
```

Each module defines helper functions: `_build_client()`, `_get_formatter()`, `_get_console()`, `_get_output_format()`.

### Entry Point (`src/netskope_cli/main.py`)

- `State` dataclass holds global options (profile, output format, verbose, quiet, raw, epoch)
- `_hoist_global_options()` rewrites argv so flags like `-o json` work before or after subcommands
- `cli()` wraps the Typer app with top-level exception handling
- Commands are optional/lazy-loaded — missing modules don't break the CLI

### Key Conventions

- **Line length:** 120 (ruff and black)
- **Python target:** 3.11+
- **Config format:** Ruff rules E, F, W, I; mypy strict mode
- **Test tools:** pytest + respx (httpx mocking) + pytest-mock
- **Secrets:** Never hardcode; use env vars or keyring. Config files in `.gitignore`.
- **Formatters:** always obtain one via `netskope_cli.core.output.build_formatter(ctx)` (each module's
  `_get_formatter`/`_build_formatter` is a thin wrapper). The global query options `--fields`, `--list-fields`,
  `--where`, `--sort` live on `State` and are applied inside `OutputFormatter.format_output`; an unknown `--fields`
  name is always a warning, never an exit code (which keys a page has depends on the rows in it). Never
  declare a per-command `--fields`/`-f`: it is global and client-side only, and a local one would shadow it. An
  endpoint that accepts a server-side `fields` parameter exposes it as `--api-fields` (no short flag) and runs it
  through `core.datasearch.resolve_api_fields(ctx, value, params)`, which widens the projection with every top-level
  name `--fields`/`--where`/`--sort` reference, stores it in `params["fields"]` and returns an `ApiFieldSelection`
  (`display` goes to `format_output(fields=)`); send the request through `request_with_projection` so an HTTP 400 for
  a widened name names the option. The datasearch list commands do all of this through `fetch_page(ctx, client, ...)`
  and spread `page.format_kwargs(ctx)` into `format_output`. Help strings come from `API_FIELDS_HELP`/`COUNT_HELP`. Other
  per-command options that share a global name (`dem --where`, a local `--count`) are protected from hoisting by
  `_resolve_leaf_command()` in `main.py`. Path/filter machinery lives in `core/fieldpaths.py` and
  `core/filtering.py`; the user-facing reference is `ntsk docs fields`.
- **Datasearch counts:** `/api/v2/events/datasearch/*` returns at most 10,000 rows and no total. `--count` on those
  commands goes through `core/datasearch.py` (`DATASEARCH_PAGE_CAP`, `is_page_capped`, `count_exact`) and passes
  `capped_at=`/`capped_hint=` to `format_output`; every count path prints through `output.print_count` (`N+` on a
  terminal in table/human output, the bare integer otherwise) and shares `output.page_is_capped`/`page_count` with
  `ntsk status`. The global `--exact` pages with `offset` on datasearch endpoints only and requires `--start`. The
  events endpoints without a total (`counts_full_page`) fetch the full page under `--count`; audit keeps `--limit`.

## Releasing to PyPI

```bash
# 1. Bump version in BOTH places (keep them in sync)
#    - pyproject.toml  →  version = "X.Y.Z"
#    - src/netskope_cli/main.py  →  __version__ = "X.Y.Z"

# 2. Commit and push the version bump
git add pyproject.toml src/netskope_cli/main.py
git commit -m "Bump version to X.Y.Z"
git push origin master

# 3. Build and publish (PyPI token must be pre-configured in Poetry)
poetry build
poetry publish
```

**PyPI token setup** (one-time, done by the user — never by AI):
```bash
poetry config pypi-token.pypi pypi-YOUR_TOKEN
```

The token is stored locally by Poetry. Never pass it as a CLI argument in shared sessions or commit it to any file.
