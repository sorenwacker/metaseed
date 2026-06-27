"""DCAT card viewer route.

Renders the DCAT description ("catalog card") of the dataset currently loaded in
the editor, as Turtle and JSON-LD. A preview of the export feature (issues
#28/#30); read-only.
"""

from __future__ import annotations

import html
from typing import TYPE_CHECKING

from fastapi.responses import HTMLResponse

if TYPE_CHECKING:
    from collections.abc import Callable

    from fastapi import FastAPI

    from metaseed.ui.state import AppState


def _page(title: str, turtle: str, jsonld: str) -> str:
    """Render a minimal HTML page showing the two serializations."""
    return f"""<!doctype html>
<html><head><meta charset="utf-8"><title>DCAT card — {html.escape(title)}</title>
<style>
  body {{ font-family: system-ui, sans-serif; margin: 2rem; max-width: 70rem; }}
  h1 {{ font-size: 1.3rem; }} h2 {{ font-size: 1rem; margin-top: 1.5rem; }}
  pre {{ background: #f5f5f7; padding: 1rem; border-radius: 8px; overflow-x: auto;
        font-size: 0.85rem; line-height: 1.4; }}
  .hint {{ color: #555; }}
</style></head>
<body>
  <h1>DCAT card for <code>{html.escape(title)}</code></h1>
  <p class="hint">Catalog/discovery metadata derived from the dataset's root
  entity (and any explicit catalog metadata). This is what a data portal or a
  FAIR-assessment tool (F-UJI) would ingest.</p>
  <h2>Turtle</h2>
  <pre>{html.escape(turtle)}</pre>
  <h2>JSON-LD</h2>
  <pre>{html.escape(jsonld)}</pre>
</body></html>"""


def register_dcat_routes(app: FastAPI, get_state: Callable[[], AppState]) -> None:
    """Register the DCAT viewer route."""

    @app.get("/dcat", response_class=HTMLResponse)
    def dcat_card() -> HTMLResponse:
        from metaseed.dcat import build_dcat_catalog
        from metaseed.dcat.resolver import build_dcat_dataset_from_entities
        from metaseed.specs.loader import SpecLoader
        from metaseed.ui.datasets import get_current_dataset_name

        state = get_state()
        facade = state.get_or_create_facade()
        spec = SpecLoader(profile=facade.profile).load_profile(
            facade.version, facade.profile
        )
        name = get_current_dataset_name(state) or "dataset"

        dataset = build_dcat_dataset_from_entities(
            profile=facade.profile,
            root_entity_type=spec.root_entity,
            entities=facade.to_dict(),
            identifier=name,
        )
        catalog = build_dcat_catalog(
            title=spec.display_name or facade.profile,
            description=spec.description or None,
            datasets=[dataset],
        )

        try:
            from metaseed.dcat.serialize import to_jsonld, to_turtle

            turtle = to_turtle(catalog)
            jsonld = to_jsonld(catalog)
        except ModuleNotFoundError as exc:
            return HTMLResponse(
                f"<p>DCAT RDF serialization is unavailable: {html.escape(str(exc))}</p>",
                status_code=501,
            )

        return HTMLResponse(_page(name, turtle, jsonld))
