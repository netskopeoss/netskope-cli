# Changelog

## [0.2.19] - 2026-03-06

- Fix zsh/bash/fish shell completion (`ntsk completion install`) failing with `Error: 'COMP_WORDS'` when `add_completion=False` is set on the Typer app — Typer's custom completion classes were never registered, causing Click's default handler to run instead

## [0.2.18] - 2026-03-06

- Add interactive HTML guide with shadcn/Tailwind design, Mermaid architecture diagrams, real API response examples, and full command reference
- Publish guide as GitHub Pages at https://netskopeoss.github.io/netskope-cli/
- Add homepage and documentation URLs to pyproject.toml for PyPI display
- Add guide link to top of README.md
- Set GitHub repo homepage to the guide URL

## [0.2.17] - 2026-03-06

- Allow `intel url-lookup` to accept URL as a positional argument (e.g. `ntsk intel url-lookup google.com`) in addition to `--url`
- Fix `--wide` / `-W` flag not working for events, incidents, and most other commands (only alerts had it wired up)
- Add `--since` alias for `--period` on `status` command (e.g. `ntsk status --since 7d`)
- Auto-route `devices list` to `events client-status` endpoint when the devices API returns 404
- Add record count to stderr for CSV output (matching table/human behavior) for visibility when piping
- Clarify publishers command hierarchy: top-level `publishers` help now notes it's a shortcut for `npa publishers`

## [0.2.16] - 2026-03-06

- Improve playwright missing error message: clarify that browser SSO is optional, show correct `netskope-cli[browser]` install command, and suggest API token auth as an alternative

## [0.2.15] - 2026-03-06

- Fix `alerts summary` to show actual counts per group (API only returned unique values, now aggregates locally)
- Fix `-W` / `--wide` flag on alerts to show all columns (was being overridden by default field selection)
- Add `--group-by` alias for `--by` on `alerts summary` and `alerts list` for discoverability
- Add `--since` alias for `--start` on `alerts list` and `alerts summary` for common time-range queries
- Fix `_flatten_grouped_results` to handle API group-by responses that omit a count field
- Update README: use `ntsk` shorthand in all examples, fix clone URL typos, add all missing command groups, document global flags and environment variables, fix shell completion syntax

## [0.2.14] - 2026-03-06

- Add `--wide` / `-W` global flag to show all table columns without truncation
- Add `--desc` and `--asc` sort direction flags for `--order-by` on alerts and events commands
- Auto-enable quiet mode (`-q`) when stdout is not a TTY (piped output), suppressing spinners automatically
- Add `config setup` one-step wizard combining profile creation, tenant, and token setup
- Fix pre-existing test failures in `test_status_cmd.py` (mock signature mismatch)

## [0.2.13] - 2026-03-06

- Add `completion` command for shell completion installation (bash, zsh, fish, PowerShell)
- Fix misleading "No matching records found" message in `alerts summary` when groupby field has no data

## [0.2.12] - 2026-03-06

- Add issue tracker link to README for bug reports and feature requests

## [0.2.11] - 2026-03-06

- Add SSL/TLS CA bundle support for environments with Netskope client SSL inspection
- New `config set-ca-bundle` command with auto-detection of Netskope CA certificates
- Support `NETSKOPE_CA_BUNDLE`, `REQUESTS_CA_BUNDLE`, `SSL_CERT_FILE` env vars for CA bundle resolution
- Add `SSLError` exception with actionable platform-specific fix suggestions
- `doctor` command now checks CA bundle configuration and detects Netskope CA certs
- `status` command now passes cookies for session-based auth in async API calls

## [0.2.10] - 2026-03-06

- Fix repository URL typo in PyPI metadata

## [0.2.9] - 2026-03-06

- Fix API endpoint corrections: infrastructure events, transaction event metrics, notification delivery settings, publisher upgrade profiles, URL list creation, and NSIQ URL lookup/recategorize request bodies
- Add verbose logging support (-v for INFO, -vv for DEBUG) with HTTP request/response logging
- Improve error handling: detect API-level errors in 200 responses and raise typed exceptions
- Add NETSKOPE_PROFILE env var support for profile resolution
- Replace typer.Exit with typed ConfigError exceptions for missing configuration
- Add --offset alias for --start-index in user list command
- Fix auth token-info to use config-aware token resolution

## [0.2.8] - 2026-03-06

- Add Homebrew tap installation support (`brew tap netskopeoss/tap && brew install netskope`)
- Add Homebrew install instructions to README

## [0.2.7] - 2026-03-05

- Initial public release on PyPI
