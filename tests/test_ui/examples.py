"""Load example values from MIAPPE YAML spec for use in tests."""

from pathlib import Path

import yaml


def load_spec_examples(profile: str = "miappe", version: str | None = None) -> dict[str, dict]:
    """Load example values for all entities from the YAML spec.

    Args:
        profile: The profile to load (miappe, isa, etc.).
        version: The version to load. If None, uses default (1.1 for miappe, 1.0 for isa).

    Returns:
        Dictionary mapping entity names to their example values.
    """
    spec_dir = Path(__file__).parent.parent.parent / "src" / "metaseed" / "specs"

    # Default versions
    if version is None:
        version = "1.1" if profile == "miappe" else "1.0"

    # New directory structure: specs/<profile>/<version>/profile.yaml
    spec_file = spec_dir / profile / version / "profile.yaml"

    with open(spec_file) as f:
        spec = yaml.safe_load(f)

    examples = {}
    for entity_name, entity_def in spec.get("entities", {}).items():
        if "example" in entity_def:
            examples[entity_name] = entity_def["example"]

    return examples


# Pre-load MIAPPE examples for convenience
MIAPPE_EXAMPLES = load_spec_examples("miappe")

# Export all entity examples for easy access
INV_EXAMPLE = MIAPPE_EXAMPLES.get("Investigation", {})
STUDY_EXAMPLE = MIAPPE_EXAMPLES.get("Study", {})
PERSON_EXAMPLE = MIAPPE_EXAMPLES.get("Person", {})
BIO_MAT_EXAMPLE = MIAPPE_EXAMPLES.get("BiologicalMaterial", {})
OBS_UNIT_EXAMPLE = MIAPPE_EXAMPLES.get("ObservationUnit", {})
OBS_VAR_EXAMPLE = MIAPPE_EXAMPLES.get("ObservedVariable", {})
FACTOR_EXAMPLE = MIAPPE_EXAMPLES.get("Factor", {})
FACTOR_VALUE_EXAMPLE = MIAPPE_EXAMPLES.get("FactorValue", {})
EVENT_EXAMPLE = MIAPPE_EXAMPLES.get("Event", {})
ENVIRONMENT_EXAMPLE = MIAPPE_EXAMPLES.get("Environment", {})
SAMPLE_EXAMPLE = MIAPPE_EXAMPLES.get("Sample", {})
DATA_FILE_EXAMPLE = MIAPPE_EXAMPLES.get("DataFile", {})
LOCATION_EXAMPLE = MIAPPE_EXAMPLES.get("Location", {})
MATERIAL_SOURCE_EXAMPLE = MIAPPE_EXAMPLES.get("MaterialSource", {})
