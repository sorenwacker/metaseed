"""Routes for markdown notes functionality."""

from collections.abc import Callable

from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from metaseed.ui.notes_filesystem import NotesFilesystem
from metaseed.ui.state import AppState


def register_notes_routes(
    app: FastAPI,
    templates: Jinja2Templates,
    _get_state: Callable[[], AppState],
    notes_fs: NotesFilesystem | None = None,
    base_url: str = "",
) -> None:
    """Register notes-related routes.

    Args:
        app: FastAPI application instance.
        templates: Jinja2 templates instance.
        _get_state: Function to get app state (unused, kept for API consistency).
        notes_fs: Optional NotesFilesystem instance. If not provided, uses default.
        base_url: Base URL prefix for the application (e.g., "/hub").
    """
    if notes_fs is None:
        notes_fs = NotesFilesystem()

    @app.get("/notes/", response_class=HTMLResponse)
    async def notes_index(request: Request) -> HTMLResponse:
        """List all notes."""
        notes = notes_fs.list_notes()
        return templates.TemplateResponse(
            request,
            "notes/index.html",
            {
                "notes": notes,
                "base_url": base_url,
            },
        )

    @app.get("/notes/new", response_class=HTMLResponse)
    async def new_note(request: Request) -> HTMLResponse:
        """Create new note form."""
        return templates.TemplateResponse(
            request,
            "notes/edit.html",
            {
                "note_name": "",
                "content": "",
                "is_new": True,
                "base_url": base_url,
            },
        )

    @app.get("/notes/{name}", response_class=HTMLResponse)
    async def edit_note(request: Request, name: str) -> HTMLResponse:
        """Edit existing note."""
        content = notes_fs.read_note(name)
        if content is None:
            # Note doesn't exist, treat as new
            content = ""
        return templates.TemplateResponse(
            request,
            "notes/edit.html",
            {
                "note_name": name,
                "content": content,
                "is_new": not notes_fs.note_exists(name),
                "base_url": base_url,
            },
        )

    @app.post("/notes/{name}", response_class=HTMLResponse)
    async def save_note(
        _request: Request,
        name: str,
        content: str = Form(""),
        new_name: str = Form(""),
    ) -> RedirectResponse:
        """Save note content."""
        # Use new_name if provided (for renaming), otherwise use URL name
        target_name = new_name.strip() if new_name.strip() else name

        # Handle rename if names differ and old note exists
        if target_name != name and notes_fs.note_exists(name):
            notes_fs.rename_note(name, target_name)
        else:
            notes_fs.save_note(target_name, content)

        # Redirect to the saved note
        return RedirectResponse(
            url=f"{base_url}/notes/{target_name}",
            status_code=303,
        )

    @app.delete("/notes/{name}")
    async def delete_note(request: Request, name: str) -> HTMLResponse:
        """Delete a note."""
        deleted = notes_fs.delete_note(name)
        notes = notes_fs.list_notes()
        # Return updated note list partial for HTMX
        return templates.TemplateResponse(
            request,
            "notes/partials/note_list.html",
            {
                "notes": notes,
                "base_url": base_url,
                "deleted": deleted,
                "deleted_name": name if deleted else None,
            },
        )
