"""`metaseed hub`, `metaseed seek`, `metaseed plugin` and `metaseed ontology`.

The services are fakes here — the rules they follow are tested where they live
(``tests/test_hub``, ``tests/test_seek``); what is tested here is that the
commands reach them, report the outcome, and say what is missing rather than
raising a traceback at someone.
"""

from __future__ import annotations

import json
from typing import Any

import pytest
from typer.testing import CliRunner

import metaseed.cli.commands.hub as hub_commands
from metaseed.cli import app
from metaseed.repositories.dataset_repository import DatasetData
from metaseed.repositories.filesystem_dataset import FilesystemDatasetRepository
from metaseed.settings import Settings

runner = CliRunner()

ENTITIES = [{"_type": "Investigation", "identifier": "I1", "title": "An investigation"}]


class _FakeHub:
    url = "https://hub.test"

    def __init__(self) -> None:
        self.datasets: list[dict[str, Any]] = []
        self.specs: dict[tuple[str, str], str] = {}

    def me(self) -> dict[str, str]:
        return {
            "email": "me@example.org",
            "name": "Me",
            "tenant_id": "t1",
            "tenant_name": "T",
        }

    def list_datasets(self, tenant_id: str) -> list[dict[str, Any]]:
        return list(self.datasets)

    def get_dataset(self, dataset_id: str) -> dict[str, Any]:
        return next(d for d in self.datasets if d["id"] == dataset_id)

    def create_dataset(self, **kw: Any) -> dict[str, Any]:
        row = {"id": f"d{len(self.datasets) + 1}", **kw}
        self.datasets.append(row)
        return row

    def update_dataset(
        self, dataset_id: str, *, data: dict[str, Any]
    ) -> dict[str, Any]:
        row = self.get_dataset(dataset_id)
        row["data"] = data
        return row

    def list_specs(self) -> list[dict[str, Any]]:
        return [
            {
                "id": f"{vis[0]}-{n}-{v}",
                "name": n,
                "version": v,
                "description": None,
                "tenant_id": "t1",
                "content_hash": "h",
                "visibility": vis,
                "mine": True,
            }
            for (n, v), vis in self.specs.items()
        ]

    def get_spec(self, name: str, version: str) -> str:
        return "name: x\n"

    def push_spec(
        self, yaml_text: str, *, publish: bool = False
    ) -> tuple[dict[str, Any], bool]:
        vis = "published" if publish else "draft"
        self.specs[("test-local-profile", "1.0")] = vis
        return {
            "id": f"{vis[0]}-test-local-profile-1.0",
            "name": "test-local-profile",
            "version": "1.0",
            "content_hash": "abcdef123456789",
            "visibility": vis,
            "mine": True,
        }, True

    def unpublish_spec(self, spec_id: str) -> dict[str, Any]:
        self.specs[("test-local-profile", "1.0")] = "draft"
        return {"id": spec_id, "visibility": "draft"}


@pytest.fixture
def hub(monkeypatch: pytest.MonkeyPatch) -> _FakeHub:
    fake = _FakeHub()
    monkeypatch.setattr(hub_commands, "client", lambda: fake)
    return fake


@pytest.fixture
def saved() -> str:
    FilesystemDatasetRepository().save(
        "test-cli-hubbed",
        DatasetData(
            name="test-cli-hubbed",
            profile="isa",
            version="1.0",
            entities=list(ENTITIES),
        ),
    )
    return "test-cli-hubbed"


