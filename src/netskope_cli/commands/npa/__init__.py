"""Netskope Private Access (NPA) command group.

Consolidates all NPA functionality: private apps, publishers, tags,
NPA policy rules/groups, local brokers, upgrade profiles, discovery,
alerts configuration, and resource search.
"""

from __future__ import annotations

import typer

# ---------------------------------------------------------------------------
# Top-level NPA app
# ---------------------------------------------------------------------------
npa_app = typer.Typer(
    name="npa",
    help=(
        "Netskope Private Access — manage your ZTNA infrastructure.\n\n"
        "Provides full management of private applications, publishers, NPA policy "
        "rules and groups, private app tags, local brokers, upgrade profiles, "
        "discovery settings, and publisher alerts configuration."
    ),
    no_args_is_help=True,
)

# ---------------------------------------------------------------------------
# Register sub-apps
# ---------------------------------------------------------------------------
from netskope_cli.commands.npa.alerts_config_cmd import alerts_config_app  # noqa: E402
from netskope_cli.commands.npa.app_publishers_cmd import app_publishers_app  # noqa: E402
from netskope_cli.commands.npa.apps_cmd import apps_app  # noqa: E402
from netskope_cli.commands.npa.discovery_cmd import discovery_app  # noqa: E402
from netskope_cli.commands.npa.policy_cmd import policy_app  # noqa: E402
from netskope_cli.commands.npa.publishers_cmd import publishers_app  # noqa: E402
from netskope_cli.commands.npa.search_cmd import search_resources, validate_name  # noqa: E402
from netskope_cli.commands.npa.tags_cmd import tags_app  # noqa: E402

npa_app.add_typer(apps_app, name="apps", help="Manage NPA private applications.")
npa_app.add_typer(tags_app, name="tags", help="Manage private application tags.")
npa_app.add_typer(app_publishers_app, name="app-publishers", help="Manage app-publisher associations.")
npa_app.add_typer(policy_app, name="policy", help="Manage NPA policy rules and groups.")
npa_app.add_typer(publishers_app, name="publishers", help="Manage publishers, upgrade profiles, and local brokers.")
npa_app.add_typer(discovery_app, name="discovery", help="Manage private app discovery settings.")
npa_app.add_typer(alerts_config_app, name="alerts-config", help="Manage publisher alert configuration.")

# Top-level commands on npa_app
npa_app.command("validate-name", help="Validate a resource name for uniqueness.")(validate_name)
npa_app.command("search", help="Search NPA resources by query.")(search_resources)

__all__ = ["npa_app"]
