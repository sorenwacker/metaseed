#!/usr/bin/env python3
"""Convert CropXR JSON schema to metaseed profile.yaml format."""

import json
from pathlib import Path

import yaml


def convert_cardinality(cardinality: str) -> tuple[bool, bool]:
    """Convert CropXR cardinality to (required, is_list).

    Args:
        cardinality: CropXR cardinality string (e.g., "1", "0-1", "1+", "0+")

    Returns:
        Tuple of (required, is_list)
    """
    if cardinality is None:
        return False, False

    cardinality = str(cardinality).strip()

    if cardinality in ("1", "1-1"):
        return True, False
    if cardinality in ("0-1", "0", ""):
        return False, False
    if cardinality in ("1+", "1-n", "1-*"):
        return True, True
    if cardinality in ("0+", "0-n", "0-*", "*"):
        return False, True
    # Default to optional single
    return False, False


def convert_field_type(field: dict) -> str:
    """Determine field type from format and options.

    Args:
        field: CropXR field definition

    Returns:
        Metaseed field type string
    """
    fmt = field.get("format", "").lower()
    options = field.get("options")

    # Check for enum/options
    if options and options.get("type") == "pre-defined list":
        return "string"  # Will add enum constraint

    # Check format for type hints
    if "date" in fmt or "iso 8601" in fmt.lower():
        return "date"
    if "integer" in fmt:
        return "integer"
    if "decimal" in fmt or "float" in fmt or "number" in fmt:
        return "float"  # Use 'float' not 'number'
    if "boolean" in fmt:
        return "boolean"
    if "uri" in fmt or "url" in fmt:
        return "uri"
    if "doi" in fmt:
        return "string"  # DOI is a string with pattern
    return "string"


def extract_enum_values(options: dict) -> list[str] | None:
    """Extract enum values from options.

    Args:
        options: CropXR options dict

    Returns:
        List of enum values or None
    """
    if not options:
        return None

    if options.get("type") != "pre-defined list":
        return None

    opts = options.get("options", [])
    if not opts:
        return None

    # Extract values
    values = []
    for opt in opts:
        if isinstance(opt, dict):
            value = opt.get("value") or opt.get("name")
            if value:
                values.append(value)
        elif isinstance(opt, str):
            values.append(opt)

    return values if values else None


def convert_field(field: dict) -> dict:
    """Convert a CropXR field to metaseed field format.

    Args:
        field: CropXR field definition

    Returns:
        Metaseed field definition
    """
    required, is_list = convert_cardinality(field.get("cardinality"))
    field_type = convert_field_type(field)

    result = {
        "name": field["name"],
        "type": "list" if is_list else field_type,
        "required": required,
        "description": field.get("definition", ""),
    }

    # Add items type for lists
    if is_list:
        result["items"] = field_type

    # Add enum constraint
    enum_values = extract_enum_values(field.get("options"))
    if enum_values:
        result["constraints"] = {"enum": enum_values}

    return result


def to_pascal_case(name: str) -> str:
    """Convert snake_case to PascalCase.

    Args:
        name: Snake case string

    Returns:
        PascalCase string
    """
    return "".join(word.capitalize() for word in name.split("_"))


def convert_section(section: dict) -> tuple[str, dict]:
    """Convert a CropXR section to metaseed entity format.

    Args:
        section: CropXR section definition

    Returns:
        Tuple of (entity_name, entity_definition)
    """
    entity_name = to_pascal_case(section["name"])

    fields = []
    for field in section.get("fields", []):
        if not field.get("hide_from_user", False):
            fields.append(convert_field(field))

    entity = {
        "description": section.get("definition", ""),
        "fields": fields,
    }

    return entity_name, entity


