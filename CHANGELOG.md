# Changelog

## [1.4.0] - 2026-04-24

- Add `incidents notes` sub-app with three commands for managing notes on DLP incidents: `notes list <dlp-incident-id>` (GET), `notes add <dlp-incident-id> -c "text"` (POST, client-side 512-char guard), and `notes delete <dlp-incident-id> <note-id> [-y]` (DELETE with confirmation prompt). Wraps the `/api/v2/incidents/dlpincidents/{id}/notes` endpoints.

## [1.3.1] - 2026-04-24

- Fix `rbac admins list` returning `HTTP 404: no Route matched with those values`. The command was calling `/api/v2/rbac/admins`, which does not exist — admin users are served by the ms-platform service at `/api/v2/platform/administration/scim/Users` (SCIM-based).
- Add `--limit`, `--start-index`, and `--filter` options to `rbac admins list` for SCIM pagination and filtering (e.g. `--filter 'urn:ietf:params:scim:schemas:netskope:2.0:user[recordType eq "SERVICE_ACCOUNT"]'`).
- Fix `test_config_token_used` and `test_auth_token_without_token_raises` leaking the developer's real keyring token into test assertions; both now mock the keyring call / `get_api_token` directly.

## [1.3.0] - 2026-04-17

- **Breaking:** `dem users applications` now requires `--device-id`. Without it, the `/api/v2/adem/users/getapplications` endpoint returns only a 1-2 app subset instead of the full per-device application list. Run `dem users devices` first to enumerate device IDs.
- `dem users diagnose` now fetches applications per device (inside the device loop) rather than at the user level, so each device's full app list appears under `devices[].applications` in JSON output and within each device panel in table output. The `--application` filter now scopes per-device.

## [1.2.1] - 2026-04-17

