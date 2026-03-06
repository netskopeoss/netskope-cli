# Netskope CLI

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
git clone https://github.com/netSkopeoss/netksope-cli.git
cd netksope-cli
pip install .
```

### Verify installation

```bash
netskope --version
ntsk --help
```

---

## Quick Start

### 1. Configure your tenant

```bash
netskope config set-tenant mytenant.goskope.com
```

### 2. Authenticate

**Option A — API token:**

```bash
export NETSKOPE_API_TOKEN="your-token"
```

**Option B — Browser SSO login:**

```bash
netskope auth login
```

### 3. Start using the CLI

```bash
# Check tenant connectivity and status
ntsk status

# List recent alerts
ntsk alerts list --limit 10

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

---

## Commands

| Category         | Commands                                                   |
|------------------|------------------------------------------------------------|
| **Status**       | `status`                                                   |
| **Events**       | `events list --type alert\|application\|network\|...`      |
| **Alerts**       | `alerts list`                                              |
| **Incidents**    | `incidents list`, `incidents search`, `incidents uci`      |
| **Users**        | `users list`, `users groups list`                          |
| **Policy**       | `policy url-list list`, `policy deploy`                    |
| **Auth**         | `auth login`, `auth logout`, `auth status`                 |
| **Config**       | `config set-tenant`, `config set-token`, `config show`     |
| **Publishers**   | `publishers list`                                          |
| **Steering**     | `steering private-apps list`, `steering config get`        |
| **IPSec**        | `ipsec tunnels list`, `ipsec pops list`                    |
| **Services**     | `services cci APP_NAME`, `services tags list`              |
| **DNS**          | `dns profiles list`, `dns categories`                      |
| **Docs**         | `docs open`, `docs search`, `docs jql`                     |

Run `ntsk --help` or `ntsk <command> --help` for full details.

---

## Environment Variables

| Variable             | Description                              |
|----------------------|------------------------------------------|
| `NETSKOPE_API_TOKEN` | API v2 token for authentication          |
| `NETSKOPE_TENANT`    | Tenant hostname (overrides config file)  |
| `NETSKOPE_PROFILE`   | Configuration profile to use             |

```bash
# Check which values are active and their sources
netskope config show
```

---

## Shell Completion

```bash
# Bash
netskope --install-completion bash

# Zsh
netskope --install-completion zsh

# Fish
netskope --install-completion fish

# PowerShell
netskope --install-completion powershell
```

---

## Requirements

- Python 3.11 or later
- A Netskope tenant with API access

---

## License

MIT
