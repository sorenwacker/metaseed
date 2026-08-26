"""`metaseed plugin` — the optional integration adapters and their settings.

The same registry and settings store the Plugins page renders
(:mod:`metaseed.adapters`, :class:`metaseed.settings.Settings`), so a value set
here is the value the web interface and the adapters read.
"""

from __future__ import annotations

from typing import Annotated

import typer

from metaseed import adapters
from metaseed.cli.output import ExitCode, echo_error, echo_success
from metaseed.cli.workspace import emit, parse_assignments
from metaseed.settings import Settings

app = typer.Typer(
    name="plugin", no_args_is_help=True, help="Optional integration adapters."
)


def _known(key: str) -> adapters.AdapterInfo:
    if not adapters.is_known(key):
        echo_error(
            f"'{key}' is not an adapter. Known: {', '.join(a.key for a in adapters.ADAPTERS)}."
        )
        raise typer.Exit(ExitCode.INPUT_ERROR)
    return adapters.get_adapter(key)


@app.command("list")
def list_plugins() -> None:
    """Every adapter: what it does, whether it is installed, enabled, configured."""
    settings = Settings()
    emit(
        [
            {
                "key": info.key,
                "name": info.name,
                "description": info.description,
                "direction": info.direction,
                "extra": info.extra,
                "installed": adapters.is_available(info),
                "enabled": settings.adapter_enabled(info.key),
                "config": {
                    field.key: ("(set)" if field.secret else value)
                    for field in info.config_fields
                    if (value := settings.get_adapter_config(info.key).get(field.key))
                },
            }
            for info in adapters.ADAPTERS
        ]
    )


@app.command("enable")
def enable(key: Annotated[str, typer.Argument(help="Adapter key")]) -> None:
    """Enable an adapter in this instance."""
    info = _known(key)
    try:
        Settings().set_adapter_enabled(key, True)
    except ValueError as exc:
        echo_error(str(exc))
        raise typer.Exit(ExitCode.CONFIG_ERROR) from exc
    echo_success(f"Enabled {info.name}.")


@app.command("disable")
def disable(key: Annotated[str, typer.Argument(help="Adapter key")]) -> None:
    """Disable an adapter in this instance."""
    info = _known(key)
    Settings().set_adapter_enabled(key, False)
    echo_success(f"Disabled {info.name}.")


@app.command("config")
def config(
    key: Annotated[str, typer.Argument(help="Adapter key")],
    set_: Annotated[
        list[str] | None,
        typer.Option("--set", "-s", help="Setting as name=value; repeatable"),
    ] = None,
) -> None:
    """Show or change an adapter's settings.

    A secret is never printed back; ``(set)`` says one is stored.
    """
    info = _known(key)
    settings = Settings()
    values = parse_assignments(set_)
    if not values:
        stored = settings.get_adapter_config(key)
        emit(
            {
                field.key: (
                    "(set)"
                    if field.secret and stored.get(field.key)
                    else stored.get(field.key)
                )
                for field in info.config_fields
            }
        )
        return
    unknown = sorted(set(values) - {field.key for field in info.config_fields})
    if unknown:
        echo_error(
            f"{info.name} has no setting {', '.join(unknown)}. "
            f"It takes: {', '.join(f.key for f in info.config_fields)}."
        )
        raise typer.Exit(ExitCode.INPUT_ERROR)
    settings.set_adapter_config(key, {k: str(v) for k, v in values.items()})
    echo_success(f"Set {', '.join(sorted(values))} for {info.name}.")


@app.command("check")
def check(key: Annotated[str, typer.Argument(help="Adapter key")]) -> None:
    """Run an adapter's connection check against its stored settings."""
    info = _known(key)
    if info.check_ref is None:
        echo_error(f"{info.name} has nothing to connect to.")
        raise typer.Exit(ExitCode.INPUT_ERROR)
    outcome = info.resolve_check()(Settings().get_adapter_config(key))
    typer.echo(outcome.message)
    for identifier, title in getattr(outcome, "projects", []) or []:
        typer.echo(f"  {identifier}  {title}")
    if not outcome.ok:
        raise typer.Exit(ExitCode.CONFIG_ERROR)
