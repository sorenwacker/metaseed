"""DCAT card routes.

Describe the dataset currently loaded in the editor as a DCAT "catalog card"
(Turtle + JSON-LD):

- ``GET /api/dcat`` returns the card as JSON, used by the in-app DCAT panel.
- ``GET /dcat`` renders a standalone read-only page.

A preview of the export/exposure work (issues #28/#30).
"""

from __future__ import annotations

import html
from typing import TYPE_CHECKING

from fastapi import Form
from fastapi.responses import HTMLResponse, JSONResponse

if TYPE_CHECKING:
    from collections.abc import Callable

    from fastapi import FastAPI

    from metaseed.dcat.model import DcatDataset
    from metaseed.ui.state import AppState


def _build_card(state: AppState) -> tuple[DcatDataset, str, str]:
    """Resolve and serialize the DCAT card for the loaded dataset.

    Returns the dataset model plus its Turtle and JSON-LD serializations.
    Raises ModuleNotFoundError if the ``dcat`` extra (rdflib) is not installed.
    """
    from metaseed.api.client import MetaseedClient
    from metaseed.dcat.export import build_card
    from metaseed.dcat.model import DcatDataset
    from metaseed.dcat.serialize import to_jsonld, to_turtle
    from metaseed.ui.datasets import get_current_dataset_name

    facade = state.get_or_create_facade()
    name = get_current_dataset_name(state) or "dataset"

    # Resolved through the same builder the export action uses, so the page and
    # the downloaded file cannot describe the dataset differently.
    dataset = build_card(
        MetaseedClient.from_facade(facade),
        catalog_metadata=state.catalog_metadata,
        identifier=name,
    ) or DcatDataset(identifier=name, title=name)

    return dataset, to_turtle(dataset), to_jsonld(dataset)


def _page(dataset: DcatDataset, turtle: str, jsonld: str) -> str:
    """Render a standalone HTML page for the card."""
    heading = dataset.title or dataset.identifier or "dataset"
    return f"""<!doctype html>
<html><head><meta charset="utf-8"><title>DCAT card — {html.escape(heading)}</title>
<style>
  body {{ font-family: system-ui, sans-serif; margin: 2rem; max-width: 70rem; }}
  h1 {{ font-size: 1.3rem; }} h2 {{ font-size: 1rem; margin-top: 1.5rem; }}
  pre {{ background: #f5f5f7; padding: 1rem; border-radius: 8px; overflow-x: auto;
        font-size: 0.85rem; line-height: 1.4; }}
  .hint {{ color: #555; }}
</style></head>
<body>
  <h1>DCAT card: {html.escape(heading)}</h1>
  <p class="hint">Catalog/discovery metadata derived from the dataset's root
  entity (and any explicit catalog metadata) — what a data portal or a
  FAIR-assessment tool (F-UJI) would ingest.</p>
  <h2>Turtle</h2>
  <pre>{html.escape(turtle)}</pre>
  <h2>JSON-LD</h2>
  <pre>{html.escape(jsonld)}</pre>
</body></html>"""


def register_dcat_routes(app: FastAPI, get_state: Callable[[], AppState]) -> None:
    """Register the DCAT card routes."""

    @app.get("/api/dcat")
    def dcat_api() -> JSONResponse:
        state = get_state()
        try:
            dataset, turtle, jsonld = _build_card(state)
        except ModuleNotFoundError as exc:
            return JSONResponse({"error": str(exc)}, status_code=501)
        except Exception as exc:  # never leak a 500 stack trace to the client
            return JSONResponse(
                {"error": f"Could not build the DCAT card: {exc}"}, status_code=500
            )
        cm = state.catalog_metadata
        return JSONResponse(
            {
                "title": dataset.title,
                "identifier": dataset.identifier,
                "turtle": turtle,
                "jsonld": jsonld,
                # Echo the explicit metadata so the editor form can prefill.
                "metadata": {
                    "title": (cm.title if cm else None) or "",
                    "description": (cm.description if cm else None) or "",
                    "publisher": (cm.publisher if cm else None) or "",
                    "license": (cm.license if cm else None) or "",
                    "keywords": ", ".join(cm.keywords) if cm and cm.keywords else "",
                },
            }
        )

    @app.post("/api/dcat/metadata")
    def set_dcat_metadata(
        title: str = Form(""),
        description: str = Form(""),
        publisher: str = Form(""),
        license: str = Form(""),
        keywords: str = Form(""),
    ) -> JSONResponse:
        """Set explicit dataset-level catalog metadata for the DCAT card.

        Lets profiles whose root entity is not a dataset container (e.g. Darwin
        Core) supply title/description/publisher that cannot be derived.
        """
        from metaseed.repositories.dataset_repository import CatalogMetadata

        state = get_state()
        state.catalog_metadata = CatalogMetadata(
            title=title.strip() or None,
            description=description.strip() or None,
            publisher=publisher.strip() or None,
            license=license.strip() or None,
            keywords=[k.strip() for k in keywords.split(",") if k.strip()],
        )
        return JSONResponse({"status": "saved"})

    @app.get("/dcat", response_class=HTMLResponse)
    def dcat_card() -> HTMLResponse:
        try:
            dataset, turtle, jsonld = _build_card(get_state())
        except ModuleNotFoundError as exc:
            return HTMLResponse(
                f"<p>DCAT RDF serialization is unavailable: {html.escape(str(exc))}</p>",
                status_code=501,
            )
        except Exception as exc:
            return HTMLResponse(
                f"<p>Could not build the DCAT card: {html.escape(str(exc))}</p>",
                status_code=500,
            )
        return HTMLResponse(_page(dataset, turtle, jsonld))