class TestHubCommands:
    def test_push_creates_it_and_records_where_it_went(
        self, hub: _FakeHub, saved: str
    ) -> None:
        result = runner.invoke(app, ["hub", "push-dataset", saved])
        assert result.exit_code == 0, result.output
        assert hub.datasets[0]["name"] == saved
        assert hub.datasets[0]["data"] == {"entities": ENTITIES}
        stamped = FilesystemDatasetRepository().load(saved)
        assert stamped.hub is not None
        assert stamped.hub["direction"] == "push"
        assert stamped.hub["hub"] == "https://hub.test"

    def test_plan_sends_nothing(self, hub: _FakeHub, saved: str) -> None:
        result = runner.invoke(app, ["hub", "push-dataset", saved, "--plan"])
        assert result.exit_code == 0, result.output
        assert json.loads(result.stdout)["would"] == "create"
        assert hub.datasets == []

    def test_a_differing_hub_dataset_is_not_replaced_without_being_asked(
        self, hub: _FakeHub, saved: str
    ) -> None:
        hub.datasets.append(
            {
                "id": "d1",
                "tenant_id": "t1",
                "name": saved,
                "profile": "isa",
                "version": "1.0",
                "data": {"entities": []},
            }
        )
        refused = runner.invoke(app, ["hub", "push-dataset", saved])
        assert refused.exit_code == 1
        assert "--replace" in refused.output
        assert hub.datasets[0]["data"] == {"entities": []}
        replaced = runner.invoke(app, ["hub", "push-dataset", saved, "--replace"])
        assert replaced.exit_code == 0, replaced.output
        assert hub.datasets[0]["data"] == {"entities": ENTITIES}

    def test_list_says_where_a_pull_would_land(self, hub: _FakeHub, saved: str) -> None:
        hub.datasets.append(
            {
                "id": "d1",
                "tenant_id": "t1",
                "name": saved,
                "profile": "isa",
                "version": "1.0",
                "data": {"entities": []},
            }
        )
        rows = json.loads(runner.invoke(app, ["hub", "list"]).stdout)
        assert rows[0]["pull_would"] == "beside"
        assert rows[0]["pull_as"] == f"{saved}-hub"

    def test_a_hub_name_the_store_cannot_hold_does_not_break_the_listing(
        self, hub: _FakeHub
    ) -> None:
        # A hub dataset named with a space is not a name this store can hold;
        # asking whether it is here must answer, not raise.
        hub.datasets.append(
            {
                "id": "d1",
                "tenant_id": "t1",
                "name": "not a local name",
                "profile": "isa",
                "version": "1.0",
                "data": {"entities": []},
            }
        )
        result = runner.invoke(app, ["hub", "list"])
        assert result.exit_code == 0, result.output
        assert json.loads(result.stdout)[0]["name"] == "not a local name"

    def test_pull_lands_beside_a_differing_local_dataset(
        self, hub: _FakeHub, saved: str
    ) -> None:
        hub.datasets.append(
            {
                "id": "d1",
                "tenant_id": "t1",
                "name": saved,
                "profile": "isa",
                "version": "1.0",
                "data": {"entities": []},
            }
        )
        result = runner.invoke(app, ["hub", "pull-dataset", "d1"])
        assert result.exit_code == 0, result.output
        store = FilesystemDatasetRepository()
        assert store.exists(f"{saved}-hub")
        assert store.load(saved).entities == ENTITIES, "the local one was kept"

    def test_without_a_configured_hub_the_command_says_so(self, tmp_path: Any) -> None:
        settings = Settings(tmp_path / "settings.json")
        original = hub_commands.Settings
        try:
            hub_commands.Settings = lambda: settings  # type: ignore[assignment,misc]
            result = runner.invoke(app, ["hub", "push-dataset", "test-cli-anything"])
        finally:
            hub_commands.Settings = original  # type: ignore[misc]
        assert result.exit_code == 3
        assert "Plugins" in result.output or "plugin config" in result.output

    def test_push_profile_is_a_draft_unless_publish_is_asked(
        self, hub: _FakeHub, tmp_path: Any, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        local = tmp_path / "specs" / "test-local-profile" / "1.0" / "profile.yaml"
        local.parent.mkdir(parents=True)
        local.write_text(
            "spec_version: '0.1'\nversion: '1.0'\nname: test-local-profile\nroot_entity: S\nentities: {S: {fields: []}}\n"
        )
        monkeypatch.setattr(hub_commands, "_specs_dir", lambda: tmp_path / "specs")
        result = runner.invoke(
            app, ["hub", "push-profile", "test-local-profile", "1.0"]
        )
        assert result.exit_code == 0, result.output
        assert "private draft" in result.output
        assert hub.specs[("test-local-profile", "1.0")] == "draft"
        result = runner.invoke(
            app, ["hub", "push-profile", "test-local-profile", "1.0", "--publish"]
        )
        assert "every hub user" in result.output
        assert hub.specs[("test-local-profile", "1.0")] == "published"
        result = runner.invoke(
            app, ["hub", "unpublish-profile", "test-local-profile", "1.0"]
        )
        assert result.exit_code == 0, result.output
        assert hub.specs[("test-local-profile", "1.0")] == "draft"
        result = runner.invoke(
            app, ["hub", "unpublish-profile", "test-local-profile", "1.0"]
        )
        assert result.exit_code == 2, "nothing published: nothing to withdraw"

    def test_profiles_says_draft_or_published_for_each_entry(
        self, hub: _FakeHub, tmp_path: Any, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # The listing used to call everything on the hub "published" -- the
        # one state the first version knew -- which is how a private draft
        # and a public specification looked the same.
        hub.specs[("test-local-profile", "1.0")] = "draft"
        hub.specs[("test-other", "2.0")] = "published"
        monkeypatch.setattr(hub_commands, "_specs_dir", lambda: tmp_path / "specs")
        result = runner.invoke(app, ["hub", "profiles"])
        assert result.exit_code == 0, result.output
        listed = {
            (s["name"], s["visibility"]) for s in json.loads(result.stdout)["on_hub"]
        }
        assert listed == {("test-local-profile", "draft"), ("test-other", "published")}


class TestPluginCommands:
    def test_list_reports_every_adapter(self) -> None:
        result = runner.invoke(app, ["plugin", "list"])
        assert result.exit_code == 0, result.output
        keys = {row["key"] for row in json.loads(result.stdout)}
        assert {"seek", "hub", "dcat"} <= keys

    def test_config_refuses_a_setting_the_adapter_does_not_have(self) -> None:
        result = runner.invoke(app, ["plugin", "config", "seek", "--set", "nonsense=1"])
        assert result.exit_code == 2
        assert "nonsense" in result.output

    def test_an_unknown_adapter_is_named_with_the_known_ones(self) -> None:
        result = runner.invoke(app, ["plugin", "enable", "nosuch"])
        assert result.exit_code == 2
        assert "seek" in result.output

    def test_a_secret_is_never_printed_back(self, tmp_path: Any) -> None:
        import metaseed.cli.commands.plugins as plugin_commands

        settings = Settings(tmp_path / "settings.json")
        settings.set_adapter_config(
            "hub", {"url": "https://hub.test", "token": "msh_secret"}
        )
        original = plugin_commands.Settings
        try:
            plugin_commands.Settings = lambda: settings  # type: ignore[assignment,misc]
            result = runner.invoke(app, ["plugin", "config", "hub"])
        finally:
            plugin_commands.Settings = original  # type: ignore[misc]
        assert result.exit_code == 0, result.output
        assert "msh_secret" not in result.output
        assert "(set)" in result.output


class TestSeekCommands:
    def test_preview_shows_the_sample_types_a_profile_would_create(self) -> None:
        result = runner.invoke(
            app, ["seek", "preview", "--profile", "isa", "--version", "1.0"]
        )
        assert result.exit_code == 0, result.output
        assert json.loads(result.stdout)["sample_types"], (
            "isa maps onto SEEK sample types"
        )

    def test_isa_templates_are_written_as_json(self, tmp_path: Any) -> None:
        out = tmp_path / "templates.json"
        result = runner.invoke(
            app,
            [
                "seek",
                "isa-templates",
                "--profile",
                "isa",
                "--version",
                "1.0",
                "--output",
                str(out),
            ],
        )
        assert result.exit_code == 0, result.output
        assert json.loads(out.read_text())["data"]

    def test_import_templates_is_reachable_under_the_group(self) -> None:
        result = runner.invoke(app, ["seek", "import-templates", "--help"])
        assert result.exit_code == 0
        assert "template" in result.output.lower()


class TestOntologyCommands:
    def test_search_prints_what_the_term_source_returns(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        class _Hit:
            def __init__(self) -> None:
                self.id = "PO:0007113"
                self.label = "rosette growth"

        class _Source:
            def search_sync(
                self, query: str, ontology: str | None = None, limit: int = 10
            ) -> list[_Hit]:
                return [_Hit()]

        source = _Source()
        monkeypatch.setattr("metaseed.services.terms.get_term_source", lambda: source)
        result = runner.invoke(app, ["ontology", "search", "rosette"])
        assert result.exit_code == 0, result.output
        assert json.loads(result.stdout)[0]["label"] == "rosette growth"

    def test_a_service_that_does_not_answer_is_not_checked_rather_than_failed(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        class _Source:
            def list_ontologies_sync(self, limit: int = 50) -> list[dict[str, str]]:
                raise RuntimeError("the service did not answer")

        source = _Source()
        monkeypatch.setattr("metaseed.services.terms.get_term_source", lambda: source)
        result = runner.invoke(app, ["ontology", "list"])
        assert result.exit_code == 0, (
            "someone else's downtime is not the user's failure"
        )
        assert json.loads(result.stdout)["checked"] is False
