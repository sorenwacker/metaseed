"""User data paths for metaseed.

Follows platform conventions:
- Linux/macOS: ~/.local/share/metaseed or XDG_DATA_HOME/metaseed
- Windows: %LOCALAPPDATA%/metaseed
"""

import os
from pathlib import Path


def user_data_base() -> Path:
    """Where metaseed's data lives, without creating anything.

    The same resolution as :func:`get_user_data_dir` -- ``XDG_DATA_HOME`` or
    ``~/.local/share`` on Unix, ``%LOCALAPPDATA%`` on Windows -- but without the
    ``mkdir``, so a module-level default can be derived from it without touching
    the filesystem at import time.

    Returns:
        Path to the metaseed data directory, which may not exist.
    """
    if os.name == "nt":  # Windows
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    else:  # Unix-like (Linux, macOS)
        xdg_data = os.environ.get("XDG_DATA_HOME")
        base = Path(xdg_data) if xdg_data else Path.home() / ".local" / "share"
    return base / "metaseed"


def get_user_data_dir() -> Path:
    """Get the user data directory for metaseed.

    Returns:
        Path to user data directory (created if it doesn't exist).
    """
    data_dir = user_data_base()
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


def get_user_config_path() -> Path:
    """Get the path to the instance-level settings file (created on first write).

    Returns:
        Path to ``<user data dir>/settings.json`` (the parent dir is ensured by
        :func:`get_user_data_dir`; the file itself may not exist yet).
    """
    return get_user_data_dir() / "settings.json"


def get_datasets_dir() -> Path:
    """Get the directory holding saved datasets, creating it if needed.

    Resolution is delegated to
    :func:`metaseed.repositories.filesystem_dataset.default_datasets_dir`, the
    same call the dataset repository makes, so a caller listing the directory
    and a caller writing to it cannot disagree about where datasets live --
    including under the ``METASEED_DATASETS_DIR`` override.

    Returns:
        Path to the datasets directory (created if it doesn't exist).
    """
    from metaseed.repositories.filesystem_dataset import default_datasets_dir

    datasets_dir = default_datasets_dir()
    datasets_dir.mkdir(parents=True, exist_ok=True)
    return datasets_dir


def get_builtin_specs_dir() -> Path:
    """Get the directory for built-in specifications.

    Returns:
        Path to built-in specs directory.
    """
    return Path(__file__).parent / "specs"
