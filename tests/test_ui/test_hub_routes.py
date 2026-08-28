"""The hub push/pull routes, against a fake hub.

The rules (plan before send, replace only when chosen, pull beside a differing
local dataset, profiles never overwritten) are tested on the library; here the
routes are checked to reach them, render the outcome, and stamp provenance.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

import metaseed.ui.routes.hub as hub_routes
from metaseed.hub.client import HubApiError
from metaseed.repositories.dataset_repository import DatasetData
from metaseed.settings import Settings
from metaseed.ui.app import create_app
from metaseed.ui.dataset_manager import resolve_dataset_manager
from metaseed.ui.state import AppState

ENTITIES = [
    {"_type": "Investigation", "identifier": "I1", "title": "inv"},
    {"_type": "Study", "identifier": "S1", "title": "study", "_parent_unique_id": "I1"},
]

PROFILE = """\
spec_version: '0.1'
version: '1.0'
name: test-local-profile
display_name: Local
description: A user-local profile.
root_entity: Study
entities:
  Study:
    description: A study.
    fields:
      - name: identifier
        type: string
        required: true
        is_identifier: true
"""


class _FakeHub:
    url = "https://hub.test"

    def __init__(self) -> None:
        self.datasets: list[dict[str, Any]] = []
        self.specs: dict[tuple[str, str], tuple[str, str, str]] = {}
        self.refuse_spec: str | None = None

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
                "content_hash": h,
                "visibility": vis,
                "mine": True,
            }
            for (n, v), (vis, h, _text) in self.specs.items()
        ]

    def get_spec(self, name: str, version: str) -> str:
        return self.specs[(name, version)][2]

    def push_spec(
        self, yaml_text: str, *, publish: bool = False
    ) -> tuple[dict[str, Any], bool]:
        if self.refuse_spec:
            raise HubApiError(409, self.refuse_spec)
        import yaml

        from metaseed.specs import content_hash
        from metaseed.specs.schema import ProfileSpec

        spec = ProfileSpec.model_validate(yaml.safe_load(yaml_text))
        key = (spec.name, spec.version)
        vis = "published" if publish else "draft"
        created = key not in self.specs or self.specs[key][0] != vis
        self.specs[key] = (vis, content_hash(spec), yaml_text)
        return {
            "id": f"{vis[0]}-{spec.name}-{spec.version}",
            "name": spec.name,
            "version": spec.version,
            "content_hash": content_hash(spec),
            "visibility": vis,
            "mine": True,
        }, created

    def unpublish_spec(self, spec_id: str) -> dict[str, Any]:
        key = next(
            k
            for k, (vis, _h, _t) in self.specs.items()
            if f"{vis[0]}-{k[0]}-{k[1]}" == spec_id
        )
        _vis, h, text = self.specs[key]
        self.specs[key] = ("draft", h, text)
        return {"id": spec_id, "visibility": "draft"}


@pytest.fixture
def hub(monkeypatch, tmp_path: Path) -> _FakeHub:
    fake = _FakeHub()
    monkeypatch.setattr(hub_routes, "hub_client_from_settings", lambda _config: fake)
    monkeypatch.setattr(hub_routes, "user_specs_dir", lambda: tmp_path / "specs")
    return fake


@pytest.fixture
def client(tmp_path: Path):
    state = AppState(profile="isa", version="1.0")
    app = create_app(state)
    settings = Settings(tmp_path / "settings.json")
    settings.set_adapter_enabled("hub", True)
    settings.set_adapter_config("hub", {"url": "https://hub.test", "token": "msh_x"})
    app.state.settings = settings
    manager = resolve_dataset_manager(app, state)
    manager.repository.save(
        "test-drought",
        DatasetData(
            name="test-drought", profile="isa", version="1.0", entities=ENTITIES
        ),
    )
    return TestClient(app), manager


def test_the_datasets_page_offers_push_and_pull_when_the_hub_is_enabled(
    client, hub
) -> None:
    page = client[0].get("/").text
    assert 'data-testid="btn-hub-pull"' in page
    assert 'data-testid="btn-hub-push-test-drought"' in page


def test_without_the_adapter_the_page_offers_nothing_and_the_routes_say_why(
    tmp_path: Path,
) -> None:
    state = AppState(profile="isa", version="1.0")
    app = create_app(state)
    app.state.settings = Settings(tmp_path / "settings.json")
    page = TestClient(app).get("/").text
    assert "btn-hub-pull" not in page
    response = TestClient(app).get("/hub/datasets/pull")
    assert "Settings" in response.text and "Metaseed Hub" in response.text


def test_a_push_is_planned_then_sent_and_stamps_provenance(client, hub) -> None:
    web, manager = client
    plan = web.get("/hub/datasets/test-drought/push")
    assert 'data-testid="hub-push-plan-create"' in plan.text
    assert hub.datasets == []
    done = web.post("/hub/datasets/test-drought/push")
    assert 'data-testid="hub-status-ok"' in done.text
    assert hub.datasets[0]["name"] == "test-drought"
    assert hub.datasets[0]["data"] == {"entities": ENTITIES}
    stamped = manager.repository.load("test-drought")
    assert stamped.hub["hub"] == "https://hub.test"
    assert stamped.hub["direction"] == "push"
    assert "Pushed" in web.get("/").text or "hub" in web.get("/").text


def test_a_differing_hub_dataset_is_replaced_only_on_request(client, hub) -> None:
    web, _manager = client
    hub.datasets.append(
        {
            "id": "d1",
            "tenant_id": "t1",
            "name": "test-drought",
            "profile": "isa",
            "version": "1.0",
            "data": {"entities": [ENTITIES[0]]},
        }
    )
    plan = web.get("/hub/datasets/test-drought/push")
    assert 'data-testid="hub-push-plan-differs"' in plan.text
    assert "Study S1" in plan.text
    refused = web.post("/hub/datasets/test-drought/push")
    assert 'data-testid="hub-status-warn"' in refused.text
    assert 'data-testid="btn-hub-replace"' in refused.text
    assert hub.datasets[0]["data"] == {"entities": [ENTITIES[0]]}
    replaced = web.post("/hub/datasets/test-drought/push", data={"replace": "1"})
    assert 'data-testid="hub-status-ok"' in replaced.text
    assert hub.datasets[0]["data"] == {"entities": ENTITIES}


def test_a_pull_lands_beside_a_differing_local_dataset(client, hub) -> None:
    web, manager = client
    hub.datasets.append(
        {
            "id": "d1",
            "tenant_id": "t1",
            "name": "test-drought",
            "profile": "isa",
            "version": "1.0",
            "data": {"entities": [ENTITIES[0]]},
        }
    )
    listing = web.get("/hub/datasets/pull")
    assert "test-drought-hub" in listing.text
    pulled = web.post("/hub/datasets/pull/d1")
    assert "test-drought-hub" in pulled.text
    assert manager.dataset_exists("test-drought-hub")
    assert manager.repository.load("test-drought").entities == ENTITIES
    assert manager.repository.load("test-drought-hub").hub["direction"] == "pull"


def test_a_pushed_profile_is_a_private_draft_and_publishing_is_a_separate_click(
    client, hub, tmp_path: Path
) -> None:
    web, _manager = client
    local = tmp_path / "specs" / "test-local-profile" / "1.0" / "profile.yaml"
    local.parent.mkdir(parents=True)
    local.write_text(PROFILE)
    panel = web.get("/hub/profiles").text
    assert 'data-testid="btn-hub-push-profile-test-local-profile-1.0"' in panel
    assert 'data-testid="btn-hub-publish-profile-test-local-profile-1.0"' in panel
    assert "not on the hub" in panel
    pushed = web.post("/hub/profiles/test-local-profile/1.0/push")
    assert "as your private draft" in pushed.text
    assert hub.specs[("test-local-profile", "1.0")][0] == "draft", (
        "a push publishes nothing"
    )
    panel = web.get("/hub/profiles").text
    assert "your draft" in panel
    assert 'data-testid="btn-hub-unpublish-profile-test-local-profile-1.0"' not in panel
    published = web.post(
        "/hub/profiles/test-local-profile/1.0/push", data={"publish": "1"}
    )
    assert "for every hub user" in published.text
    assert hub.specs[("test-local-profile", "1.0")][0] == "published"
    panel = web.get("/hub/profiles").text
    assert 'data-testid="btn-hub-unpublish-profile-test-local-profile-1.0"' in panel
    withdrawn = web.post("/hub/profiles/test-local-profile/1.0/unpublish")
    assert "private draft again" in withdrawn.text
    assert hub.specs[("test-local-profile", "1.0")][0] == "draft"


def test_a_hub_profile_that_is_not_here_can_be_pulled(
    client, hub, tmp_path: Path
) -> None:
    web, _manager = client
    hub.specs[("test-remote", "2.0")] = (
        "published",
        "h",
        PROFILE.replace("test-local-profile", "test-remote").replace("'1.0'", "'2.0'"),
    )
    panel = web.get("/hub/profiles").text
    assert 'data-testid="btn-hub-pull-profile-test-remote-2.0"' in panel
    pulled = web.post("/hub/profiles/test-remote/2.0/pull")
    assert "Pulled test-remote 2.0" in pulled.text
    assert (tmp_path / "specs" / "test-remote" / "2.0" / "profile.yaml").exists()


def test_the_hubs_refusal_of_a_profile_is_shown(client, hub, tmp_path: Path) -> None:
    web, _manager = client
    local = tmp_path / "specs" / "test-local-profile" / "1.0" / "profile.yaml"
    local.parent.mkdir(parents=True)
    local.write_text(PROFILE)
    hub.refuse_spec = (
        "'test-local-profile' 1.0 is already published with different content"
    )
    response = web.post("/hub/profiles/test-local-profile/1.0/push")
    assert 'data-testid="hub-status-error"' in response.text
    assert "different content" in response.text


def test_profile_push_and_pull_live_on_the_plugins_page_not_the_explorer(
    client,
) -> None:
    web, _manager = client
    assert 'data-testid="btn-hub-profiles"' in web.get("/settings").text
    assert 'data-testid="btn-hub-profiles"' not in web.get("/explore").text
