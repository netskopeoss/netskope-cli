# Use the Netskope CLI

You are an expert at using the `netskope` CLI (alias: `ntsk`) to interact with a Netskope Security Cloud tenant. When the user asks you to query, investigate, or manage their Netskope tenant, use the CLI directly via shell commands.

## Input

$ARGUMENTS

## How to Run the CLI

The CLI is installed as `netskope` (or `ntsk`) on PATH. Just run it directly:
```bash
ntsk status
ntsk alerts list --limit 10
```

If the CLI is not on PATH (e.g. you get "command not found"), fall back to running from the source repo:
```bash
poetry run netskope <command>
```

## Authentication

**CRITICAL: Never hardcode credentials in files.** Use environment variables:
```bash
NETSKOPE_TENANT=<tenant> NETSKOPE_API_TOKEN=<token> ntsk <command>
```

Check if a profile is already configured: `ntsk config show`. If so, env vars are unnecessary.
If credentials are not configured and not provided, ask the user for their tenant name and API token.

## Global Options (apply to ALL commands)

These flags can appear **before or after** the subcommand:

| Flag | Description |
|------|-------------|
| `-o json\|table\|csv\|yaml\|jsonl` | Output format (default: table for TTY, json for piped) |
| `-W` / `--wide` | Show all table columns (no truncation) |
| `--count` | Print only the total record count |
| `-v` / `-vv` | Verbose / debug output |
| `-q` / `--quiet` | Suppress spinners and progress indicators (errors still print to stderr) |
| `--raw` | Include internal `_`-prefixed fields |
| `--epoch` | Keep timestamps as raw epoch integers |
| `--profile NAME` | Use a specific config profile |

**Always use `-o json` when you need to parse output programmatically.** Use table format for direct display to the user.

**Piping behavior:** When stdout is piped (not a TTY), the CLI **automatically outputs JSON** — you never need to add `-o json` when piping to `jq`, `python`, etc. It just works. Use `-o table` explicitly only if you want table format in a pipe.

**`--count` output format:**
- TTY: prints metadata lines + bare integer (e.g. `1616 results\nTime range: ...\n1616`)
- With `-o json`: prints just the bare integer (`1616`) — best for scripting
- For reliable scripting: `ntsk alerts list --start 24h --count -o json` gives a clean number

**`-q` behavior:** Suppresses spinners and progress indicators only. Errors still print to stderr. Exit codes are unchanged. Safe to use in scripts.

**Output size tip:** API responses can be large (100+ records, 500KB+). Always use `--limit` and `--fields`/`-f` to keep output manageable. Start with `--limit 5 -o json` for exploration, then increase as needed.

## `--fields` — Server-Side Field Projection

**IMPORTANT:** `--fields`/`-f` is a **server-side projection** — it tells the Netskope API which fields to return. This means:

1. **Not all response fields are valid `--fields` values.** Some fields that appear in the full response (e.g. `dlp_file`, `dlp_match_info` for incidents) are **not accepted** by the API as projection fields and will cause a 400 error.
2. **If you get a 400 "unrecognized field" error**, drop the offending field from `--fields` and retry, or omit `--fields` entirely to get all fields and filter client-side with `jq`.
3. **Safe common fields** that work across most event types: `user`, `app`, `activity`, `object`, `timestamp`, `severity`, `srcip`, `action`, `incident_id`, `alert_name`, `alert_type`

**Fallback pattern when `--fields` fails:**
```bash
# Instead of --fields with potentially invalid names:
ntsk incidents list --start 7d --limit 10 -o json | jq '[.[] | {user, app, severity, object, dlp_file}]'
```

## Parsing JSON Output

**Prefer `jq` over inline Python** for extracting fields from JSON output. Python one-liners with escaped quotes are fragile in zsh/bash. Use `jq` instead:

```bash
# Extract field values
ntsk alerts list --start 24h | jq '.[].alert_name'

# Select specific fields from full output
ntsk incidents list --start 7d --limit 10 | jq '[.[] | {user, app, severity, object}]'

# Count by field value
ntsk alerts list --start 7d | jq 'group_by(.alert_type) | map({type: .[0].alert_type, count: length})'

# Filter results
ntsk alerts list --start 7d | jq '[.[] | select(.severity == "high" or .severity == "High")]'
```

Note: piped output is automatically JSON, so `-o json` is optional in these examples.

## Command Reference

### Quick Health Check
```bash
ntsk status                          # Tenant overview dashboard (alerts, publishers, events)
ntsk status --since 7d               # Events in last 7 days
ntsk doctor                          # Diagnose CLI setup issues
ntsk tenant                          # Show tenant info & connectivity
```

