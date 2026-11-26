"""A profile shortcut keeps working after its namesake subpackage is imported (261126).

``metaseed.ena`` is both the ``ena()`` facade shortcut and the ENA adapter
package. Importing the package rebinds ``metaseed.ena`` to it, which made
``from metaseed import ena; ena()`` fail with "'module' object is not callable"
depending on what had been imported before. The colliding packages are callable
and delegate to the shortcut.
"""

from __future__ import annotations

import inspect
import subprocess
import sys
from pathlib import Path

import pytest

from metaseed.facade import profiles

SRC_ROOT = Path(__file__).resolve().parents[2] / "src" / "metaseed"

SHORTCUTS = [
    name
    for name, obj in inspect.getmembers(profiles, inspect.isfunction)
    if obj.__module__ == profiles.__name__
]
COLLIDING = sorted(
    name for name in SHORTCUTS if (SRC_ROOT / name / "__init__.py").is_file()
)


def test_the_known_collisions_are_detected() -> None:
    assert {"ena", "pride", "metabolights"} <= set(COLLIDING)


def _run(code: str) -> str:
    result = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, check=False
    )
    assert result.returncode == 0, result.stderr
    return result.stdout.strip()


@pytest.mark.parametrize("name", COLLIDING)
def test_shortcut_works_after_the_subpackage_is_imported(name: str) -> None:
    out = _run(
        f"import metaseed.{name}\n"
        f"from metaseed import {name}\n"
        f"print(type({name}()).__name__, {name}().profile)"
    )
    assert out == f"ProfileFacade {name}"


@pytest.mark.parametrize("name", COLLIDING)
def test_the_subpackage_still_works_as_a_package(name: str) -> None:
    out = _run(
        f"from metaseed import {name}\n"
        f"import metaseed.{name} as package\n"
        "print(package.__name__, hasattr(package, '__path__'))"
    )
    assert out == f"metaseed.{name} True"


@pytest.mark.parametrize("name", COLLIDING)
def test_calling_the_package_passes_the_version(name: str) -> None:
    out = _run(
        f"import metaseed.{name} as package\n"
        f"from metaseed.facade.profiles import {name} as shortcut\n"
        "print(package(None).version == shortcut().version)"
    )
    assert out == "True"