- Fix table output summarizing list-of-dict fields as `[N items]` (GitHub issue #9). Columns like `pops` on `ipsec tunnels list` and `categories` on `intel url-lookup` now render the inline values (e.g. `ord1, atl1`) using a common identifying key (`name`, `display_name`, `label`, `title`, or `id`), with `, ... (N items)` for lists longer than 3. Falls back to `[N items]` only when no common key exists.

## [1.2.0] - 2026-04-15

- Add `dem users diagnose` composite command: one-shot diagnostic report combining user info, applications, device details, aggregated scores, and RCA from a ticket's user + time range. Supports `--include-npa` for NPA path analysis and `--application` to focus on a specific app.
- Add `dem users applications` command for `/api/v2/adem/users/getapplications` — list applications a user has accessed with experience scores
- Add `dem users device-details` command for `/api/v2/adem/users/device/getdetails` — detailed device info including client status/version, CPU, memory, OS, geo location, gateway, POP, public/private IPs
- Add `dem users npa-network-paths` command for `/api/v2/adem/users/npa/getnetworkpaths` — NPA network path graph showing nodes (DEVICE, GATEWAY, STITCHER, PUBLISHER, HOST) and edges with latency data
- Add unit tests for all new ADEM commands including diagnose partial-failure resilience
- Update documentation: README, index.html, Claude Code skill, and CHANGELOG with full new command reference

## [1.1.0] - 2026-04-07

- Add 10 ADEM user/device telemetry commands under `dem users`: devices, info, locations, scores, exp-score, rca, network, npa-hosts, traceroute-ts, traceroute
- `dem users rca` provides CPU utilization, top processes, memory usage, and disk utilization — previously only available in the Netskope web UI
- Add Netskope Community support banner to README and documentation site
- Update documentation: README, index.html, and Claude Code skill with full ADEM command reference

## [1.0.2] - 2026-04-02

- Fix README links: point Claude Code skills URL to https://code.claude.com/docs/en/skills and use full GitHub URL for netskope.md so it renders correctly on PyPI

## [1.0.1] - 2026-04-02

- Add troubleshooting guide for redacted user fields in alerts and events (API-side anonymization)
- Add troubleshooting subsection to Error Handling in documentation

## [1.0.0] - 2026-04-02

First public stable release. Promotes the CLI from beta to v1.0.0 with a stable command surface, comprehensive API coverage, and production-ready features:

- 25+ command groups covering alerts, events, incidents, users, policy, NPA, DEM, DSPM, SPM, ATP, IPS, RBI, and more
- Async HTTP client with token and browser SSO authentication
- JSON, table, CSV, YAML, and JSONL output formats with TTY auto-detection
- AI agent discoverability via `commands --flat --json` with read/write safety tags
- Shell completion for bash, zsh, fish, and PowerShell
- XDG-compliant config with system keyring credential storage
- SSL/TLS CA bundle support for environments behind Netskope SSL inspection
- Background version update notifications
- Homebrew tap, pip, and pipx installation support
- Interactive HTML guide and Claude Code AI agent skill

## [0.2.28] - 2026-04-02

- URL-encode all string-typed user inputs interpolated into API URL paths to prevent path traversal and parameter injection
- Thread configured CA bundle through browser-based login session validation so `netskope auth login` works behind Netskope SSL inspection
- Thread configured CA bundle through `netskope docs search` Algolia requests so documentation search works behind SSL inspection

## [0.2.27] - 2026-04-02

- Tag every command as `[read]` or `[write]` in `ntsk commands --flat` output so AI agents can distinguish safe queries from mutating operations
- Add `"mode"` and `"supports_yes_flag"` fields to `ntsk commands --flat --json` for programmatic safety checks
- Promote `ntsk commands --flat --json` as the primary agent discovery command in `--help`
- Add `ntsk status --extended -o json` as a prominent help item
- Add "Write command safety" section to main help explaining `--yes` flag behavior

## [0.2.26] - 2026-04-02

### Discoverability & Help Improvements (Round 2)

Based on a real AI agent session that attempted to auto-discover and call every CLI subcommand:

- `ntsk commands --flat` prints only leaf (executable) commands, one per line with descriptions — the fastest way for scripts and AI agents to discover all 231 commands
- `ntsk commands --flat --json` outputs a flat JSON array for machine consumption
- Universal "did you mean?" hints on all group commands — invoking any group without a subcommand (e.g. `ntsk users`) now lists available subcommands after the help text
- `ntsk status --extended` / `-x` fetches additional resource counts: SCIM groups, URL lists, NPA policy rules, IPsec tunnels, RBAC roles, and IPS enabled status
- `ntsk services cci` (no argument) now prints helpful guidance instead of "Missing argument", explaining the API requires an exact app name
- Added "Quick start for scripting / AI agents" section to `ntsk --help`
- Added DSPM cross-reference tip: "Run 'ntsk dspm list-types'" in the `resources` command help
- Expanded 403/404 error hints with endpoint-specific scope/license messages for RBAC, devices, IPsec, enrollment, events, notifications, ATP, DNS, and IPS
- Improved 403/404 fallback messages to reference Settings > Tools > REST API v2

## [0.2.25] - 2026-04-02

- Add background version update check — notifies users when a newer release is available on PyPI
- Auto-detects install method (pip, pipx, brew, uv) and shows the exact upgrade command
- Never blocks CLI startup — cache misses trigger a background daemon thread; notice appears on next invocation
- Suppress with `NETSKOPE_NO_UPDATE_CHECK=1`, `--quiet`, or non-TTY stderr

## [0.2.24] - 2026-04-02

### Discoverability & Help Improvements

Based on feedback from an AI agent discovery session, 10 improvements to help text, error messages, and command discoverability:

- `ntsk commands` now shows positional argument signatures (e.g. `resources <RESOURCE_TYPE>`) in the tree
- `ntsk commands --json` outputs a machine-readable JSON tree of all commands, args, options, and descriptions — ideal for AI agent enumeration
- `ntsk dspm list-types` lists all valid DSPM resource types for the `resources` command
- `ntsk dspm analytics` help text now includes example metric types
- `ntsk npa policy list` now prints a helpful redirect to `rules list` and `groups list` instead of a generic error
- `ntsk steering config` (bare, no subcommand) now defaults to `get` instead of printing help
- `ntsk devices list --no-fallback` errors instead of silently falling back to `events client-status` with a different schema
- `ntsk devices list` fallback warning now notes the schema difference
- `--count` help text clarified: returns fetched count (subject to `--limit`), not the true total
- 403 errors now include license/scope hints (e.g. "DEM requires a Digital Experience Management license and a 'DEM Admin' role")
- 404 error hints already existed; 403 hints now use the same path-based suggestion pattern

## [0.2.23] - 2026-04-01

- Add 9 DEM query, alert, and app commands covering the full DEM API surface
- `dem metrics query` — query RUM, traceroute, HTTP, and UX score metrics from 17 data sources with JSON select/where/groupby/orderby
- `dem entities list` — list users with experience scores, device info, and location data (max 48h window)
- `dem states query` — query current agent or client connection states (agent_status, client_status)
- `dem traceroute query` — get hop-by-hop network path graph data
- `dem fields list` — discover available fields and metrics per data source
- `dem experience-alerts search` — search triggered DEM alert instances by category, type, severity
- `dem experience-alerts get` — get full details for a specific alert
- `dem experience-alerts entities` — list users/devices impacted by an alert
- `dem apps list` — list DEM-monitored applications (predefined and custom)
- Client-side validation for data sources and 48-hour time window constraint
- Add 39 unit tests and 10 integration tests for all new DEM commands
- Update README, interactive HTML guide, and AI Agent Skill with new DEM commands

## [0.2.22] - 2026-03-31

- Replace SCIM read-only commands with User Management API for richer data including group membership
- `users list` and `users get` now use `POST /api/v2/users/getusers` — returns `parentGroups`, `scimId`, `provisioner` per user
- `users groups list` and `users groups get` now use `POST /api/v2/users/getgroups` — returns `userCount`, `provisioner`, `deleted`
- Add `users groups members` command to list all users in a specific group by display name
- `users get` now accepts email or username instead of SCIM UUID, with auto-detection
- `groups get` now accepts display name instead of SCIM UUID
- `--filter` on user/group queries now accepts JSON dict syntax with operators (`eq`, `in`, `sw`, `co`)
- SCIM CRUD commands (create/update/delete) unchanged — still use `/api/v2/scim/` endpoints
- Update AI Agent Skill, README, and interactive HTML guide with new User Management API commands and filter syntax
- Add 19 unit tests for all new and modified user/group commands

## [0.2.21] - 2026-03-06

- Add AI Agent Skill (`.claude/commands/netskope.md`) — a Claude Code `/netskope` slash command that teaches AI agents how to use every CLI command, with verified flags, field names, gotchas, and workflow patterns
- Add AI Agent Skill section to the interactive HTML guide with collapsible viewer and copy-to-clipboard button
- Add AI Agent Skill section to README with setup instructions and examples
- Track `.claude/commands/` in git for shared agent skills

## [0.2.20] - 2026-03-06

- Add `alerts get` command — look up alerts by ID, user, app, name, type, severity, or activity without writing raw JQL
- Add `events get` command — look up events by ID, user, app, action, severity, policy, domain, source/destination IP, or hostname
- Update README and interactive HTML guide with examples and documentation for the new `get` commands
- Update User Investigation Workflow in docs to use the new ergonomic `get` commands

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
