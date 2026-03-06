# Netskope CLI

> **Found a bug or have a feature request?** Please file an issue at [github.com/netskopeoss/netskope-cli/issues](https://github.com/netskopeoss/netskope-cli/issues).

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

# List recent alerts
ntsk alerts list --since 24h --limit 10

# Alert summary by type
ntsk alerts summary --by severity

# Search events by type
ntsk events list --type alert --limit 20

# List SCIM users
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
| `--count`      | Print only the total record count                   |
| `--epoch`      | Keep timestamps as raw Unix epoch integers          |
| `-q` / `--quiet` | Suppress spinners and informational messages     |
| `--no-color`   | Disable coloured output                             |
| `-v` / `--verbose` | Increase verbosity (-vv for debug)              |

---

## Commands

| Category              | Commands                                                   |
|-----------------------|------------------------------------------------------------|
| **Status & Setup**    | `doctor`, `tenant`, `status`, `commands`                   |
| **Events**            | `events list --type alert\|application\|network\|...`      |
| **Alerts**            | `alerts list`, `alerts summary`, `alerts types`            |
| **Incidents**         | `incidents list`, `incidents search`, `incidents uci`      |
| **Users & RBAC**      | `users list`, `users groups list`, `rbac roles list`       |
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
| **DEM**               | `dem app-probes list`, `dem network-probes list`           |
| **Notifications**     | `notifications templates list`                             |
| **Docs**              | `docs open`, `docs search`, `docs jql`                     |

Run `ntsk --help` or `ntsk <command> --help` for full details.

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

## Requirements

- Python 3.11 or later
- A Netskope tenant with API access

---

## License

MIT
