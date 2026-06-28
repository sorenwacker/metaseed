"""Public API and modularity guarantees.

These pin two promises consumers rely on:
- ``metaseed.list_profiles()`` is a public entry point.
- The reusable tools (``metaseed.forms``) and the top-level package import
  WITHOUT pulling in the web framework (FastAPI/Starlette/the UI app), so a
  downstream app can reuse them headlessly.
"""

from __future__ import annotations

import subprocess
import sys


def _import_loads_web_modules(import_stmt: str) -> list[str]:
    """Run ``import_stmt`` in a fresh interpreter; return any web modules loaded."""
    code = (
        f"{import_stmt}\n"
        "import sys\n"
        "web = ('fastapi', 'starlette', 'metaseed.ui.app')\n"
        "print(','.join(m for m in web if m in sys.modules))\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, check=True
    )
    loaded = result.stdout.strip()
    return loaded.split(",") if loaded else []


def test_list_profiles_is_public_and_lists_builtins():
    import metaseed

    profiles = metaseed.list_profiles()
    assert isinstance(profiles, list)
    assert "miappe" in profiles
    assert "list_profiles" in metaseed.__all__


def test_forms_package_imports_without_the_web_stack():
    assert _import_loads_web_modules("import metaseed.forms") == []


def test_top_level_metaseed_import_does_not_pull_fastapi():
    # The FastAPI app is exposed lazily via metaseed.api; importing the package
    # must not eagerly load it.
    assert _import_loads_web_modules("import metaseed") == []


def test_rest_app_is_still_importable_lazily():
    from metaseed.api import app

    assert app.__class__.__name__ == "FastAPI"
