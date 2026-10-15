<figure markdown="span">
  ![Metaseed](images/metaseed-logo-400.png){ width="200" }
</figure>

# Metaseed

- **Try it without installing** — [the hub](https://metaseed.ewi.tudelft.nl/hub/), a hosted metaseed you sign into
- **Install it** — [`metaseed` on PyPI](https://pypi.org/project/metaseed/) · `uv tool install metaseed` for the command-line tool, `uv add metaseed` or `pip install metaseed` for library use
- **Source** — [metaseed](https://github.com/sorenwacker/metaseed) · [metaseed-hub](https://github.com/sorenwacker/metaseed-hub)
- **The hub's documentation** — [how the hosted version works](https://sorenwacker.github.io/metaseed-hub/)


Metaseed creates, edits, and validates scientific metadata against a standard, from a YAML specification of that standard.

A metadata standard is written as a *profile*: a YAML file naming the entity types, their fields, the parent–child hierarchy, and the validation rules. Profiles ship for MIAPPE, ISA, Darwin Core, DiSSCo, ENA, PRIDE, MetaboLights, REMBI, Health-RI core and FAIRDOM-SEEK. From a profile, metaseed:

- Generates Pydantic models for every entity type at runtime.
- Validates a dataset: required fields, patterns, ranges, uniqueness, references between entities, conditional rules, and ontology terms looked up in the term sources the field names.
- Serializes datasets to JSON, YAML and Excel, and reads them back.
- Imports public records from ENA, PRIDE, MetaboLights and BrAPI servers.
- Exports to ISA-Tab, ENA XML, PRIDE `submission.px` with SDRF, SEEK's ISA RDF, and a [DCAT](architecture/dcat.md) catalog record; pushes a dataset into a running FAIRDOM-SEEK instance or a [metaseed-hub](https://github.com/sorenwacker/metaseed-hub).

Profiles are data, not code: the [spec builder](guides/spec-builder.md) authors a new one or adapts an existing one, and [spec merge](guides/spec-merge.md) compares and merges profiles.

Metaseed is used from a command line, a web interface, a Python API, or an [MCP server](guides/mcp-setup.md) for an AI agent. All four call the same library functions.
