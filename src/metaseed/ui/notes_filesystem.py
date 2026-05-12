"""Filesystem-based storage for markdown notes.

Notes are stored in user space at ~/.local/share/metaseed/notes/.
"""

from datetime import datetime
from pathlib import Path


class NotesFilesystem:
    """Manage markdown notes in user space."""

    def __init__(self, base_path: Path | None = None) -> None:
        """Initialize notes filesystem.

        Args:
            base_path: Base directory for notes. Defaults to ~/.local/share/metaseed/notes.
        """
        self.base_path = base_path or (Path.home() / ".local/share/metaseed/notes")
        self.base_path.mkdir(parents=True, exist_ok=True)

    def _note_path(self, name: str) -> Path:
        """Get the full path for a note.

        Args:
            name: Note name (without .md extension).

        Returns:
            Full path to the note file.
        """
        # Sanitize name to prevent path traversal
        safe_name = name.replace("/", "_").replace("\\", "_").strip()
        if not safe_name:
            safe_name = "untitled"
        return self.base_path / f"{safe_name}.md"

    def list_notes(self) -> list[dict]:
        """List all notes with metadata.

        Returns:
            List of dicts with name, modified timestamp, and size.
        """
        notes = []
        for path in sorted(
            self.base_path.glob("*.md"), key=lambda p: p.stat().st_mtime, reverse=True
        ):
            stat = path.stat()
            notes.append(
                {
                    "name": path.stem,
                    "modified": datetime.fromtimestamp(stat.st_mtime),
                    "size": stat.st_size,
                }
            )
        return notes

    def read_note(self, name: str) -> str | None:
        """Read note content.

        Args:
            name: Note name (without .md extension).

        Returns:
            Note content as string, or None if not found.
        """
        path = self._note_path(name)
        if not path.exists():
            return None
        return path.read_text(encoding="utf-8")

    def save_note(self, name: str, content: str) -> Path:
        """Save note content.

        Args:
            name: Note name (without .md extension).
            content: Markdown content to save.

        Returns:
            Path to the saved note.
        """
        path = self._note_path(name)
        path.write_text(content, encoding="utf-8")
        return path

    def delete_note(self, name: str) -> bool:
        """Delete a note.

        Args:
            name: Note name (without .md extension).

        Returns:
            True if deleted, False if not found.
        """
        path = self._note_path(name)
        if not path.exists():
            return False
        path.unlink()
        return True

    def rename_note(self, old_name: str, new_name: str) -> Path | None:
        """Rename a note.

        Args:
            old_name: Current note name (without .md extension).
            new_name: New note name (without .md extension).

        Returns:
            Path to the renamed note, or None if old note not found.
        """
        old_path = self._note_path(old_name)
        if not old_path.exists():
            return None
        new_path = self._note_path(new_name)
        old_path.rename(new_path)
        return new_path

    def note_exists(self, name: str) -> bool:
        """Check if a note exists.

        Args:
            name: Note name (without .md extension).

        Returns:
            True if note exists.
        """
        return self._note_path(name).exists()
