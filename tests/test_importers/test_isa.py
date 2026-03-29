"""Tests for ISA importer."""

from pathlib import Path

import pytest

from miappe_api.importers import ISAImporter


class TestISAImporter:
    """Tests for ISAImporter class."""

    @pytest.fixture
    def importer(self) -> ISAImporter:
        """Create ISA importer instance."""
        return ISAImporter()

    @pytest.fixture
    def isa_json_path(self) -> Path:
        """Path to test ISA-JSON file."""
        return Path("tests/fixtures/isa_examples/BII-I-1.json")

    @pytest.fixture
    def isa_tab_path(self, tmp_path: Path) -> Path:
        """Create temp ISA-Tab directory with test files."""
        import shutil

        # Copy files to temp directory
        tab_dir = tmp_path / "isatab"
        tab_dir.mkdir()

        fixtures = Path("tests/fixtures/isa_examples")
        shutil.copy(fixtures / "i_MTBLS1.txt", tab_dir / "i_Investigation.txt")
        shutil.copy(fixtures / "s_MTBLS1.txt", tab_dir / "s_MTBLS1.txt")
        shutil.copy(
            fixtures / "a_MTBLS1_metabolite_profiling.txt",
            tab_dir / "a_MTBLS1_metabolite_profiling_NMR_spectroscopy.txt",
        )

        return tab_dir


class TestISAJSONImport(TestISAImporter):
    """Tests for ISA-JSON import."""

    def test_import_json_returns_result(self, importer: ISAImporter, isa_json_path: Path) -> None:
        """Importing ISA-JSON returns ImportResult."""
        result = importer.import_json(isa_json_path)

        assert result is not None
        assert result.investigation is not None
        assert isinstance(result.studies, list)

    def test_import_json_investigation_fields(
        self, importer: ISAImporter, isa_json_path: Path
    ) -> None:
        """Investigation has expected MIAPPE fields."""
        result = importer.import_json(isa_json_path)

        inv = result.investigation
        assert "unique_id" in inv
        assert "title" in inv
        assert inv["unique_id"] == "BII-I-1"

    def test_import_json_studies_extracted(
        self, importer: ISAImporter, isa_json_path: Path
    ) -> None:
        """Studies are extracted from ISA-JSON."""
        result = importer.import_json(isa_json_path)

        assert len(result.studies) == 2
        assert result.studies[0]["unique_id"] == "BII-S-1"
        assert result.studies[1]["unique_id"] == "BII-S-2"

    def test_import_json_samples_extracted(
        self, importer: ISAImporter, isa_json_path: Path
    ) -> None:
        """Samples are extracted from ISA-JSON."""
        result = importer.import_json(isa_json_path)

        assert len(result.samples) > 0

    def test_import_json_persons_extracted(
        self, importer: ISAImporter, isa_json_path: Path
    ) -> None:
        """Persons are extracted from ISA-JSON."""
        result = importer.import_json(isa_json_path)

        assert len(result.persons) > 0
        assert all("name" in p for p in result.persons)

    def test_import_json_publications_mapped(
        self, importer: ISAImporter, isa_json_path: Path
    ) -> None:
        """Publications are mapped to associated_publication."""
        result = importer.import_json(isa_json_path)

        assert "associated_publication" in result.investigation
        assert any("doi" in pub for pub in result.investigation["associated_publication"])

    def test_import_json_nonexistent_raises(self, importer: ISAImporter) -> None:
        """Importing nonexistent file raises FileNotFoundError."""
        with pytest.raises(FileNotFoundError):
            importer.import_json(Path("/nonexistent/file.json"))

    def test_summary_property(self, importer: ISAImporter, isa_json_path: Path) -> None:
        """ImportResult has summary property."""
        result = importer.import_json(isa_json_path)

        summary = result.summary
        assert "investigation" in summary
        assert "studies" in summary
        assert "samples" in summary


class TestISATabImport(TestISAImporter):
    """Tests for ISA-Tab import."""

    def test_import_tab_returns_result(self, importer: ISAImporter, isa_tab_path: Path) -> None:
        """Importing ISA-Tab returns ImportResult."""
        result = importer.import_tab(isa_tab_path)

        assert result is not None
        assert result.investigation is not None

    def test_import_tab_investigation_fields(
        self, importer: ISAImporter, isa_tab_path: Path
    ) -> None:
        """Investigation has expected MIAPPE fields."""
        result = importer.import_tab(isa_tab_path)

        inv = result.investigation
        assert "unique_id" in inv
        assert "title" in inv
        assert inv["unique_id"] == "MTBLS1"

    def test_import_tab_study_extracted(self, importer: ISAImporter, isa_tab_path: Path) -> None:
        """Study is extracted from ISA-Tab."""
        result = importer.import_tab(isa_tab_path)

        assert len(result.studies) == 1
        assert result.studies[0]["unique_id"] == "MTBLS1"

    def test_import_tab_factors_extracted(self, importer: ISAImporter, isa_tab_path: Path) -> None:
        """Experimental factors are extracted."""
        result = importer.import_tab(isa_tab_path)

        study = result.studies[0]
        assert "factors" in study
        factor_names = [f["name"] for f in study["factors"]]
        assert "Gender" in factor_names

    def test_import_tab_samples_extracted(self, importer: ISAImporter, isa_tab_path: Path) -> None:
        """Samples are extracted from ISA-Tab."""
        result = importer.import_tab(isa_tab_path)

        assert len(result.samples) > 0

    def test_import_tab_not_directory_raises(self, importer: ISAImporter) -> None:
        """Importing non-directory raises NotADirectoryError."""
        with pytest.raises(NotADirectoryError):
            importer.import_tab(Path("tests/fixtures/isa_examples/BII-I-1.json"))