def add_relationships(entities: dict, profile_name: str) -> None:
    """Add entity relationships based on profile type.

    Args:
        entities: Dict of entity definitions
        profile_name: Profile name to determine relationships
    """
    if "sequencing" in profile_name:
        # Sequencing relationships
        if "Study" in entities:
            entities["Study"]["fields"].extend(
                [
                    {
                        "name": "experiments",
                        "type": "list",
                        "items": "Experiment",
                        "required": False,
                        "description": "Experiments in this study",
                    },
                    {
                        "name": "samples",
                        "type": "list",
                        "items": "Sample",
                        "required": False,
                        "description": "Samples in this study",
                    },
                    {
                        "name": "persons",
                        "type": "list",
                        "items": "Person",
                        "required": False,
                        "description": "Persons associated with this study",
                    },
                ]
            )
        if "Experiment" in entities:
            entities["Experiment"]["fields"].append(
                {
                    "name": "runs",
                    "type": "list",
                    "items": "Run",
                    "required": False,
                    "description": "Sequencing runs for this experiment",
                }
            )
        if "Investigation" in entities:
            entities["Investigation"]["fields"].append(
                {
                    "name": "studies",
                    "type": "list",
                    "items": "Study",
                    "required": False,
                    "description": "Studies in this investigation",
                }
            )

    elif "phenotyping" in profile_name:
        # Phenotyping relationships (based on MIAPPE structure)
        if "Investigation" in entities:
            entities["Investigation"]["fields"].extend(
                [
                    {
                        "name": "studies",
                        "type": "list",
                        "items": "Study",
                        "required": False,
                        "description": "Studies in this investigation",
                    },
                    {
                        "name": "persons",
                        "type": "list",
                        "items": "Person",
                        "required": False,
                        "description": "Persons associated with this investigation",
                    },
                ]
            )
        if "Study" in entities:
            entities["Study"]["fields"].extend(
                [
                    {
                        "name": "biological_materials",
                        "type": "list",
                        "items": "BiologicalMaterial",
                        "required": False,
                        "description": "Biological materials used in this study",
                    },
                    {
                        "name": "observation_units",
                        "type": "list",
                        "items": "ObservationUnit",
                        "required": False,
                        "description": "Observation units in this study",
                    },
                    {
                        "name": "experimental_factors",
                        "type": "list",
                        "items": "ExperimentalFactor",
                        "required": False,
                        "description": "Experimental factors in this study",
                    },
                    {
                        "name": "environments",
                        "type": "list",
                        "items": "Environment",
                        "required": False,
                        "description": "Environment parameters for this study",
                    },
                    {
                        "name": "events",
                        "type": "list",
                        "items": "Event",
                        "required": False,
                        "description": "Events in this study",
                    },
                    {
                        "name": "observed_variables",
                        "type": "list",
                        "items": "ObservedVariable",
                        "required": False,
                        "description": "Variables observed in this study",
                    },
                    {
                        "name": "data_files",
                        "type": "list",
                        "items": "DataFile",
                        "required": False,
                        "description": "Data files associated with this study",
                    },
                ]
            )
        if "ObservationUnit" in entities:
            entities["ObservationUnit"]["fields"].append(
                {
                    "name": "samples",
                    "type": "list",
                    "items": "Sample",
                    "required": False,
                    "description": "Samples taken from this observation unit",
                }
            )


def convert_schema(schema_path: Path, profile_name: str, display_name: str) -> dict:
    """Convert a CropXR schema to metaseed profile format.

    Args:
        schema_path: Path to CropXR JSON schema
        profile_name: Profile name (e.g., "cropxr-sequencing")
        display_name: Display name (e.g., "CropXR Sequencing")

    Returns:
        Metaseed profile dict
    """
    with open(schema_path) as f:
        schema = json.load(f)

    version = schema.get("version", "1.0")

    # Convert sections to entities
    entities = {}
    for section in schema.get("sections", []):
        entity_name, entity_def = convert_section(section)
        entities[entity_name] = entity_def

    # Add relationships between entities
    add_relationships(entities, profile_name)

    # Determine root entity
    if "phenotyping" in profile_name and "Investigation" in entities:
        root_entity = "Investigation"
    elif "Study" in entities:
        root_entity = "Study"
    else:
        root_entity = next(iter(entities.keys()))

    profile = {
        "name": profile_name,
        "display_name": display_name,
        "version": version,
        "description": f"{display_name} metadata schema for CropXR consortium.",
        "root_entity": root_entity,
        "entities": entities,
        "validation_rules": [],
    }

    return profile


def main():
    """Convert CropXR schemas to metaseed profiles."""
    cropxr_dir = Path(
        "/Users/sdrwacker/workspace/cropxr/metadata-model-generator/"
        "src/metadata_template_generator/schema_definitions"
    )
    output_dir = Path("/Users/sdrwacker/workspace/metaseed/src/metaseed/specs")

    schemas = [
        {
            "input": cropxr_dir / "sequencing_schema.json",
            "profile": "cropxr-sequencing",
            "display_name": "CropXR Sequencing",
        },
        {
            "input": cropxr_dir / "phenotyping_schema.json",
            "profile": "cropxr-phenotyping",
            "display_name": "CropXR Phenotyping",
        },
    ]

    for schema_config in schemas:
        print(f"Converting {schema_config['profile']}...")  # noqa: T201

        profile = convert_schema(
            schema_config["input"],
            schema_config["profile"],
            schema_config["display_name"],
        )

        # Create output directory
        profile_dir = output_dir / schema_config["profile"] / profile["version"]
        profile_dir.mkdir(parents=True, exist_ok=True)

        # Write profile.yaml
        output_path = profile_dir / "profile.yaml"
        with open(output_path, "w") as f:
            yaml.dump(
                profile,
                f,
                default_flow_style=False,
                allow_unicode=True,
                sort_keys=False,
                width=120,
            )

        print(f"  Wrote {output_path}")  # noqa: T201
        print(f"  Entities: {list(profile['entities'].keys())}")  # noqa: T201
        print(f"  Root: {profile['root_entity']}")  # noqa: T201
        print()  # noqa: T201


if __name__ == "__main__":
    main()
