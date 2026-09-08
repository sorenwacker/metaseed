<figure markdown="span">
  ![Metaseed](images/metaseed-logo-400.png){ width="200" }
</figure>

# Metaseed

- **Try it without installing** — [the hub](https://metaseed.ewi.tudelft.nl/hub/), a hosted metaseed you sign into
- **Install it** — [`metaseed` on PyPI](https://pypi.org/project/metaseed/) · `pip install metaseed`
- **Source** — [metaseed](https://github.com/sorenwacker/metaseed) · [metaseed-hub](https://github.com/sorenwacker/metaseed-hub)
- **The hub's documentation** — [how the hosted version works](https://sorenwacker.github.io/metaseed-hub/)


Metaseed provides tools for creating, editing, and validating experimental metadata across scientific standards — MIAPPE (plant phenotyping), ISA, Darwin Core, DiSSCo, ENA, JERM, PRIDE, and MetaboLights.

Metadata structure is defined in YAML specification files, which are used to generate Pydantic models at runtime. This schema-driven approach allows the same codebase to support multiple metadata standards. Fields reference real ontologies (PPEO, ISA, PROV-O) for semantic interoperability.

A dataset can also be exported as a [DCAT](architecture/dcat.md) catalog card (JSON-LD / Turtle) so it is discoverable in data portals and assessable by FAIR tools.

The library can be used through a command-line interface, a web-based editor, or programmatically via Python.
