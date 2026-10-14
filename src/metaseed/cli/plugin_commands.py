"""Registering the command groups that plugins contribute.

The core command line names no plugin. Each adapter that adds commands says so
with :attr:`metaseed.adapters.AdapterInfo.commands_ref`, and this module adds
that group under the adapter's key. A group is listed only while its plugin is
enabled and usable, the state the Plugins page shows; run otherwise, it names
what is missing instead of failing on an absent module.
"""

from __future__ import annotations

from collections.abc import Callable

import typer

from metaseed import adapters
from metaseed.cli.output import ExitCode, echo_error
from metaseed.settings import Settings


def register_plugin_groups(app: typer.Typer, settings: Settings) -> None:
    """Add every plugin's command group to ``app``.

    Args:
        app: The command line to extend.
        settings: Where each plugin's enabled state is read.
    """
    for info in adapters.all_adapters():
        if info.commands_ref is None:
            continue
        app.add_typer(
            info.resolve_commands(),
            name=info.key,
            hidden=not settings.adapter_enabled(info.key),
            callback=_require_enabled(info, settings),
        )


def _require_enabled(
    info: adapters.AdapterInfo, settings: Settings
) -> Callable[[], None]:
    """A group callback that stops with the missing step when the plugin is unusable."""

    def callback() -> None:
        if settings.adapter_enabled(info.key):
            return
        if not adapters.is_available(info):
            echo_error(
                f"the {info.name} plugin is not installed: "
                f"uv tool install 'metaseed[{info.extra}]' "
                f"(or pip install 'metaseed[{info.extra}]' in a virtual environment)"
            )
        else:
            echo_error(
                f"the {info.name} plugin is disabled: metaseed plugin enable {info.key}"
            )
        raise typer.Exit(ExitCode.CONFIG_ERROR)

    return callback
