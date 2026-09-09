# Changelog

All notable changes to this project are documented in this file.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project
adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- `--api-fields` on `alerts list`, every `events` subcommand, `incidents list`/`search`, `npa publishers list` and `npa policy rules list`/`rules get`/`groups list`: the server-side field projection, now distinct from the global `--fields`. It is widened with every top-level name that `--fields`, `--where` or `--sort` reference, shows its columns in the requested order unless `--fields` picks others, keeps the `<field>_iso` companions of the fields it names, and warns rather than fails when the API omits a projected field. An HTTP 400 for a name the widening added says which option referenced it, on `--exact` and the NPA commands too.
- Global `--exact`: with `--count` on the datasearch commands (alerts, incidents, events other than `audit`, `infrastructure` and `transaction`, which count a single page and say so), page through the endpoint with `offset` for the true total, applying `--where` per page, up to `NETSKOPE_COUNT_CEILING` rows (default 200,000; prints `N+`, or the bare integer when piped, if reached). It requires `--start`, which the commands resolve to a fixed epoch once so every page is counted against the same window; paging the API's rolling default window would count a moving target. `--group-by` results are counted on a single page. An endpoint that ignores `offset` (the same first `_id` on consecutive pages) is an error rather than a doubled or falsely exact count, and an `--api-fields` projection is widened with `_id` while counting so that check always has something to compare.
- `ntsk status` marks a count that hit the 10,000-row page cap as `≥N` in the table and adds `alerts_capped` and friends to the JSON output.
- GitHub Actions: `ci.yml` runs `uv sync --locked`, `ruff check`, `ruff format --check`, `ty check` and `pytest` on Python 3.11 and 3.14 for every pull request and push to master, then builds the wheel and sdist and installs each into a clean environment to check the CLI runs and its command tree is intact (`scripts/smoke-dist.sh`, the check that would have caught v1.4.6). `release.yml` publishes to PyPI from a `vX.Y.Z` tag through PyPI's Trusted Publisher after checking that the tag matches the project version, and runs the same smoke test on the artifacts it uploads. Both workflows pin every action by commit SHA.
- PyPI metadata: Changelog and Issues links, console and security classifiers, keywords.

### Changed

- `--fields`/`-f` is the global, client-side option on every command and always reaches the formatter. A name that no returned record has warns with close-match suggestions and renders a blank (table/csv) or null (json/yaml) column; it never fails the command, because which keys a page carries depends on the rows that landed in it (`users list --fields externalId` when no user in the page has one, `dlp_rule` when no DLP alert did). The warning is specific where it can be: a hidden `_`-prefixed name points at `--raw`, and a `<field>_iso` name in table output says the companion exists only in json/jsonl/csv/yaml.
- For one release, a plain top-level `--fields` list on the commands that used to send it to the API prints a stderr note pointing at `--api-fields`. It survives piped stdout; only an explicit `--quiet` silences it.
- `--count` on the datasearch commands and on `events infrastructure`/`transaction` fetches the full 10,000-row page (`events audit` states a total and counts with `--limit` rows), and a page that came back full is a lower bound whatever filled it, the 10,000-row cap or a smaller `--limit`: on a terminal, table/human output prints `10000+` with a stderr notice; `-o json`/`jsonl`/`csv`/`yaml` and any piped output print the bare integer so `$(ntsk ... --count)` keeps parsing a number, with the same notice on stderr; a listing's result banner reads `10,000+ results (capped)`; `alerts summary` notes when its aggregation covered only the first 10,000 alerts. One rule decides, shared with `ntsk status`: a stated envelope total (`total`, `totalResults`, `status.total`) is exact; a `status.count` larger than the rows of a full page is the lower bound; a `--count --where` over a full page is a lower bound whatever the total says. `--count` with `--group-by` reports the number of groups on every events command.
- `npa policy rules get` prints the rule object rather than its `{"data": ..., "status": ...}` envelope.
- `typer` 0.25.1 to 0.27.2. The command-tree walkers introspect typer's public classes (`typer.core.TyperGroup`, `TyperCommand`, `TyperOption`, `TyperArgument`) instead of the standalone `click` package; `ntsk commands --json` keeps upper-case argument names and click's type names.
- Packaging moves from Poetry to uv: PEP 621 metadata, hatchling as the build backend, dev dependencies in `[dependency-groups]`, a committed `uv.lock`. Wheel metadata differs from 1.4.8 only in `License-Expression: MIT` replacing the `License` field and classifier, `Requires-Python` losing Poetry's `<4.0` cap, and `click` no longer being required.
- Lint, format and type-check with `ruff check`, `ruff format` and `ty` (`src/`). The one-time reformat joins implicit string concatenations that fit on one line.
- `CHANGELOG.md` follows Keep a Changelog throughout: every version's entries are grouped by change type and every version heading links to its GitHub comparison.
- Release runbook: the tag-triggered workflow is the primary publish path and the keychain-token `uv publish` is the fallback; `uv lock` is part of the version bump.
- `ntsk docs fields`, README, the docs site and the per-command help describe `--api-fields`, `--exact` and the count cap.