### Security Alerts

Alerts are security events like SPM assessments, policy violations, anomalies, and threat detections. They come from the datasearch API.

**Time flag:** `--start` or `--since` (both work, they are aliases). Short form: `-s`.

```bash
# List alerts
ntsk alerts list --limit 25
ntsk alerts list --start 7d --query 'severity eq "high"'
ntsk alerts list --query 'alert_type eq "DLP"' -o json
ntsk alerts list --start 24h --type DLP              # --type is shorthand for alert_type filter
ntsk alerts list --start 7d --fields alert_name,alert_type,severity,app,timestamp -o json

# Get specific alert by ID or filters
ntsk alerts get <alert_id>
ntsk alerts get --user alice@example.com --since 7d
ntsk alerts get --app Slack --type DLP
ntsk alerts get --severity high --since 24h

# Summarize alerts (aggregate by field)
ntsk alerts summary                              # Defaults: group by alert_type, last 24h
ntsk alerts summary --by severity --since 7d     # Use --by or --group-by (NOT --field)
ntsk alerts summary --by app --query 'severity eq "high"'
ntsk alerts types                                # List known alert types
```

**Key alert response fields:** `_id`, `alert_name`, `alert_type`, `sa_rule_severity` (for SPM alerts), `app`, `user`, `action`, `activity`, `policy`, `status`, `cci`, `ccl`, `timestamp`, `timestamp_iso`, `compliance_standards`, `rule_labels`

**Safe `--fields` values for alerts:** `alert_name`, `alert_type`, `severity`, `app`, `user`, `action`, `activity`, `timestamp`, `cci`, `ccl`, `policy`, `status`

**Severity casing warning:** The API returns severity values with inconsistent casing (e.g. both `"high"` and `"High"`). Use case-insensitive matching when filtering or aggregating. JQL `eq` is case-sensitive, so `--query 'severity eq "high"'` won't match `"High"`. For reliable severity filtering, use `alerts summary --by severity` to see actual values first, or filter client-side with `jq`.

**Note on `--group-by` in `alerts list`:** This sends a server-side aggregation. It may return empty `[]` for some field combinations — an API limitation. Use `alerts summary --by <field>` instead for reliable aggregation (client-side).

### Events (Unified Query Interface)

Events are the raw activity log. Each event type has its own subcommand.

**Shared options for all event subcommands:**
- `--query JQL` — JQL filter string
- `--fields field1,field2` / `-f` — server-side field projection (see `--fields` section above)
- `--start TIME` / `-s` — start time (`24h`, `7d`, `1h`, or epoch)
- `--end TIME` / `-e` — end time
- `--limit N` / `-l` — max records (default 25)
- `--group-by FIELD` — aggregate by field
- `--order-by FIELD` — sort field
- `--desc` / `--asc` — sort direction

```bash
ntsk events alerts --start 24h --limit 50
ntsk events application --start 7d --query 'app eq "Slack"' --fields user,activity,app,timestamp
ntsk events network --start 1h --fields srcip,dstip,app,action,dstport
ntsk events page --start 24h --query 'category eq "Malware"'
ntsk events incident --start 7d
ntsk events audit --start 7d --query 'user eq "admin@example.com"'
ntsk events infrastructure --start 24h
ntsk events client-status --start 24h
ntsk events epdlp --start 7d
ntsk events transaction --start 24h

# Unified interface (requires --type/-t)
ntsk events list --type application --start 24h

# Get event by ID or filters
ntsk events get <event_id>
ntsk events get --user alice@example.com --type application --start 7d
```

**Key response fields by event type:**
- **application:** `user`, `app`, `activity`, `object`, `object_type`, `srcip`, `src_country`, `browser`, `os`, `instance_id`, `cci`, `ccl`
- **network:** `user`, `app`, `srcip`, `dstip`, `dstport`, `dsthost`, `protocol`, `action`, `policy`, `numbytes`, `session_duration`, `publisher_name`
- **alerts (event):** same as Security Alerts above
- **incident:** same as Incidents below (DLP-focused)

**JQL Syntax Quick Reference:**
- `field eq "value"` — equals (case-sensitive)
- `field ne "value"` — not equals
- `field gt 100` / `field lt 100` — comparisons
- `field in ["a","b"]` — in list
- Combine with `AND`, `OR`: `'severity eq "high" AND app eq "Slack"'`
- Run `ntsk docs jql` for full reference

### Incidents

