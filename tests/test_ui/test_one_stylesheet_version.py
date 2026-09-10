"""Every template asks for the same stylesheet version.

The version query is what makes a browser fetch a changed stylesheet. Four
templates each carried their own number, so a restyle bumped the one in the
base template and the explorer kept serving the cached copy from before it.
"""

import re

from metaseed.ui.app import TEMPLATES_DIR


def test_every_template_links_the_stylesheet_with_one_version() -> None:
    versions: dict[str, str] = {}
    for template in TEMPLATES_DIR.rglob("*.html"):
        for match in re.finditer(r"style\.css\?v=(\w+)", template.read_text()):
            versions[str(template.relative_to(TEMPLATES_DIR))] = match.group(1)
    assert versions, "no template links the stylesheet"
    assert len(set(versions.values())) == 1, versions
