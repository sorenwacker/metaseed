"""User data paths for metaseed.

Follows platform conventions:
- Linux/macOS: ~/.local/share/metaseed or XDG_DATA_HOME/metaseed
- Windows: %LOCALAPPDATA%/metaseed
"""

import os
from pathlib import Path


def get_user_data_dir() -> Path:
    """Get the user data directory for metaseed.

    Returns:
        Path to user data directory (created if it doesn't exist).
    """
    if os.name == "nt":  # Windows
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    else:  # Unix-like (Linux, macOS)
        xdg_data = os.environ.get("XDG_DATA_HOME")
        base = Path(xdg_data) if xdg_data else Path.home() / ".local" / "share"

    data_dir = base / "metaseed"
    data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir


def get_user_specs_dir() -> Path:
    """Get the directory for user-defined specifications.

    Returns:
        Path to user specs directory (created if it doesn't exist).
    """
    specs_dir = get_user_data_dir() / "specs"
    specs_dir.mkdir(parents=True, exist_ok=True)
    return specs_dir


def get_builtin_specs_dir() -> Path:
    """Get the directory for built-in specifications.

    Returns:
        Path to built-in specs directory.
    """
    return Path(__file__).parent / "specs"
