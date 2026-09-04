# Netskope CLI

**[Read the full guide](https://netskopeoss.github.io/netskope-cli/)** | [Report an issue](https://github.com/netskopeoss/netskope-cli/issues)

> **Need help?** Support for the Netskope CLI is provided through the [Netskope Community](https://community.netskope.com/). Ask questions, share feedback, and connect with other Netskope users and experts.

The official command-line interface for the [Netskope](https://www.netskope.com/) platform. Manage your tenant, query events, investigate alerts, configure policies, and more — all from your terminal.

Available as both `netskope` and the shorter alias `ntsk`.

---

## Installation

### pip (all platforms)

```bash
pip install netskope
```

### Homebrew (macOS / Linux)

```bash
brew tap netskopeoss/tap
brew install netskope
```

### pipx (recommended — isolated install)

[pipx](https://pypa.github.io/pipx/) installs the CLI in its own virtual environment so it won't conflict with other Python packages.

```bash
# Install pipx if you don't have it
# macOS
brew install pipx && pipx ensurepath

# Linux
python3 -m pip install --user pipx && pipx ensurepath

# Windows
py -m pip install --user pipx && pipx ensurepath

# Then install Netskope CLI
pipx install netskope
```

### Windows

```powershell
# Using pip (requires Python 3.11+)
py -m pip install netskope

# Or using pipx
py -m pipx install netskope
```

### From source

```bash
git clone https://github.com/netskopeoss/netskope-cli.git
cd netskope-cli
pip install .
```

### Verify installation

```bash
ntsk --version
ntsk --help
```

---

## Quick Start

### 1. Configure your tenant

```bash
ntsk config set-tenant mytenant.goskope.com
```

### 2. Authenticate

**Option A — API token:**

```bash
export NETSKOPE_API_TOKEN="your-token"
```

**Option B — Browser SSO login:**

```bash
ntsk auth login
```

### 3. Start using the CLI

```bash
# Check setup and connectivity
ntsk doctor

# Tenant health overview
ntsk status

# Extended status with SCIM groups, URL lists, NPA rules, IPsec, RBAC, IPS
ntsk status --extended

# List recent alerts
ntsk alerts list --since 24h --limit 10

# Look up a specific alert by ID
ntsk alerts get f1c18fd0065a21e4ace54efb

# Find alerts for a specific user
ntsk alerts get --user alice@example.com --since 7d

# Alert summary by type
ntsk alerts summary --by severity

# Search events by type
ntsk events list --type alert --limit 20

# Look up events by user and app
ntsk events get --type application --user alice@example.com --since 7d

# Find blocked page events for a domain
ntsk events get --type page --domain example.com --action block

# List users (with group membership data)
ntsk users list

# Export incidents as CSV
ntsk incidents list -o csv > incidents.csv

# View URL lists used in policies
ntsk policy url-list list
```

---

## Output Formats

Every command supports multiple output formats via the `-o` / `--output` flag:

| Format   | Flag          | Description                          |
|----------|---------------|--------------------------------------|
| Table    | `-o table`    | Human-friendly table (default in TTY)|
| JSON     | `-o json`     | Pretty-printed JSON                  |
| JSONL    | `-o jsonl`    | One JSON object per line             |
| CSV      | `-o csv`      | Comma-separated values               |
| YAML     | `-o yaml`     | YAML output                          |

```bash
# Pipe JSON output to jq
ntsk alerts list -o json | jq '.[] | .alert_name'

# Export users to CSV
ntsk users list -o csv > users.csv
```

### Global Flags

| Flag           | Description                                        |
|----------------|----------------------------------------------------|
| `-W` / `--wide`| Show all table columns without truncation           |
| `--raw`        | Include internal `_`-prefixed fields in output      |
| `--count`      | Print the record count (subject to `--limit`)       |
| `--epoch`      | Keep timestamps as raw Unix epoch integers          |
| `-q` / `--quiet` | Suppress spinners and informational messages     |
| `--no-color`   | Disable coloured output                             |
| `-v` / `--verbose` | Increase verbosity (-vv for debug)              |
| `-f` / `--fields A,B` | Pick output fields on any command, in order. Dotted paths, `a[].b` lists, `*` globs |
| `--list-fields` | Show every field in the response (nested paths, type, presence, sample) instead of the records |
| `--where 'EXPR'` | Client-side JQL row filter (`eq ne gt ge lt le in like between and or not`) |
| `--sort FIELD[:desc]` | Client-side sort, comma-separated for several keys, missing values last |

### Querying results: discover, select, filter, sort

The four query flags above work on **every** command and never change the API request. They run on the rows the
command fetched, so `--limit` still applies. Hints and warnings go to stderr, so `-o json | jq` stays clean.

```bash
# 1. Discover: what fields does this response actually have?
ntsk devices list --list-fields
#   field                        type      present  sample                default
#   hostname                     str       100%     LAPTOP-7Q2            *
#   host_info.os                 str       100%     Windows
#   epdlp.criticalErrorsCount    str       61%      0
#   on_premises_detail[].match_ip str      12%      10.0.4.1
#   63 fields across 25 records · pick: --fields hostname,host_info.os · filter: --where 'hostname eq "..."'

# 2. Select: nested paths, list hops, globs, in the order you give them (quote globs in zsh)
ntsk devices list --fields hostname,host_info.os,host_info.os_version,last_event_timestamp
ntsk npa apps list --fields app_name,protocols[].port,service_publisher_assignments[].publisher_name -o csv
ntsk publishers list --fields 'publisher_name,assessment.version,capabilities.*'

# 3. Filter: the JQL syntax from `ntsk docs jql`, evaluated locally
ntsk devices list --where 'host_info.os like "win*" and epdlp.criticalErrorsCount gt 0'
ntsk publishers list --where 'status in ["disconnected","upgrading"]'
ntsk devices list --where 'idps eq null' --count          # counts the filtered rows

# 4. Sort, and combine everything
ntsk devices list --where 'host_info.os like "mac*"' --sort last_event_timestamp:desc \
                  --fields hostname,host_info.os_version -o csv > macs.csv
```

Unknown field names print a warning with close matches instead of silently blanking a column, and a `--where`
syntax error is reported (exit code 2) before any API call. Run `ntsk docs fields` for the full reference.

A few commands declare their **own** option with the same name; those are sent to the API and keep their original
meaning: `events`/`alerts`/`incidents --fields` (server-side projection) and `--query` (server-side JQL),
`dns`/`dspm`/`publishers --filter`, `dem ... --where` (DEM JSON syntax), `aicc ... --sort-by`. On those commands
use the server-side option to fetch less, and the global ones to shape what you got back.

---

## Commands

| Category              | Commands                                                   |
|-----------------------|------------------------------------------------------------|
| **Status & Setup**    | `doctor`, `tenant`, `status`, `status --extended`, `commands`, `commands --flat` |
| **AICC (AI Command Center)** | `aicc overview`, `aicc report`, `aicc guide`, `aicc apps\|mcp\|models\|agents list/get/identities/trend/violations`, `aicc identities list --type user\|unknown`, `aicc analytics breakdown`, `aicc data-protection summary` |
| **Events**            | `events get`, `events list --type alert\|application\|network\|...` |
| **Alerts**            | `alerts get`, `alerts list`, `alerts summary`, `alerts types` |
| **Incidents**         | `incidents list`, `incidents search`, `incidents update`, `incidents uci`, `incidents anomalies`, `incidents forensics`, `incidents notes list/add/delete` |
| **Users & RBAC**      | `users list`, `users get`, `users groups list`, `users groups members`, `rbac roles list` |
| **Policy**            | `policy url-list list`, `policy deploy`                    |
| **Auth & Config**     | `auth login`, `auth logout`, `config set-tenant`, `config set-token` |
| **Tokens**            | `tokens list`, `tokens create`, `tokens revoke`            |
| **Publishers**        | `publishers list`                                          |
| **NPA**               | `npa apps list`, `npa publishers list`, `npa policy list`  |
| **Steering**          | `steering private-apps list`, `steering config get`        |
| **Devices**           | `devices list`, `devices tags list`                        |
| **Enrollment**        | `enrollment list`, `enrollment create`                     |
| **IPSec**             | `ipsec tunnels list`, `ipsec pops list`                    |
| **DNS**               | `dns profiles list`, `dns categories`                      |
| **Services**          | `services cci APP_NAME`, `services tags list`              |
| **DSPM**              | `dspm resources list`, `dspm datastores list`              |
| **SPM**               | `spm inventory list`, `spm posture`                        |
| **ATP**               | `atp scan-file`, `atp scan-url`                            |
| **IPS**               | `ips status`, `ips allowlist list`                         |
| **Threat Intel**      | `intel url-lookup`, `intel recategorize`                   |
| **RBI**               | `rbi apps list`, `rbi browsers list`                       |
| **DEM**               | `dem metrics query`, `dem dataset query`, `dem sites summary`, `dem entities list`, `dem fields list`, `dem experience-alerts search`, `dem apps list`, `dem probes list` |
| **DEM User Telemetry**| `dem users diagnose`, `dem users devices`, `dem users device-details`, `dem users applications`, `dem users scores`, `dem users npa-network-paths`, `dem users rca` |
| **Notifications**     | `notifications templates list`                             |
| **Docs**              | `docs open`, `docs search`, `docs jql`, `docs fields`      |

Run `ntsk --help` or `ntsk <command> --help` for full details.

### Discoverability

```bash
ntsk commands                # Browse the full command tree with argument signatures
ntsk commands --flat         # All commands with [read]/[write] safety tags
ntsk commands --flat --json  # Flat JSON with mode + supports_yes_flag (best for agents)
ntsk commands --json         # Full JSON tree with args, options, and descriptions
ntsk dspm list-types         # List valid DSPM resource types
ntsk aicc guide              # AICC data model, command map, and workflow recipes
```

The `commands --flat` output lists every leaf command with `[read]`/`[write]` tags — the fastest way for a script or AI agent to discover all available commands and their safety level. The `--flat --json` variant adds `"mode"` and `"supports_yes_flag"` fields for programmatic use. Write commands prompt for confirmation; pass `--yes` to skip.

---

## Environment Variables

| Variable              | Description                                    |
|-----------------------|------------------------------------------------|
| `NETSKOPE_API_TOKEN`  | API v2 token for authentication                |
| `NETSKOPE_TENANT`     | Tenant hostname (overrides config file)        |
| `NETSKOPE_PROFILE`    | Configuration profile to use                   |
| `NETSKOPE_CA_BUNDLE`  | Custom CA bundle path (for SSL inspection)     |
| `NETSKOPE_WIDE`       | Set to `1` to show all table columns           |
| `NO_COLOR`            | Disable coloured output when set               |

```bash
# Check which values are active and their sources
ntsk config show
```

---

## Shell Completion

```bash
# Bash
ntsk completion install bash

# Zsh
ntsk completion install zsh

# Fish
ntsk completion install fish

# PowerShell
ntsk completion install powershell
```

---

## AI Agent Skill (Claude Code)

A ready-to-use [Claude Code skill](https://code.claude.com/docs/en/skills) is included at [`.claude/commands/netskope.md`](https://github.com/netskopeoss/netskope-cli/blob/master/.claude/commands/netskope.md). It teaches an AI agent how to use every `netskope` CLI command — including flags, field names, gotchas, and workflow patterns.

**Setup:** Copy the file into your project's `.claude/commands/` directory (or symlink it), then use the `/netskope` slash command in Claude Code:

```
/netskope show me high severity alerts from the last 24 hours
/netskope investigate user alice@example.com
/netskope export application events from last 7 days as CSV
```

The skill is also available as a copyable block in the [interactive guide](https://netskopeoss.github.io/netskope-cli/#ai-agent-skill).

---

## Requirements

- Python 3.11 or later
- A Netskope tenant with API access

---

## License

MIT