### Removed

- The redundant client-side `--fields` copies on `steering private-apps list`, `policy url-list list`, `services publishers list`/`private-apps list`, `npa apps list` and every `aicc` command; the global option covers them and binds `-f` there too.
- The direct `click` dependency and the `typer[all]` extra (typer 0.25 no longer defined it; `rich` and `shellingham` were already pinned).
- black, mypy, `types-toml` and `types-pyyaml` from the dev dependencies.

### Fixed

- `--fields` on `alerts list`, the `events` subcommands and `incidents list`/`search` was sent to the API but never applied to the output, so requested columns and their order were ignored, unknown names were accepted silently, and `--where` on a field outside the projection could never match (#19).
- `--count` on the datasearch commands, and the event counts in `ntsk status`, reported the 10,000-row page cap as if it were the total (#19).
- `netskope`/`ntsk` exited 0 after a command failed with `typer.Exit(code=N)`, for example `ntsk alerts get` with no ID or filter; scripts checking `$?` now see the failure.
- An HTTP 200 `ok: 0` error envelope on `alerts list --count`, `incidents list --count` and `alerts summary` is an error rather than a count of 1 or an empty summary, and its message is markup-safe on every events subcommand.
- `--raw` and `--epoch` apply to `events audit` and `events list --type audit`, and `--limit 0` is rejected there as on every other events command. The events title no longer repeats the total the result banner states, `--verbose` metadata omits `ok`/`message`, and the single-page notices `--exact` prints off datasearch endpoints respect `--quiet`.
- `ntsk status` prints its "All API calls failed" hint again when every metric is unavailable; the new `*_capped` flags had defeated the check.
- `ntsk commands --flat` omitted `ntsk status`, a group with no subcommands that runs on its own.
- An unknown option showed two competing suggestions after the typer bump; typer's `(Possible options: ...)` is folded into the CLI's hint.
- Two type errors mypy had been told to ignore: the `aicc analytics breakdown` config is a `TypedDict` and the filter tokenizer's token table is typed.

## [1.4.8] - 2026-09-04

### Added

- Add four global query options that work on **every** command, before or after the subcommand, and never change the API request: `--fields/-f` (pick output fields in the order given; dotted paths such as `host_info.os`, `a[].b` list hops, `a[0].b` indexes and `*` globs), `--list-fields` (print the response schema instead of the records: every nested path with type, presence percentage, sample value and a marker for the command's default columns; `-o json` for a machine-readable version), `--where 'EXPR'` (client-side row filter using the JQL syntax from `ntsk docs jql`: `eq ne gt ge lt le in like between`, `and/or/not`, parentheses, case-insensitive strings, numeric coercion, any-element semantics on lists, `eq null` for missing) and `--sort FIELD[:desc]` (stable multi-key sort, missing values last). `--where` runs before `--count` so the filtered count is reported. Syntax errors exit 2 with a caret under the offending token before any API call. Reference: `ntsk docs fields`.
- Docs: new `ntsk docs fields`, a cross-link from `ntsk docs jql`, a "Query any command" block in `ntsk --help`, a "Querying results" section in the README and on the docs site, and server-side notes on the per-command `--fields` help texts.

### Changed

- Field selection now supports nested paths and preserves the requested column order (previously exact top-level keys only, in record order). Applies to the pre-existing client-side `--fields` options too (policy, steering, services, npa apps, aicc).
- Global flag hoisting is now leaf-aware: a global flag is only moved in front of the subcommand when that subcommand does not declare the same flag itself, so `events/alerts/incidents --fields` still project server-side, `dem ... --where` still sends the DEM JSON where-clause, `atp scan-file -f` still means `--file`, and `aicc --sort-by` is untouched. Hoisting previously had no tests; it now has 20.
- All 26 per-module formatter helpers delegate to `core.output.build_formatter(ctx)`, the single place that reads the global options from `State`.

### Fixed

- Fix the wide-table hint that suggested `--fields` on commands that did not accept it (`ntsk devices list --fields ...` failed with "No such option"). The hint now names `--list-fields`, a `--fields` example drawn from all columns including hidden ones, and `-W`, and is suppressed when the user already chose columns. Unknown field names in `--fields`, `--where` or `--sort` print a warning with close matches instead of silently producing blank columns; `--field` typos suggest `--fields`.

## [1.4.7] - 2026-09-04

### Added

- Add `dem sites summary` — the DEM "Sites" view in one call: one row per site with `avg_dns_ms`, `avg_isp_latency_ms` (traceroute_pop `rtt_e2e` to the Netskope POP), `pops_used` (+ `pops`), `apps_reached` (+ `apps`), packet loss and request counts. Joins two public `getdataset` queries (`http_steered` and `traceroute_pop`) grouped by `site_name`; the empty site is reported as `Remote`. Defaults to the last 24h, capped at 48h; `--begin/--end`, `--where` and `--limit` are optional. Mirrors the `get_site_summary` action added to the MCP server in v3.7.0.
- Add `dem dataset query` for the public `/api/v2/dem/query/getdataset` endpoint (8 synthetic/RUM sources, 48h window, 9999-row cap). Same select/where/groupby/orderby grammar as `dem metrics query`, but documented and usable with scoped API tokens.

### Changed

- Pin every runtime and dev dependency to an exact version in `pyproject.toml` (typer 0.25.1, click 8.5.0, rich 14.3.4, httpx 0.28.1, pydantic 2.13.5, pydantic-settings 2.15.0, keyring 25.7.0, pyyaml 6.0.3, toml 0.10.2, shellingham 1.5.4; playwright 1.58.0 for the `browser` extra). The v1.4.6 typer cap stopped one regression, but open ranges still let fresh installs drift to newer click/rich/pydantic than the test suite runs against. Verified on fresh venvs (Python 3.11–3.14): `netskope commands` renders the full tree and typer 0.27.2 still breaks it. Bumping a pin now means editing `pyproject.toml`, running `poetry lock`, the full suite, and a fresh-install smoke test.
- Document the exact DEM aggregation function names in `dem metrics query --help` (`countDistinct`, `topK5`, `"/"` for µs→ms; there is no `count_distinct`), that time metrics are microseconds, and that the `isp` key only exists on the RUM sources. Per-site views should use `site_name`/`pop_name`/`application_name` on `http_*`/`traceroute_*`.

### Fixed

- Fix table output dropping values that look like Rich markup tags (#16). NPA private app names are returned as `[name]`; when the name started with a lowercase letter (`[ipinfo]`, `[linux1-EB-ssh]`) Rich parsed it as a style tag and rendered an empty `app_name` cell, while `[Cloud Exchange]` survived. Table, key/value and single-column cells are now markup-escaped, as are the `SUCCESS`/`ERROR`/`WARNING`/`INFO` message helpers. JSON/YAML/CSV output was never affected.

## [1.4.6] - 2026-09-02

### Added

- Add regression tests that exercise the real Typer app (not a synthetic `click` group) and assert `typer.Context` still subclasses `click.Context`, so a future dependency bump cannot reintroduce this silently.

### Changed

- Constrain `typer` to `>=0.9,<0.26` so the CLI builds against the same `click` it imports. Last known-good version is 0.25.1.

### Fixed

- Fix `netskope commands` returning an empty command tree on fresh installs. typer 0.26.0 began bundling its own vendored copy of `click`, so the `isinstance(obj, click.Group)` checks in `tree_cmd.py` and `main.py` silently evaluated to `False`. Because the dependency constraint allowed `typer <1.0`, any new `pip install` resolved a broken combination:
  - `netskope commands` rendered only the root node, and `netskope commands --flat` / `--json` returned nothing.
  - The "available subcommands" hint shown when a command group is invoked bare stopped appearing, and a bare `Error:` line leaked to stderr instead.

## [1.4.5] - 2026-08-18

### Added

- Add the `aicc` command group — full AI Command Center support (34 commands over the `/api/v2/aicc` inventory API):
  - Inventories with search/filter/sort/pagination (`--all` fetches every page): `aicc apps`, `aicc mcp`, `aicc models`, `aicc agents`, `aicc identities` (`--type user|unknown` for known people vs unattributed sources), and `aicc extensions`.
  - Per-entity drill-down: `get` (detail + usage summary + footprint), `identities`, `deployments --type <footprint key>`, `trend --kind traffic|identity|risk`, `violations`, and `apps status` for CASB sanctioning checks.
  - Analytics: `entities` (headline counts), `counts`/`sums` (KPIs with trend vs the prior window and bucketed time series), `breakdown` (dimension charts with per-entity dimension/metric validation), `alerts-matrix`, and `alert-policies`.
  - Provider DLP posture: `aicc data-protection summary|violations anthropic|mscopilot|chatgpt`.
  - `aicc report` — aggregates ~10 endpoints into one AI Risk Report data bundle (executive summary, top apps/MCP servers/users/unknown identities, alert posture, computed key findings) as JSON or rendered Markdown; `aicc overview` for a one-call dashboard summary; `aicc coverage` for the earliest date with data; `aicc guide` for an in-CLI cheat sheet (data model, command map, workflow recipes, gotchas).
  - Time flags accept relative offsets (`7d`), ISO dates, or epochs and are converted to the ISO 8601 UTC strings the AICC API requires. 404s explain the AICC licensing requirement; 403s point at the missing `ai_security_discovery` token scope.
- Add `tests/unit/test_aicc_cmd.py` (26 tests).

### Changed

- The output formatter now unwraps `data.items` and `data.violations` envelopes (used by AICC and other newer APIs).
- Document the `aicc` group in README and teach it to the AI agent skill (`.claude/commands/netskope.md`).

## [1.4.4] - 2026-07-31

### Added

- Add `--object-id` to `incidents update` for the original object-scoped behaviour, now opt-in and requiring `--old-value`. It warns before running: the API updates every incident attached to the object (50 in one observed case) while reporting `"result": "1"`, because `result` counts payload entries rather than incidents.
- Add `tests/unit/test_incidents_cmd.py` (18 tests); `incidents update` previously had none.

### Changed

- `incidents update` validates `--new-value` against the values each field accepts: `new`/`in_progress`/`resolved`/`closed` for status, `Low`/`Medium`/`High`/`Critical` for severity. The tenant validates severity itself but writes an unrecognised *status* verbatim, so a typo or wrong capitalisation silently corrupts the incident's workflow state. `--force` bypasses the check.

### Fixed

- Fix `incidents update` never updating anything. The command sent the incident ID as `object_id`, but the API treats that as the ID of the *object* an incident is about (e.g. `hash_user@example.com_<md5>_<sha1>`), not the incident. Nothing matched, and the API answered either HTTP 200 `{"ok": 1, "result": "0"}` or HTTP 500 "Failed to update incidents, please try later." The command now sends `incident_id` as a JSON integer, which the API requires — a quoted ID is rejected with `incident_id attribute needs to be integer`.
- `incidents update` now fails on responses that only look successful. HTTP 200 with `{"ok": 0, ...}` (how several input errors are returned) and `{"ok": 1, "result": "0"}` (every payload entry silently discarded) both exit non-zero with the API's message. A 500 from this endpoint is reported as "no incident matched" with a note that retrying will not help, since that is what it actually means.
- Correct `incidents update` help text, which documented status values (`open`) and severity capitalisation (`low`, `critical`) the API does not use, IDs in a `INC-123` format that does not exist, and claimed `--user` must be a valid tenant user (it is not validated at all). Also documents that success means the request was accepted, not that an incident changed — an ID matching no incident is reported as success.
- Fix incident examples in `docs/index.html` that do not run: `incidents update` was shown with `--status`/`--assignee`/`--comment` flags and a `PATCH /api/v2/incidents/{id}` endpoint that do not exist, `incidents anomalies` with a positional user (it takes `--users`, plural), and `incidents uci` with `--user` (it takes a positional argument).

## [1.4.3] - 2026-07-03

### Changed

- `npa` commands using `--json-file` now reject JSON files whose top-level value is not an object, instead of sending malformed payloads to the API.
- Type-safety pass: `mypy src/` is now clean (was 38 errors) — added `types-toml`/`types-PyYAML` stubs and fixed untyped returns, variable redefinitions, and annotations across 25 modules.

### Fixed

- Fix `npa publishers list --count` crashing with `TypeError`: the command passed an unsupported `count` keyword to the output formatter (now `count_only`).
- Fix a latent `AttributeError` in the getting-started hint: `main.py` referenced `ctx.protected_params`, which does not exist on Click's Context (now uses `ctx.args`).

### Security

- Security: resolve all GitHub Dependabot alerts — bump pytest to >=9.0.3 (tmpdir handling vulnerability) and refresh locked versions of cryptography (49.0.0), idna (3.18), and pydantic-settings (2.14.2).

## [1.4.2] - 2026-07-03

### Changed

- Document privileged endpoints: `dem metrics`, `dem states`, `dem traceroute`, `dem users traceroute`, and `dem users traceroute-ts` use internal endpoints absent from the public swagger; scoped API tokens may receive 403 (browser/session auth works).

### Fixed

- Fix `dem users scores --aggregation-type`: the API enum is `avg`/`p95` — the option previously advertised `avg/min/max`, where `min`/`max` return HTTP 400 and the valid `p95` was undocumented. Now a validated enum choice.
- Fix `dem users network --metric-type`: now a validated enum of the API's actual values `all/latency/packet_loss/jitter`, surfacing the previously hidden `jitter` metric and rejecting the invalid `packetloss` spelling client-side.
- Correct `dem users rca` help text: the endpoint returns a weighted root-cause tree plus per-component score summary (CPU, memory, disk, wifi, network, network RTT, device, user DEM), not raw CPU utilization/top-process data.
- Ports the applicable DEM/ADEM correctness fixes from mcp-server-pilot PR #25.
- Fix `policy url-list update <id>` returning HTTP 400 (`name required`). The PUT body placed `name` inside `data`, and the API requires `name` (top level), `data.urls`, and `data.type` on every request — but the command only sent the fields the user explicitly passed. The command now GETs the existing list first and PUTs with the user's `--name` / `--urls` / `--type` merged over the current values, so callers only need to specify what they want to change.

## [1.4.0] - 2026-04-24

### Added

- Add `incidents notes` sub-app with three commands for managing notes on DLP incidents: `notes list <dlp-incident-id>` (GET), `notes add <dlp-incident-id> -c "text"` (POST, client-side 512-char guard), and `notes delete <dlp-incident-id> <note-id> [-y]` (DELETE with confirmation prompt). Wraps the `/api/v2/incidents/dlpincidents/{id}/notes` endpoints.

## [1.3.1] - 2026-04-24

### Added

- Add `--limit`, `--start-index`, and `--filter` options to `rbac admins list` for SCIM pagination and filtering (e.g. `--filter 'urn:ietf:params:scim:schemas:netskope:2.0:user[recordType eq "SERVICE_ACCOUNT"]'`).

### Fixed

- Fix `rbac admins list` returning `HTTP 404: no Route matched with those values`. The command was calling `/api/v2/rbac/admins`, which does not exist — admin users are served by the ms-platform service at `/api/v2/platform/administration/scim/Users` (SCIM-based).
- Fix `test_config_token_used` and `test_auth_token_without_token_raises` leaking the developer's real keyring token into test assertions; both now mock the keyring call / `get_api_token` directly.

## [1.3.0] - 2026-04-17

### Changed

- **Breaking:** `dem users applications` now requires `--device-id`. Without it, the `/api/v2/adem/users/getapplications` endpoint returns only a 1-2 app subset instead of the full per-device application list. Run `dem users devices` first to enumerate device IDs.

### Fixed

- `dem users diagnose` now fetches applications per device (inside the device loop) rather than at the user level, so each device's full app list appears under `devices[].applications` in JSON output and within each device panel in table output. The `--application` filter now scopes per-device.

## [1.2.1] - 2026-04-17

### Fixed

- Fix table output summarizing list-of-dict fields as `[N items]` (GitHub issue #9). Columns like `pops` on `ipsec tunnels list` and `categories` on `intel url-lookup` now render the inline values (e.g. `ord1, atl1`) using a common identifying key (`name`, `display_name`, `label`, `title`, or `id`), with `, ... (N items)` for lists longer than 3. Falls back to `[N items]` only when no common key exists.

## [1.2.0] - 2026-04-15

### Added

- Add `dem users diagnose` composite command: one-shot diagnostic report combining user info, applications, device details, aggregated scores, and RCA from a ticket's user + time range. Supports `--include-npa` for NPA path analysis and `--application` to focus on a specific app.
- Add `dem users applications` command for `/api/v2/adem/users/getapplications` — list applications a user has accessed with experience scores
- Add `dem users device-details` command for `/api/v2/adem/users/device/getdetails` — detailed device info including client status/version, CPU, memory, OS, geo location, gateway, POP, public/private IPs
- Add `dem users npa-network-paths` command for `/api/v2/adem/users/npa/getnetworkpaths` — NPA network path graph showing nodes (DEVICE, GATEWAY, STITCHER, PUBLISHER, HOST) and edges with latency data
- Add unit tests for all new ADEM commands including diagnose partial-failure resilience

### Changed

- Update documentation: README, index.html, Claude Code skill, and CHANGELOG with full new command reference

## [1.1.0] - 2026-04-07

### Added

- Add 10 ADEM user/device telemetry commands under `dem users`: devices, info, locations, scores, exp-score, rca, network, npa-hosts, traceroute-ts, traceroute
- `dem users rca` provides CPU utilization, top processes, memory usage, and disk utilization — previously only available in the Netskope web UI
- Add Netskope Community support banner to README and documentation site

### Changed

- Update documentation: README, index.html, and Claude Code skill with full ADEM command reference

## [1.0.2] - 2026-04-02

### Fixed

- Fix README links: point Claude Code skills URL to https://code.claude.com/docs/en/skills and use full GitHub URL for netskope.md so it renders correctly on PyPI

## [1.0.1] - 2026-04-02

### Added

- Add troubleshooting guide for redacted user fields in alerts and events (API-side anonymization)
- Add troubleshooting subsection to Error Handling in documentation

## [1.0.0] - 2026-04-02

First public stable release. Promotes the CLI from beta to v1.0.0 with a stable command surface, comprehensive API coverage, and production-ready features.

### Added

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

### Fixed

- Thread configured CA bundle through browser-based login session validation so `netskope auth login` works behind Netskope SSL inspection
- Thread configured CA bundle through `netskope docs search` Algolia requests so documentation search works behind SSL inspection

### Security

- URL-encode all string-typed user inputs interpolated into API URL paths to prevent path traversal and parameter injection

## [0.2.27] - 2026-04-02

### Added

- Tag every command as `[read]` or `[write]` in `ntsk commands --flat` output so AI agents can distinguish safe queries from mutating operations
- Add `"mode"` and `"supports_yes_flag"` fields to `ntsk commands --flat --json` for programmatic safety checks
- Add `ntsk status --extended -o json` as a prominent help item
- Add "Write command safety" section to main help explaining `--yes` flag behavior

### Changed

- Promote `ntsk commands --flat --json` as the primary agent discovery command in `--help`

## [0.2.26] - 2026-04-02

Discoverability & Help Improvements (Round 2). Based on a real AI agent session that attempted to auto-discover and call every CLI subcommand.

### Added

- `ntsk commands --flat` prints only leaf (executable) commands, one per line with descriptions — the fastest way for scripts and AI agents to discover all 231 commands
- `ntsk commands --flat --json` outputs a flat JSON array for machine consumption
- Universal "did you mean?" hints on all group commands — invoking any group without a subcommand (e.g. `ntsk users`) now lists available subcommands after the help text
- `ntsk status --extended` / `-x` fetches additional resource counts: SCIM groups, URL lists, NPA policy rules, IPsec tunnels, RBAC roles, and IPS enabled status
- Added "Quick start for scripting / AI agents" section to `ntsk --help`
- Added DSPM cross-reference tip: "Run 'ntsk dspm list-types'" in the `resources` command help

### Changed

- `ntsk services cci` (no argument) now prints helpful guidance instead of "Missing argument", explaining the API requires an exact app name
- Expanded 403/404 error hints with endpoint-specific scope/license messages for RBAC, devices, IPsec, enrollment, events, notifications, ATP, DNS, and IPS
- Improved 403/404 fallback messages to reference Settings > Tools > REST API v2

## [0.2.25] - 2026-04-02

### Added

- Add background version update check — notifies users when a newer release is available on PyPI
- Auto-detects install method (pip, pipx, brew, uv) and shows the exact upgrade command
- Never blocks CLI startup — cache misses trigger a background daemon thread; notice appears on next invocation
- Suppress with `NETSKOPE_NO_UPDATE_CHECK=1`, `--quiet`, or non-TTY stderr

## [0.2.24] - 2026-04-02

Discoverability & Help Improvements. Based on feedback from an AI agent discovery session, 10 improvements to help text, error messages, and command discoverability.

### Added

- `ntsk commands` now shows positional argument signatures (e.g. `resources <RESOURCE_TYPE>`) in the tree
- `ntsk commands --json` outputs a machine-readable JSON tree of all commands, args, options, and descriptions — ideal for AI agent enumeration
- `ntsk dspm list-types` lists all valid DSPM resource types for the `resources` command
- `ntsk devices list --no-fallback` errors instead of silently falling back to `events client-status` with a different schema

### Changed

- `ntsk dspm analytics` help text now includes example metric types
- `ntsk npa policy list` now prints a helpful redirect to `rules list` and `groups list` instead of a generic error
- `ntsk steering config` (bare, no subcommand) now defaults to `get` instead of printing help
- `ntsk devices list` fallback warning now notes the schema difference
- `--count` help text clarified: returns fetched count (subject to `--limit`), not the true total
- 403 errors now include license/scope hints (e.g. "DEM requires a Digital Experience Management license and a 'DEM Admin' role")
- 404 error hints already existed; 403 hints now use the same path-based suggestion pattern

## [0.2.23] - 2026-04-01

### Added

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

### Changed

- Update README, interactive HTML guide, and AI Agent Skill with new DEM commands

## [0.2.22] - 2026-03-31

### Added

- Add `users groups members` command to list all users in a specific group by display name
- Add 19 unit tests for all new and modified user/group commands

### Changed

- Replace SCIM read-only commands with User Management API for richer data including group membership
- `users list` and `users get` now use `POST /api/v2/users/getusers` — returns `parentGroups`, `scimId`, `provisioner` per user
- `users groups list` and `users groups get` now use `POST /api/v2/users/getgroups` — returns `userCount`, `provisioner`, `deleted`
- `users get` now accepts email or username instead of SCIM UUID, with auto-detection
- `groups get` now accepts display name instead of SCIM UUID
- `--filter` on user/group queries now accepts JSON dict syntax with operators (`eq`, `in`, `sw`, `co`)
- SCIM CRUD commands (create/update/delete) unchanged — still use `/api/v2/scim/` endpoints
- Update AI Agent Skill, README, and interactive HTML guide with new User Management API commands and filter syntax

## [0.2.21] - 2026-03-06

### Added

- Add AI Agent Skill (`.claude/commands/netskope.md`) — a Claude Code `/netskope` slash command that teaches AI agents how to use every CLI command, with verified flags, field names, gotchas, and workflow patterns
- Add AI Agent Skill section to the interactive HTML guide with collapsible viewer and copy-to-clipboard button
- Add AI Agent Skill section to README with setup instructions and examples

### Changed

- Track `.claude/commands/` in git for shared agent skills

## [0.2.20] - 2026-03-06

### Added

- Add `alerts get` command — look up alerts by ID, user, app, name, type, severity, or activity without writing raw JQL
- Add `events get` command — look up events by ID, user, app, action, severity, policy, domain, source/destination IP, or hostname

### Changed

- Update README and interactive HTML guide with examples and documentation for the new `get` commands
- Update User Investigation Workflow in docs to use the new ergonomic `get` commands

## [0.2.19] - 2026-03-06

### Fixed

- Fix zsh/bash/fish shell completion (`ntsk completion install`) failing with `Error: 'COMP_WORDS'` when `add_completion=False` is set on the Typer app — Typer's custom completion classes were never registered, causing Click's default handler to run instead

## [0.2.18] - 2026-03-06

### Added

- Add interactive HTML guide with shadcn/Tailwind design, Mermaid architecture diagrams, real API response examples, and full command reference
- Publish guide as GitHub Pages at https://netskopeoss.github.io/netskope-cli/
- Add homepage and documentation URLs to pyproject.toml for PyPI display
- Add guide link to top of README.md

### Changed

- Set GitHub repo homepage to the guide URL

## [0.2.17] - 2026-03-06

### Added

- Add `--since` alias for `--period` on `status` command (e.g. `ntsk status --since 7d`)
- Add record count to stderr for CSV output (matching table/human behavior) for visibility when piping

### Changed

- Allow `intel url-lookup` to accept URL as a positional argument (e.g. `ntsk intel url-lookup google.com`) in addition to `--url`
- Auto-route `devices list` to `events client-status` endpoint when the devices API returns 404
- Clarify publishers command hierarchy: top-level `publishers` help now notes it's a shortcut for `npa publishers`

### Fixed

- Fix `--wide` / `-W` flag not working for events, incidents, and most other commands (only alerts had it wired up)

## [0.2.16] - 2026-03-06

### Changed

- Improve playwright missing error message: clarify that browser SSO is optional, show correct `netskope-cli[browser]` install command, and suggest API token auth as an alternative

## [0.2.15] - 2026-03-06

### Added

- Add `--group-by` alias for `--by` on `alerts summary` and `alerts list` for discoverability
- Add `--since` alias for `--start` on `alerts list` and `alerts summary` for common time-range queries

### Changed

- Update README: use `ntsk` shorthand in all examples, fix clone URL typos, add all missing command groups, document global flags and environment variables, fix shell completion syntax

### Fixed

- Fix `alerts summary` to show actual counts per group (API only returned unique values, now aggregates locally)
- Fix `-W` / `--wide` flag on alerts to show all columns (was being overridden by default field selection)
- Fix `_flatten_grouped_results` to handle API group-by responses that omit a count field

## [0.2.14] - 2026-03-06

### Added

- Add `--wide` / `-W` global flag to show all table columns without truncation
- Add `--desc` and `--asc` sort direction flags for `--order-by` on alerts and events commands
- Add `config setup` one-step wizard combining profile creation, tenant, and token setup

### Changed

- Auto-enable quiet mode (`-q`) when stdout is not a TTY (piped output), suppressing spinners automatically

### Fixed

- Fix pre-existing test failures in `test_status_cmd.py` (mock signature mismatch)

## [0.2.13] - 2026-03-06

### Added

- Add `completion` command for shell completion installation (bash, zsh, fish, PowerShell)

### Fixed

- Fix misleading "No matching records found" message in `alerts summary` when groupby field has no data

## [0.2.12] - 2026-03-06

### Added

- Add issue tracker link to README for bug reports and feature requests

## [0.2.11] - 2026-03-06

### Added

- Add SSL/TLS CA bundle support for environments with Netskope client SSL inspection
- New `config set-ca-bundle` command with auto-detection of Netskope CA certificates
- Support `NETSKOPE_CA_BUNDLE`, `REQUESTS_CA_BUNDLE`, `SSL_CERT_FILE` env vars for CA bundle resolution
- Add `SSLError` exception with actionable platform-specific fix suggestions

### Changed

- `doctor` command now checks CA bundle configuration and detects Netskope CA certs

### Fixed

- `status` command now passes cookies for session-based auth in async API calls

## [0.2.10] - 2026-03-06

### Fixed

- Fix repository URL typo in PyPI metadata

## [0.2.9] - 2026-03-06

### Added

- Add verbose logging support (-v for INFO, -vv for DEBUG) with HTTP request/response logging
- Add NETSKOPE_PROFILE env var support for profile resolution
- Add --offset alias for --start-index in user list command

### Changed

- Improve error handling: detect API-level errors in 200 responses and raise typed exceptions
- Replace typer.Exit with typed ConfigError exceptions for missing configuration

### Fixed

- Fix API endpoint corrections: infrastructure events, transaction event metrics, notification delivery settings, publisher upgrade profiles, URL list creation, and NSIQ URL lookup/recategorize request bodies
- Fix auth token-info to use config-aware token resolution

## [0.2.8] - 2026-03-06

### Added

- Add Homebrew tap installation support (`brew tap netskopeoss/tap && brew install netskope`)
- Add Homebrew install instructions to README

## [0.2.7] - 2026-03-05

### Added

- Initial public release on PyPI

[Unreleased]: https://github.com/netskopeoss/netskope-cli/compare/v1.4.8...HEAD
[1.4.8]: https://github.com/netskopeoss/netskope-cli/compare/v1.4.7...v1.4.8
[1.4.7]: https://github.com/netskopeoss/netskope-cli/compare/v1.4.6...v1.4.7
[1.4.6]: https://github.com/netskopeoss/netskope-cli/compare/v1.4.5...v1.4.6
[1.4.5]: https://github.com/netskopeoss/netskope-cli/compare/v1.4.4...v1.4.5
[1.4.4]: https://github.com/netskopeoss/netskope-cli/compare/v1.4.3...v1.4.4
[1.4.3]: https://github.com/netskopeoss/netskope-cli/compare/v1.4.2...v1.4.3
[1.4.2]: https://github.com/netskopeoss/netskope-cli/compare/v1.4.0...v1.4.2
[1.4.0]: https://github.com/netskopeoss/netskope-cli/compare/v1.3.1...v1.4.0
[1.3.1]: https://github.com/netskopeoss/netskope-cli/compare/v1.3.0...v1.3.1
[1.3.0]: https://github.com/netskopeoss/netskope-cli/compare/v1.2.1...v1.3.0
[1.2.1]: https://github.com/netskopeoss/netskope-cli/compare/v1.2.0...v1.2.1
[1.2.0]: https://github.com/netskopeoss/netskope-cli/compare/v1.1.0...v1.2.0
[1.1.0]: https://github.com/netskopeoss/netskope-cli/compare/v1.0.2...v1.1.0
[1.0.2]: https://github.com/netskopeoss/netskope-cli/compare/v1.0.1...v1.0.2
[1.0.1]: https://github.com/netskopeoss/netskope-cli/compare/v1.0.0...v1.0.1
[1.0.0]: https://github.com/netskopeoss/netskope-cli/compare/v0.2.28...v1.0.0
[0.2.28]: https://github.com/netskopeoss/netskope-cli/compare/v0.2.27...v0.2.28
[0.2.27]: https://github.com/netskopeoss/netskope-cli/compare/v0.2.26...v0.2.27
[0.2.26]: https://github.com/netskopeoss/netskope-cli/compare/v0.2.25...v0.2.26
[0.2.25]: https://github.com/netskopeoss/netskope-cli/compare/v0.2.24...v0.2.25
[0.2.24]: https://github.com/netskopeoss/netskope-cli/compare/v0.2.23...v0.2.24
[0.2.23]: https://github.com/netskopeoss/netskope-cli/compare/v0.2.22...v0.2.23
[0.2.22]: https://github.com/netskopeoss/netskope-cli/compare/v0.2.21...v0.2.22
[0.2.21]: https://github.com/netskopeoss/netskope-cli/compare/v0.2.20...v0.2.21
[0.2.20]: https://github.com/netskopeoss/netskope-cli/compare/v0.2.19...v0.2.20
[0.2.19]: https://github.com/netskopeoss/netskope-cli/compare/v0.2.18...v0.2.19
[0.2.18]: https://github.com/netskopeoss/netskope-cli/compare/v0.2.17...v0.2.18
[0.2.17]: https://github.com/netskopeoss/netskope-cli/compare/v0.2.16...v0.2.17
[0.2.16]: https://github.com/netskopeoss/netskope-cli/compare/v0.2.15...v0.2.16
[0.2.15]: https://github.com/netskopeoss/netskope-cli/compare/v0.2.14...v0.2.15
[0.2.14]: https://github.com/netskopeoss/netskope-cli/compare/v0.2.13...v0.2.14
[0.2.13]: https://github.com/netskopeoss/netskope-cli/compare/v0.2.12...v0.2.13
[0.2.12]: https://github.com/netskopeoss/netskope-cli/compare/v0.2.11...v0.2.12
[0.2.11]: https://github.com/netskopeoss/netskope-cli/compare/v0.2.10...v0.2.11
[0.2.10]: https://github.com/netskopeoss/netskope-cli/compare/v0.2.9...v0.2.10
[0.2.9]: https://github.com/netskopeoss/netskope-cli/releases/tag/v0.2.9
[0.2.8]: https://pypi.org/project/netskope/0.2.8/
[0.2.7]: https://pypi.org/project/netskope/0.2.7/
