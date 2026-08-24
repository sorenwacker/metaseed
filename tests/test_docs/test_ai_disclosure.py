"""The published documentation must disclose that it is AI-generated.

The EU AI Act's transparency obligations require AI-generated content to be
identifiable as such. The disclosure lives in ``mkdocs.yml``'s ``copyright``
field, which Material renders in the footer of every page — one declaration
covers the whole site, and this gate keeps it from silently disappearing.

The file is scanned as text rather than YAML-parsed: mkdocs.yml carries
``!!python/name:`` tags that ``yaml.safe_load`` refuses.
"""

import re
from pathlib import Path


def test_every_docs_page_carries_the_ai_generation_notice():
    text = Path(__file__).resolve().parents[2].joinpath("mkdocs.yml").read_text()
    match = re.search(r"^copyright:\s*(.+)$", text, re.MULTILINE)
    notice = match.group(1) if match else ""
    assert "generated with Claude Code" in notice, (
        "mkdocs.yml must declare a copyright footer disclosing that the "
        "documentation was generated with Claude Code (EU AI Act transparency)"
    )