Incidents are **DLP-focused** events — file policy violations with forensic data, match info, and file metadata. They are distinct from alerts (which cover threat detections, anomalies, SPM assessments, etc.).

**Time flag:** `--start` / `-s` (NOT `--since`). Default: last 24h. Default limit: 100 (can be 500KB+ of JSON — always set `--limit`).

```bash
ntsk incidents list --limit 25                          # Always set --limit to avoid huge output
ntsk incidents list --start 7d --limit 25
ntsk incidents list --query 'severity eq "critical"' --start 7d --limit 25
ntsk incidents list --count                             # Just the count

# For field selection, omit --fields and use jq (many incident field names cause API 400 errors):
ntsk incidents list --start 7d --limit 10 | jq '[.[] | {incident_id, user, app, object, severity}]'

# Safe --fields values for incidents (verified):
ntsk incidents list --fields incident_id,user,app,object,severity,timestamp --limit 10 -o json

ntsk incidents search --query 'severity eq "high"' --start 24h   # --query is REQUIRED here
ntsk incidents uci --user alice@example.com             # User Confidence Index
ntsk incidents anomalies --user alice@example.com       # UBA anomalies
ntsk incidents forensics <dlp_incident_id>              # DLP forensic data
ntsk incidents update <id> --status "Closed" --comment "Resolved"
```

**Key incident response fields:** `_id`, `incident_id`, `dlp_incident_id`, `dlp_incident_severity`, `dlp_file`, `dlp_match_info`, `user`, `app`, `activity`, `object`, `url`, `domain`, `file_type`, `file_size`, `md5`, `sha256`, `severity`, `status`, `srcip`, `src_country`, `forensic_data`

**Safe `--fields` values for incidents:** `incident_id`, `user`, `app`, `object`, `severity`, `timestamp`, `srcip`, `status`, `domain`, `activity`

**Alerts vs Incidents — when to use which:**
| Use case | Command |
|----------|---------|
| Threat detections, malware, anomalies | `ntsk alerts list` |
| SPM/posture assessment failures | `ntsk alerts list --type "Security Assessment"` |
| DLP policy violations, file incidents | `ntsk incidents list` |
| All security events broadly | `ntsk events alerts` |

### Cloud Confidence Index (CCI)
```bash
ntsk services cci Slack              # Look up app risk score
ntsk services cci "Google Drive"     # Quoted if spaces
ntsk services tags list              # List service tags
ntsk services publishers list        # List publishers
ntsk services private-apps list      # List private apps
```

### Policy Management
```bash
ntsk policy url-list list
ntsk policy url-list get <id>
ntsk policy url-list create "BlockList" --urls "bad.com,evil.org" --type exact
ntsk policy url-list update <id> --urls "new.com,updated.org"
ntsk policy url-list delete <id>
ntsk policy deploy                   # Deploy pending changes
```

### User & Group Management
```bash
# Query users (User Management API — includes group membership)
ntsk users list --limit 50
ntsk users list --filter '{"and": [{"emails": {"eq": "alice@example.com"}}]}'
ntsk users list --filter '{"accounts.active": {"eq": true}}'
ntsk users get alice@example.com                        # Look up by email
ntsk users get alice --by username                      # Look up by username

# Query groups (User Management API — includes userCount)
ntsk users groups list
ntsk users groups list --filter '{"deleted": {"eq": false}}'
ntsk users groups get "Engineering"                     # Look up by display name

# List group members
ntsk users groups members "Engineering" --limit 100
ntsk users groups members "Sales Team" -o json

# SCIM CRUD (provisioning — unchanged, uses /api/v2/scim/)
ntsk users create --username alice@example.com --email alice@example.com
ntsk users update <scimId> --set active=false
ntsk users delete <scimId>
ntsk users groups create "Engineering"
ntsk users groups update <scimId> --name "New Name"
ntsk users groups delete <scimId>
```

**User Management API filter syntax:** `--filter` accepts a JSON dict with operators `eq`, `in`, `sw`, `co`.
- User filterable fields: `userName`, `emails`, `accounts.deleted`, `accounts.active`, `accounts.parentGroups`, `accounts.ou`, `accounts.provisioner`, `accounts.collectionId`
- Group filterable fields: `id`, `scimId`, `deleted`, `collectionId`, `parentGroups`, `idps`
- Common patterns:
  - Find by email: `'{"and": [{"emails": {"eq": "user@example.com"}}]}'`
  - Active users: `'{"accounts.active": {"eq": true}}'`
  - Users in group: `'{"accounts.parentGroups": {"in": ["Engineering"]}}'` or use `ntsk users groups members "Engineering"`
  - Non-deleted groups: `'{"deleted": {"eq": false}}'`

