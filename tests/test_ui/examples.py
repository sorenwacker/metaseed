"""Load example values from MIAPPE YAML spec for use in tests."""

from pathlib import Path

import yaml


def load_spec_examples(profile: str = "miappe") -> dict[str, dict]:
    """Load example values for all entities from the YAML spec.

    Args:
        profile: The profile to load (miappe or isa).

    Returns:
        Dictionary mapping entity names to their example values.
    """
    spec_dir = Path(__file__).parent.parent.parent / "src" / "miappe_api" / "specs"
    spec_file = spec_dir / "miappe_v1.1.yaml" if profile == "miappe" else spec_dir / "isa_v1.0.yaml"

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
