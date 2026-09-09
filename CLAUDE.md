# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Build & Development Commands

```bash
uv sync                                 # Create .venv and install runtime + dev dependencies
uv run netskope --help              # Run the CLI
uv run ntsk --help                   # Short alias

# Testing
uv run pytest                       # All tests
uv run pytest tests/unit/           # Unit tests only
uv run pytest tests/integration/    # Integration tests only
uv run pytest tests/unit/test_client.py::TestClassName  # Single test class
uv run pytest --cov=src/netskope_cli tests/             # With coverage

# Lint, format, type-check (run before commits/PRs)
uv run ruff check .                 # Lint
uv run ruff check . --fix           # Auto-fix lint issues
uv run ruff format .                # Format (ruff format --check . to verify only)
uv run ty check                     # Type check src/ (scope and rules in [tool.ty])

# CI (.github/workflows/ci.yml) runs the same four checks on Python 3.11 and 3.14 for every
# pull request and push to master, then builds the wheel and sdist and smoke-tests both from a
# clean install (scripts/smoke-dist.sh, which release.yml runs on the artifacts it publishes).
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

- **Line length:** 120 (ruff lint and ruff format)
- **Python target:** 3.11+
- **Toolchain:** uv for packaging, ruff for lint (rules E, F, W, I) and formatting, ty for type checking of `src/`;
  all configured in `pyproject.toml`. Suppress a ty diagnostic with `# ty: ignore[rule]`; bare `# type: ignore` also works.
- **Changelog:** `CHANGELOG.md` follows Keep a Changelog 1.1.0 throughout. Every user-visible change
  lands in the same PR under `### Added` / `Changed` / `Deprecated` / `Removed` / `Fixed` / `Security` in the Unreleased
  section, one or two sentences per entry; the release runbook turns that section into the version entry and the
  GitHub Release notes.
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
# 1. Bump version in BOTH places (keep them in sync), then refresh the lockfile
#    - pyproject.toml  →  version = "X.Y.Z"
#    - src/netskope_cli/main.py  →  __version__ = "X.Y.Z"
uv lock                     # uv.lock records the project version; uv sync --locked fails until this runs

# 2. Commit and push the version bump
git add pyproject.toml uv.lock src/netskope_cli/main.py
git commit -m "Bump version to X.Y.Z"
git push origin master

# 3. Publish. Pushing the vX.Y.Z tag runs .github/workflows/release.yml, which
#    checks, builds and publishes through PyPI's Trusted Publisher for this repo;
#    no token is stored anywhere. Watch it with `gh run watch`.
#    The manual path below is the fallback when Actions cannot run. uv has no
#    credential store and does not read ~/.pypirc, so the token comes from the
#    macOS keychain for the one command.
rm -rf dist                 # uv publish uploads everything in dist/
uv build
token="$(security find-generic-password -s pypi-netskope -w)" && [ -n "$token" ] || exit 1
UV_PUBLISH_TOKEN="$token" uv publish --check-url https://pypi.org/simple/
```

**PyPI token setup** (one-time, done by the user — never by AI):
```bash
security add-generic-password -U -s pypi-netskope -a __token__ -w   # prompts for the token; -U lets a rotated one overwrite
```

`release.yml` uses PyPI's Trusted Publisher, Astral's recommended method, which needs no long-lived token;
the keychain-backed variable is the fallback only. Never echo the token, pass it on the command line in
shared sessions, or commit it to any file.