**Note:** SCIM CRUD commands (create/update/delete) use scimId (UUID), which is available in the `scimId` field of query results. Query commands (list/get/members) use the User Management API which returns richer data including `parentGroups`.

### Publishers & Private Access
```bash
ntsk publishers list
ntsk publishers get <id>
ntsk publishers create --name "US-East"
ntsk publishers delete <id>

# NPA (Netskope Private Access) — deep management
ntsk npa apps list
ntsk npa apps get <id>
ntsk npa publishers list
ntsk npa tags list
ntsk npa policy rules list
ntsk npa policy groups list
ntsk npa search "wiki"
```

### Steering, IPsec, DNS, Devices
```bash
ntsk steering private-apps list
ntsk steering config get

ntsk ipsec tunnels list
ntsk ipsec pops list

ntsk dns profiles list
ntsk dns categories
ntsk dns groups list

ntsk devices list --limit 50
ntsk devices tags list
ntsk devices supported-os
```

### DSPM & SPM
```bash
ntsk dspm resources list --type datastores
ntsk dspm analytics --type overview

ntsk spm posture-score
ntsk spm apps list
ntsk spm inventory --limit 50
ntsk spm rules list
ntsk spm changes
```

### Threat Protection & Intelligence
```bash
ntsk atp scan-file /path/to/file.exe
ntsk atp scan-url "https://suspicious.example.com"
ntsk atp submission <submission_id>

ntsk intel url-lookup "https://example.com"
ntsk intel url-recategorize "https://example.com" --category "Malware"
ntsk intel false-positive "https://example.com"

ntsk ips status
ntsk ips allowlist list
ntsk ips signatures --limit 20
```

### Administration
```bash
ntsk rbac roles list
ntsk rbac admins list
ntsk tokens list
ntsk tokens create --name "CI/CD Token"
ntsk tokens revoke <id>
ntsk notifications templates list
ntsk dem probes list
ntsk dem alerts list
```

### DEM (Digital Experience Monitoring)

DEM provides user experience metrics, alert instances, entity lookups, and monitored app visibility.

```bash
# Discover available fields per data source (start here)
ntsk dem fields list
ntsk dem fields list --source rum_steered

# Query metrics — 17 data sources (ux_score, rum_steered, http_steered, traceroute_pop, agent_status, etc.)
# --select uses JSON with aggregation: '{"alias": ["avg", "metric"]}'
# --where uses operator-first format: '["=", "field", ["$", "value"]]'
# --begin/--end are epoch MILLISECONDS
ntsk dem metrics query -d ux_score \
    --select '["user_id", {"avg_score": ["avg", "score"]}, {"avg_device": ["avg", "device_score"]}]' \
    --groupby user_id --begin 1711929600000 --end 1712016000000 --limit 25

ntsk dem metrics query -d rum_steered \
    --select '["user_id", "application_name"]' \
    --where '["=", "user_id", ["$", "john@example.com"]]' \
    --begin 1711929600000 --end 1712016000000

# List users with experience scores (epoch SECONDS, max 48h window)
ntsk dem entities list --start-time 1710000000 --end-time 1710086400 --limit 25
ntsk dem entities list --start-time 1710000000 --end-time 1710086400 \
    --exp-score '0~30' --applications 'Google Gmail,Twitter'

# Query agent/client connection states (no time range — always current state)
ntsk dem states query -d agent_status -s '["user_id", "status", "agent_version"]' --limit 100
ntsk dem states query -d client_status -s '["user_id"]'

# Traceroute path data (no limit support — use where filters to control size)
ntsk dem traceroute query -d traceroute_pop \
    --where '["=", "user_id", ["$", "john@example.com"]]' \
    --begin 1711929600000 --end 1712016000000

# Search triggered alert instances (not alert rules)
ntsk dem experience-alerts search --severity critical,high --limit 10
ntsk dem experience-alerts search --alert-category 'Network,User Experience'

# Get alert details and impacted entities
ntsk dem experience-alerts get ALERT_ID
ntsk dem experience-alerts entities ALERT_ID --limit 25

# List DEM-monitored applications
ntsk dem apps list
ntsk dem apps list --type predefined --limit 50
```

