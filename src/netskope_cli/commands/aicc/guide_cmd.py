"""AICC in-CLI guide (``ntsk aicc guide``) — a self-documenting cheat sheet.

Printed reference covering the whole AICC command surface, its data model,
and the workflow patterns an operator (human or AI agent) needs. Keep this
in sync when adding AICC commands.
"""

from __future__ import annotations

import typer

from netskope_cli.commands.aicc._common import get_console

_GUIDE = """
[bold]AI Command Center (AICC) — CLI guide[/bold]

AICC discovers and risk-scores every AI touchpoint in your traffic:
[cyan]apps[/cyan] (generative-AI applications), [cyan]mcp[/cyan] (MCP servers agents connect to),
[cyan]agents[/cyan] (native AI agents installed on endpoints), [cyan]models[/cyan] (hosted + locally-run
models), [cyan]extensions[/cyan] (browser/editor/desktop AI extensions), and [cyan]identities[/cyan]
(the users — and unknown sources — behind all of it).

[bold]Data model in 30 seconds[/bold]
  • Every entity is keyed by its display [green]name[/green] (identities by [green]user_id[/green]: email or IP).
    Use the exact name from 'list' output in 'get'/'identities'/'trend' — quote spaces.
  • Risk scoring: [green]cci_score[/green] (0-100, Cloud Confidence Index) maps to [green]ccl[/green]
    (Poor <20, Low, Medium, High, Excellent >=80). Medium or below = not enterprise-ready.
  • Apps also carry [green]status[/green]: Sanctioned / Unsanctioned (CASB sanctioning).
  • Usage fields: uploaded_bytes, downloaded_bytes, sessions, transactions/events,
    identities/users, first_seen, last_seen.
  • [green]footprint[/green] shows where an entity runs (cloud_web, endpoint, ...). Its keys are
    the valid --type values for the 'deployments' subcommands.

[bold]Time windows[/bold] (all commands)
  --start/-s/--since and --end/-e accept '24h', '7d', '30d', ISO dates
  ('2026-06-01'), or epochs. Default window: last 7 days. The API stores a
  limited history — check 'ntsk aicc coverage' for the earliest available date.

[bold]Pagination & output[/bold]
  List commands: --limit/--offset for one page, --all for everything,
  --search for server-side name search, --sort-by/--sort-dir for server-side
  ordering, --fields for client-side column selection. Global -o json / csv /
  yaml works everywhere; piped output is JSON automatically.

[bold]Command map[/bold]
  ntsk aicc overview                                  one-call dashboard summary
  ntsk aicc coverage                                  earliest date with data
  ntsk aicc report --start 30d                        full AI Risk Report data bundle
  ntsk aicc apps|mcp|models|agents list               inventories
  ntsk aicc apps|mcp|models|agents get NAME           entity detail (+footprint)
  ntsk aicc apps|mcp|models|agents identities NAME    who uses it
  ntsk aicc apps|mcp|models|agents deployments NAME --type T
  ntsk aicc apps|mcp trend NAME --kind traffic|identity|risk
  ntsk aicc models|agents trend NAME                  traffic trend
  ntsk aicc apps|mcp violations NAME                  policy violations
  ntsk aicc apps status NAME                          CASB sanctioning check
  ntsk aicc identities list --type user|unknown       people & blind spots
  ntsk aicc identities get|trend|models|agents|mcp ID
  ntsk aicc extensions get|deployments|identities NAME --type browser_extension
  ntsk aicc analytics entities|counts|sums            KPIs (+trend vs prior window)
  ntsk aicc analytics breakdown ENTITY -d DIMENSION   charts / discover filter values
  ntsk aicc analytics alerts-matrix|alert-policies    alert triage
  ntsk aicc data-protection summary|violations PROVIDER   DLP posture (anthropic|mscopilot|chatgpt)

[bold]Workflow patterns[/bold]
  1. Shadow-AI review:
     ntsk aicc apps list --status Unsanctioned --ccl Poor --ccl Low --sort-by identities
  2. Who is riskiest:
     ntsk aicc identities list --type user --sort-by bytes --limit 10
     ntsk aicc identities get USER -o json
  3. Blind spots (unattributed usage):
     ntsk aicc identities list --type unknown --all -o json
  4. New this month:
     ntsk aicc apps list --first-seen-after 30d
  5. MCP governance:
     ntsk aicc mcp list --sort-by sessions; then mcp get / identities / violations
  6. Monthly AI Risk Report:
     ntsk aicc report --start 2026-06-01 --end 2026-06-30 --top 25 -o json > airr.json
  7. Discover valid filter values first:
     ntsk aicc analytics breakdown apps --dimension category

[bold]Gotchas[/bold]
  • Entity names are exact and case-sensitive; get them from 'list' (or --search).
  • 404s usually mean AICC isn't enabled or the token lacks the
    'ai_security_discovery' scope.
  • KPI 'trend' is % change vs the prior window of equal length; null when the
    prior window has no data.
  • Deployment --type must be a footprint key from 'get' — unknown types return [].
  • Totals can be big (DLP violations: tens of thousands). Filter before --all.
"""


def guide(ctx: typer.Context) -> None:
    """Print the AICC concepts, command map, workflows, and gotchas cheat sheet.

    A compact self-contained reference for humans and AI agents: the data
    model (CCI/CCL scoring, footprints, entity keys), time-window and
    pagination conventions, every subcommand, and proven workflow recipes.

    Examples:
        ntsk aicc guide
    """
    console = get_console(ctx)
    console.print(_GUIDE)
