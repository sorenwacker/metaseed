"""The explorer exports its graph as a PNG holding every shown entity.

The canvas only ever holds what is in view, so saving it as-is would cut off
a graph larger than the window, and would carry the screen's resolution and a
transparent background. The export sizes a frame from the nodes' extent
instead; `pngExportFrame` decides that frame and is tested here under node.
"""

from __future__ import annotations

import base64
import json
import shutil
import struct
import subprocess
from pathlib import Path
from typing import Any

import pytest

from tests.test_ui.test_selenium import browser, server  # noqa: F401

ROOT = Path(__file__).resolve().parents[2] / "src" / "metaseed" / "ui"
ERD_SCRIPT = ROOT / "static" / "js" / "erd-common.js"
EXPLORE_PAGE = ROOT / "templates" / "explore" / "index.html"


def _frame(boxes: list[dict[str, float]], dpr: float = 1) -> dict[str, Any]:
    node = shutil.which("node")
    if node is None:
        pytest.skip("node is not installed")
    script = (
        ERD_SCRIPT.read_text()
        + f"\nprocess.stdout.write(JSON.stringify(pngExportFrame({json.dumps(boxes)}, {dpr})));\n"
    )
    out = subprocess.run(
        [node, "-e", script], capture_output=True, text=True, check=True
    ).stdout
    return json.loads(out)


def _box(left: float, top: float, right: float, bottom: float) -> dict[str, float]:
    return {"left": left, "top": top, "right": right, "bottom": bottom}


def test_the_frame_covers_every_node_with_a_margin() -> None:
    frame = _frame([_box(-500, -100, -300, 0), _box(1000, 800, 1200, 1000)])

    assert frame["center"] == {"x": 350, "y": 450}
    # 1700 x 1100 graph units, a 40-unit margin each side, two pixels per unit.
    assert (frame["width"], frame["height"]) == (3560, 2360)
    assert frame["scale"] == 2


def test_the_frame_yields_two_pixels_per_unit_on_a_high_density_screen() -> None:
    """The browser multiplies the canvas by its pixel ratio, so the view scale
    is divided by it: the image is the same size on every screen."""
    frame = _frame([_box(0, 0, 100, 100)], dpr=2)

    assert frame["scale"] == 1
    assert (frame["width"], frame["height"]) == (180, 180), "CSS pixels, not device"


def test_a_huge_graph_is_scaled_down_to_the_canvas_limit() -> None:
    frame = _frame([_box(0, 0, 20000, 1000)])

    assert frame["width"] <= 8192
    assert frame["scale"] < 2


def test_the_page_offers_png_next_to_the_reports() -> None:
    page = EXPLORE_PAGE.read_text()

    assert "ERD.exportPng(" in page


@pytest.mark.selenium
def test_the_exported_image_is_a_png_of_the_whole_graph(browser) -> None:  # noqa: F811 (the fixture imported above)
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support import expected_conditions as EC
    from selenium.webdriver.support.ui import Select, WebDriverWait

    from tests.test_ui.test_selenium import BASE_URL

    browser.get(f"{BASE_URL}/explore")
    Select(browser.find_element(By.ID, "base-profile")).select_by_value("miappe")
    WebDriverWait(browser, 10).until(
        lambda d: len(Select(d.find_element(By.ID, "base-version")).options) > 1
    )
    Select(browser.find_element(By.ID, "base-version")).select_by_index(1)
    browser.find_element(By.ID, "compare-btn").click()
    WebDriverWait(browser, 30).until(
        EC.visibility_of_element_located((By.ID, "export-section"))
    )
    browser.set_window_size(800, 600)
    url = browser.execute_async_script(
        "ERD.toPngDataUrl().then(arguments[arguments.length - 1]);"
    )
    assert url.startswith("data:image/png;base64,")
    png = base64.b64decode(url.split(",", 1)[1])
    assert png[:8] == b"\x89PNG\r\n\x1a\n"
    width, height = struct.unpack(">II", png[16:24])
    assert width > 800 or height > 600, "the image is cut to the window"
    drawn = browser.execute_async_script(
        """
        const done = arguments[arguments.length - 1];
        const image = new Image();
        image.onload = () => {
            const canvas = document.createElement('canvas');
            canvas.width = image.width;
            canvas.height = image.height;
            const context = canvas.getContext('2d');
            context.drawImage(image, 0, 0);
            const pixels = context.getImageData(0, 0, image.width, image.height).data;
            let inked = 0;
            for (let i = 0; i < pixels.length; i += 4) {
                if (pixels[i] < 250 || pixels[i + 1] < 250 || pixels[i + 2] < 250) inked++;
            }
            done(inked);
        };
        image.src = arguments[0];
        """,
        url,
    )
    assert drawn > 1000, "the image is blank"
    assert (
        browser.execute_script("return ERD.getNetwork().body.container.style.width;")
        == ""
    ), "the canvas was left at the export size"
