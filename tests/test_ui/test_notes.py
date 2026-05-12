"""Tests for the notes functionality.

Tests use FastAPI TestClient to verify route behavior.
"""

import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from metaseed.ui.notes_filesystem import NotesFilesystem
from metaseed.ui.state import AppState


@pytest.fixture
def temp_notes_dir():
    """Create a temporary directory for notes."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def notes_fs(temp_notes_dir):
    """Create a NotesFilesystem with temp directory."""
    return NotesFilesystem(base_path=temp_notes_dir)


@pytest.fixture
def client_with_notes(temp_notes_dir):
    """Create a test client with notes using temp directory."""
    from fastapi import FastAPI
    from fastapi.templating import Jinja2Templates

    from metaseed.ui.routes.notes import register_notes_routes

    app = FastAPI()
    ui_dir = Path(__file__).parent.parent.parent / "src" / "metaseed" / "ui"
    templates = Jinja2Templates(directory=str(ui_dir / "templates"))

    notes_fs = NotesFilesystem(base_path=temp_notes_dir)

    register_notes_routes(app, templates, lambda: None, notes_fs=notes_fs)

    return TestClient(app), notes_fs


class TestNotesFilesystem:
    """Tests for NotesFilesystem class."""

    def test_init_creates_directory(self, temp_notes_dir):
        """NotesFilesystem creates base directory on init."""
        notes_dir = temp_notes_dir / "notes"
        assert not notes_dir.exists()
        NotesFilesystem(base_path=notes_dir)
        assert notes_dir.exists()

    def test_list_notes_empty(self, notes_fs):
        """List notes returns empty list when no notes exist."""
        assert notes_fs.list_notes() == []

    def test_save_and_read_note(self, notes_fs):
        """Save and read a note."""
        notes_fs.save_note("test-note", "# Test Note\n\nContent here.")
        content = notes_fs.read_note("test-note")
        assert content == "# Test Note\n\nContent here."

    def test_list_notes_returns_metadata(self, notes_fs):
        """List notes returns metadata for each note."""
        notes_fs.save_note("my-note", "Content")
        notes = notes_fs.list_notes()

        assert len(notes) == 1
        assert notes[0]["name"] == "my-note"
        assert "modified" in notes[0]
        assert "size" in notes[0]

    def test_list_notes_sorted_by_modified(self, notes_fs):
        """List notes returns most recently modified first."""
        import time

        notes_fs.save_note("first", "First note")
        time.sleep(0.1)
        notes_fs.save_note("second", "Second note")

        notes = notes_fs.list_notes()
        assert notes[0]["name"] == "second"
        assert notes[1]["name"] == "first"

    def test_read_nonexistent_note(self, notes_fs):
        """Read nonexistent note returns None."""
        assert notes_fs.read_note("does-not-exist") is None

    def test_delete_note(self, notes_fs):
        """Delete removes a note."""
        notes_fs.save_note("to-delete", "Content")
        assert notes_fs.note_exists("to-delete")

        result = notes_fs.delete_note("to-delete")

        assert result is True
        assert not notes_fs.note_exists("to-delete")

    def test_delete_nonexistent_note(self, notes_fs):
        """Delete nonexistent note returns False."""
        assert notes_fs.delete_note("does-not-exist") is False

    def test_rename_note(self, notes_fs):
        """Rename changes note filename."""
        notes_fs.save_note("old-name", "Content")

        result = notes_fs.rename_note("old-name", "new-name")

        assert result is not None
        assert not notes_fs.note_exists("old-name")
        assert notes_fs.note_exists("new-name")
        assert notes_fs.read_note("new-name") == "Content"

    def test_rename_nonexistent_note(self, notes_fs):
        """Rename nonexistent note returns None."""
        assert notes_fs.rename_note("does-not-exist", "new-name") is None

    def test_note_exists(self, notes_fs):
        """Note exists returns correct boolean."""
        assert not notes_fs.note_exists("test")
        notes_fs.save_note("test", "Content")
        assert notes_fs.note_exists("test")

    def test_sanitizes_path_traversal(self, notes_fs):
        """Path traversal characters are sanitized."""
        notes_fs.save_note("../../../etc/passwd", "Malicious")
        # / is replaced with _, so ../../../etc/passwd becomes .._.._.._etc_passwd
        assert notes_fs.note_exists(".._.._.._etc_passwd")

    def test_empty_name_uses_untitled(self, notes_fs):
        """Empty note name defaults to 'untitled'."""
        notes_fs.save_note("", "Content")
        assert notes_fs.note_exists("untitled")


class TestNotesRoutes:
    """Tests for notes HTTP routes."""

    def test_notes_index_returns_html(self, client_with_notes):
        """Notes index returns HTML page."""
        client, _ = client_with_notes
        response = client.get("/notes/")
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]
        assert "Notes" in response.text

    def test_notes_index_contains_new_button(self, client_with_notes):
        """Notes index contains new note button."""
        client, _ = client_with_notes
        response = client.get("/notes/")
        assert "New Note" in response.text

    def test_new_note_page(self, client_with_notes):
        """New note page renders."""
        client, _ = client_with_notes
        response = client.get("/notes/new")
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]

    def test_edit_note_page_new_note(self, client_with_notes):
        """Edit page for non-existent note works."""
        client, _ = client_with_notes
        response = client.get("/notes/my-new-note")
        assert response.status_code == 200
        assert "my-new-note" in response.text

    def test_save_note(self, client_with_notes):
        """Save note creates file."""
        client, notes_fs = client_with_notes
        response = client.post(
            "/notes/test-note",
            data={"content": "# My Note\n\nSome content."},
            follow_redirects=False,
        )
        assert response.status_code == 303
        assert notes_fs.note_exists("test-note")
        assert notes_fs.read_note("test-note") == "# My Note\n\nSome content."

    def test_save_note_with_rename(self, client_with_notes):
        """Save note with different name renames."""
        client, notes_fs = client_with_notes
        notes_fs.save_note("old-name", "Original content")

        response = client.post(
            "/notes/old-name",
            data={"content": "Updated content", "new_name": "new-name"},
            follow_redirects=False,
        )

        assert response.status_code == 303
        assert notes_fs.note_exists("new-name")
        assert not notes_fs.note_exists("old-name")

    def test_delete_note(self, client_with_notes):
        """Delete note removes file."""
        client, notes_fs = client_with_notes
        notes_fs.save_note("to-delete", "Content")

        response = client.delete("/notes/to-delete")

        assert response.status_code == 200
        assert not notes_fs.note_exists("to-delete")

    def test_notes_list_shows_notes(self, client_with_notes):
        """Notes list shows existing notes."""
        client, notes_fs = client_with_notes
        notes_fs.save_note("note-one", "Content one")
        notes_fs.save_note("note-two", "Content two")

        response = client.get("/notes/")

        assert "note-one" in response.text
        assert "note-two" in response.text

    def test_edit_existing_note_shows_content(self, client_with_notes):
        """Edit page shows existing note content."""
        client, notes_fs = client_with_notes
        notes_fs.save_note("existing-note", "This is the content.")

        response = client.get("/notes/existing-note")

        assert response.status_code == 200
        assert "This is the content." in response.text


class TestNavigationLinks:
    """Tests for Notes navigation link in other pages."""

    def test_notes_link_in_editor(self):
        """Editor page contains Notes navigation link."""
        from metaseed.ui.app import create_app

        state = AppState()
        app = create_app(state)
        client = TestClient(app)

        response = client.get("/")
        assert "Notes" in response.text
        assert 'href="/notes/"' in response.text or 'href="/notes/' in response.text

    def test_notes_link_in_explore(self):
        """Explore page contains Notes navigation link."""
        from metaseed.ui.app import create_app

        state = AppState()
        app = create_app(state)
        client = TestClient(app)

        response = client.get("/explore/")
        assert "Notes" in response.text