**DEM Key Concepts:**
- **Data sources for metrics:** ux_score, rum_steered, rum_bypassed, http_steered, http_bypassed, traceroute_pop, traceroute_bypassed, agent_status, client_status, npa_gateway, npa_metric, npa_stitcher, and more (17 total)
- **Valid state sources:** Only `agent_status` and `client_status` (use `dem metrics query` for others)
- **Valid traceroute sources:** Only `traceroute_pop` and `traceroute_bypassed`
- **UX Score fields:** score, device_score, network_score, application_tcp_score, application_http_score (all 0-100)
- **Time units:** `metrics query` and `traceroute query` use epoch **milliseconds**; `entities list` uses epoch **seconds**
- **exp_score format:** Integer ranges with `~` separator: `"0~30"` (poor), `"31~70"` (fair), `"71~100"` (good)
- **select aggregation:** Metrics require `{"alias": ["avg", "metric_name"]}` syntax; keys (user_id, hostname) used directly
- **where clause:** Operator-first: `["=", "field", ["$", "string_value"]]`. Combiners: `["and", [...], [...]]`
- **Alert categories:** Network, Platform, Private Apps, User Experience, Site
- **Alert severities:** info, low, medium, high, critical

### Configuration Management
```bash
ntsk config show                     # Current profile config
ntsk config profiles                 # List all profiles
ntsk config setup                    # Interactive wizard
ntsk config test                     # Test connectivity
ntsk config set-tenant mycompany     # Set tenant (auto-appends .goskope.com)
ntsk config set-token                # Store token (prompts securely)
ntsk config use-profile staging      # Switch profiles
ntsk config create-profile staging   # Create new profile
```

### Misc
```bash
ntsk commands                        # Print full command tree
ntsk completion install zsh          # Install shell completion
ntsk docs jql                        # JQL syntax reference
ntsk docs api                        # API reference link
```

## Workflow Patterns

### Investigation Workflow
1. Start broad: `ntsk status --since 24h`
2. Drill into alerts: `ntsk alerts list --start 24h --query 'severity eq "high"' --limit 10 -o json`
3. Get specifics: `ntsk alerts get <id> -o json`
4. Check user activity: `ntsk events application --start 24h --query 'user eq "suspect@co.com"' --limit 20 | jq '[.[] | {user, app, activity, srcip, timestamp_iso}]'`
5. Check DLP incidents: `ntsk incidents list --start 7d --limit 25 | jq '[.[] | select(.user == "suspect@co.com") | {object, severity, app, dlp_file}]'`

### Counting Records
```bash
ntsk alerts list --start 24h --count -o json       # Bare integer output
ntsk incidents list --start 7d --count -o json
ntsk events alerts --start 7d --count -o json
```

### Bulk Data Export
```bash
ntsk events application --start 7d --limit 10000 -o csv > events.csv
ntsk alerts list --start 30d --limit 5000 -o jsonl > alerts.jsonl
```

## Important Notes

1. **Time flags:** `alerts list/get/summary` accept both `--start` and `--since` (aliases). `incidents list/search` and `events` subcommands use `--start`/`-s` only.
2. **Default limits:** `alerts list` defaults to 25. `incidents list` defaults to 100 (can be huge). Always set `--limit` explicitly.
3. **Output size:** Use `--limit` to cap records. Use `jq` for client-side field filtering (safer than `--fields`). Start small (`--limit 5`) when exploring.
4. **`--fields` is server-side** and rejects unknown field names with HTTP 400. When in doubt, omit `--fields` and use `jq` to filter client-side.
5. **JQL is case-sensitive.** Severity values have inconsistent casing (`"high"` vs `"High"`). Check actual values with `alerts summary --by severity` first.
6. **JQL queries** must be single-quoted in the shell: `--query 'field eq "value"'`
7. **Piping:** Output auto-switches to JSON when piped. You never need `-o json` explicitly when piping.
8. **No auto-pagination:** The CLI sends a single API request with your `--limit` value. There is no automatic multi-page fetching for events/alerts/incidents. The API may cap results regardless of `--limit`.
9. **License-dependent features:** DSPM, SPM, RBI, IPS, DEM require the corresponding license. A 404 usually means the feature is not licensed on this tenant.
10. **`events list` requires `--type`/`-t`.** Prefer the specific subcommands (`events alerts`, `events application`) instead.
11. **`alerts summary` uses `--by` or `--group-by`** (NOT `--field`). Example: `ntsk alerts summary --by severity --since 7d`

Now, understand the user's request in "$ARGUMENTS" and use the CLI to accomplish it. If the request is ambiguous, ask what they want. Prefer `-o json` for your own parsing, and table format for direct display to the user. Always show the commands you're running so the user can learn.
