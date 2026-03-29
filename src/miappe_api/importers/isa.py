"""ISA-Tab and ISA-JSON importer for MIAPPE entities.

This module provides functionality to import ISA (Investigation-Study-Assay)
formatted data and convert it to MIAPPE-compliant entities.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Self

from isatools import isajson, isatab
from isatools.model import Investigation as ISAInvestigation
from isatools.model import Study as ISAStudy

__all__ = ["ImportResult", "ISAImporter"]


@dataclass
class ImportResult:
    """Result of an ISA import operation."""

    investigation: dict[str, Any]
    studies: list[dict[str, Any]] = field(default_factory=list)
    samples: list[dict[str, Any]] = field(default_factory=list)
    persons: list[dict[str, Any]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def summary(self: Self) -> str:
        """Return a summary of imported entities."""
        return (
            f"Imported: 1 investigation, {len(self.studies)} studies, "
            f"{len(self.samples)} samples, {len(self.persons)} persons"
        )


class ISAImporter:
    """Import ISA-Tab or ISA-JSON data to MIAPPE format.

    Supports:
    - ISA-Tab: Directory containing i_*.txt, s_*.txt, a_*.txt files
    - ISA-JSON: Single JSON file with full investigation structure

    Example:
        >>> importer = ISAImporter()
        >>> result = importer.import_json("path/to/investigation.json")
        >>> print(result.investigation)
        >>> result = importer.import_tab("path/to/isatab_dir/")
    """

    # Mapping from ISA fields to MIAPPE Investigation fields
    INVESTIGATION_MAPPING = {
        "identifier": "unique_id",
        "title": "title",
        "description": "description",
        "submission_date": "submission_date",
        "public_release_date": "public_release_date",
    }

    # Mapping from ISA Study fields to MIAPPE Study fields
    STUDY_MAPPING = {
        "identifier": "unique_id",
        "title": "title",
        "description": "description",
        "submission_date": "start_date",
        "public_release_date": "end_date",
    }

    # Mapping from ISA Person fields to MIAPPE Person fields
    PERSON_MAPPING = {
        "first_name": "name",  # Will be combined with last_name
        "email": "email",
        "affiliation": "institution",
    }

    def import_json(self: Self, path: Path | str) -> ImportResult:
        """Import from ISA-JSON file.

        Args:
            path: Path to the ISA-JSON file.

        Returns:
            ImportResult with converted MIAPPE entities.
        """
        path = Path(path)
        if not path.exists():
            raise FileNotFoundError(f"ISA-JSON file not found: {path}")

        with open(path) as f:
            investigation = isajson.load(f)

        return self._convert_investigation(investigation)

    def import_tab(self: Self, path: Path | str) -> ImportResult:
        """Import from ISA-Tab directory.

        Args:
            path: Path to directory containing ISA-Tab files.

        Returns:
            ImportResult with converted MIAPPE entities.
        """
        path = Path(path)
        if not path.is_dir():
            raise NotADirectoryError(f"ISA-Tab path must be a directory: {path}")

        investigation = isatab.load(str(path))
        return self._convert_investigation(investigation)

    def _convert_investigation(self: Self, isa_inv: ISAInvestigation) -> ImportResult:
        """Convert ISA Investigation to MIAPPE entities.

        Args:
            isa_inv: ISA Investigation object from isatools.

        Returns:
            ImportResult with all converted entities.
        """
        result = ImportResult(investigation={})

        # Convert investigation
        inv_data = {}
        for isa_field, miappe_field in self.INVESTIGATION_MAPPING.items():
            value = getattr(isa_inv, isa_field, None)
            if value:
                inv_data[miappe_field] = str(value)

        # Add publications as associated_publications
        if isa_inv.publications:
            pubs = []
            for pub in isa_inv.publications:
                if pub.doi:
                    pubs.append(pub.doi)
                elif pub.pubmed_id:
                    pubs.append(f"PMID:{pub.pubmed_id}")
            if pubs:
                inv_data["associated_publications"] = pubs

        result.investigation = inv_data

        # Convert persons from investigation contacts
        for person in isa_inv.contacts:
            person_data = self._convert_person(person)
            if person_data:
                result.persons.append(person_data)

        # Convert studies
        for isa_study in isa_inv.studies:
            study_data, study_samples, study_persons = self._convert_study(isa_study)
            result.studies.append(study_data)
            result.samples.extend(study_samples)

            # Add study contacts
            for person in study_persons:
                if person not in result.persons:
                    result.persons.append(person)

        return result

    def _convert_study(
        self: Self, isa_study: ISAStudy
    ) -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]]]:
        """Convert ISA Study to MIAPPE Study and related entities.

        Args:
            isa_study: ISA Study object.

        Returns:
            Tuple of (study_data, samples, persons).
        """
        study_data = {}

        # Map basic fields
        for isa_field, miappe_field in self.STUDY_MAPPING.items():
            value = getattr(isa_study, isa_field, None)
            if value:
                study_data[miappe_field] = str(value)

        # Extract factors as nested Factor entities
        if isa_study.factors:
            study_data["factors"] = [
                {
                    "unique_id": f"factor_{i}_{f.name.replace(' ', '_')}",
                    "name": f.name,
                    "description": (
                        f.factor_type.term if hasattr(f, "factor_type") and f.factor_type else ""
                    ),
                }
                for i, f in enumerate(isa_study.factors)
            ]

        # Extract design descriptors as experimental_design_type
        if isa_study.design_descriptors:
            design_terms = [d.term for d in isa_study.design_descriptors if hasattr(d, "term")]
            if design_terms:
                study_data["experimental_design_type"] = ", ".join(design_terms)

        # Convert samples
        samples = []
        for sample in isa_study.samples:
            sample_data = self._convert_sample(sample)
            if sample_data:
                samples.append(sample_data)

        # Convert study contacts
        persons = []
        for person in isa_study.contacts:
            person_data = self._convert_person(person)
            if person_data:
                persons.append(person_data)

        return study_data, samples, persons

    def _convert_sample(self: Self, isa_sample: Any) -> dict[str, Any]:
        """Convert ISA Sample to MIAPPE Sample.

        Args:
            isa_sample: ISA Sample object.

        Returns:
            MIAPPE Sample dictionary.
        """
        sample_data = {
            "unique_id": isa_sample.name,
        }

        # Extract characteristics
        if hasattr(isa_sample, "characteristics") and isa_sample.characteristics:
            for char in isa_sample.characteristics:
                if hasattr(char, "category") and char.category:
                    cat_name = char.category.term.lower().replace(" ", "_")
                    if hasattr(char, "value"):
                        if hasattr(char.value, "term"):
                            sample_data[cat_name] = char.value.term
                        else:
                            sample_data[cat_name] = str(char.value)

        return sample_data

    def _convert_person(self: Self, isa_person: Any) -> dict[str, Any]:
        """Convert ISA Person to MIAPPE Person.

        Args:
            isa_person: ISA Person object.

        Returns:
            MIAPPE Person dictionary.
        """
        # Combine first and last name
        name_parts = []
        if hasattr(isa_person, "first_name") and isa_person.first_name:
            name_parts.append(isa_person.first_name)
        if hasattr(isa_person, "mid_initials") and isa_person.mid_initials:
            name_parts.append(isa_person.mid_initials)
        if hasattr(isa_person, "last_name") and isa_person.last_name:
            name_parts.append(isa_person.last_name)

        if not name_parts:
            return {}

        person_data = {"name": " ".join(name_parts)}

        if hasattr(isa_person, "email") and isa_person.email:
            person_data["email"] = isa_person.email

        if hasattr(isa_person, "affiliation") and isa_person.affiliation:
            person_data["institution"] = isa_person.affiliation

        if hasattr(isa_person, "roles") and isa_person.roles:
            person_data["role"] = ", ".join(
                r.term if hasattr(r, "term") else str(r) for r in isa_person.roles
            )

        return person_data
