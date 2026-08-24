"""Route tests for the SEEK export page — gated by the plugin feature switch."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from metaseed.settings import Settings
from metaseed.ui.app import create_app
from metaseed.ui.state import AppState


@pytest.fixture
def make_client(tmp_path):
    def _make() -> tuple[TestClient, Settings, AppState]:
        state = AppState(profile="isa", version="1.0")
        app = create_app(state)
        settings = Settings(tmp_path / "settings.json")
        app.state.settings = settings
        return TestClient(app), settings, state

    return _make


def test_seek_page_empty_state_when_no_dataset(make_client):
    client, _settings, _state = make_client()  # seek enabled, empty dataset
    response = client.get("/seek")
    assert response.status_code == 200
    assert 'data-testid="seek-sync-empty"' in response.text  # nothing to sync
    assert 'data-testid="seek-export-disabled"' in response.text  # download disabled
    assert 'data-testid="seek-needs-key"' in response.text  # no API key configured


def test_seek_page_shows_context_when_dataset_loaded(make_client):
    client, _settings, _state = make_client()
    client.post(
        "/entity",
        data={"_entity_type": "Investigation", "identifier": "INV1", "title": "T"},
    )
    response = client.get("/seek")
    assert response.status_code == 200
    assert "isa" in response.text  # profile shown
    assert "Investigation ×1" in response.text  # entity preview  # noqa: RUF001
    assert 'data-testid="seek-export-rdf"' in response.text  # download enabled
    assert 'data-testid="seek-sync-form"' in response.text  # sync offered


def test_seek_page_disables_export_when_no_exportable_types(make_client):
    # A dataset made only of entities the FDS export never emits (e.g. Person)
    # must NOT show an enabled download that yields an empty file.
    client, _settings, state = make_client()
    client.post(
        "/entity",
        data={"_entity_type": "Person", "identifier": "P1", "last_name": "Doe"},
    )
    assert [n.entity_type for n in state.nodes_by_id.values()] == ["Person"]
    response = client.get("/seek")
    assert response.status_code == 200
    assert 'data-testid="seek-sync-empty"' in response.text
    assert 'data-testid="seek-export-disabled"' in response.text
    assert 'data-testid="seek-export-rdf"' not in response.text
    assert "Person ×1" not in response.text  # not in "Will emit"  # noqa: RUF001


def test_seek_page_hidden_when_disabled(make_client):
    client, settings, _state = make_client()
    settings.set_adapter_enabled("seek", False)
    assert client.get("/seek").status_code == 404
    assert client.get("/seek/isa-rdf").status_code == 404
    assert client.get("/seek/model-ttl").status_code == 404
    assert client.post("/seek/provision").status_code == 404
    assert client.post("/seek/sync").status_code == 404


def test_model_ttl_downloads_profile_definitions(make_client):
    client, _settings, _state = make_client()
    response = client.get("/seek/model-ttl")
    assert response.status_code == 200
    assert "text/turtle" in response.headers["content-type"]
    assert "rdf:Property" in response.text or "schema:valueRequired" in response.text
    assert response.headers["content-disposition"].endswith('-model.ttl"')


def test_model_ttl_honors_selected_profile(make_client):
    # A different profile can be exported than the active session profile.
    client, _settings, _state = make_client()  # active profile is isa
    response = client.get("/seek/model-ttl", params={"profile": "miappe"})
    assert response.status_code == 200
    assert response.headers["content-disposition"].endswith('"miappe-model.ttl"')


def test_seek_page_offers_a_profile_selector(make_client):
    client, _settings, _state = make_client()
    page = client.get("/seek").text
    assert 'data-testid="seek-model-profile"' in page
    assert ">miappe</option>" in page and ">isa</option>" in page  # multiple profiles


def test_model_ttl_unknown_profile_does_not_reflect_input(make_client):
    # A crafted profile value must not be echoed back into the HTML response.
    client, _settings, _state = make_client()
    payload = "<script>alert(1)</script>"
    response = client.get("/seek/model-ttl", params={"profile": payload})
    assert response.status_code == 400
    assert payload not in response.text  # no reflected XSS
    assert "<script>" not in response.text


def test_provision_without_config_reports_error(make_client):
    # No SEEK url/key configured -> a readable error, not a crash or network call.
    client, _settings, _state = make_client()
    response = client.post("/seek/provision", data={"project_id": ""})
    assert response.status_code == 200
    assert 'data-testid="seek-action-error"' in response.text
    assert "SEEK URL" in response.text


def test_sync_without_dataset_reports_error(make_client):
    client, _settings, _state = make_client()  # empty dataset
    response = client.post("/seek/sync", data={"project_id": ""})
    assert response.status_code == 200
    assert 'data-testid="seek-action-error"' in response.text
    assert "No dataset" in response.text


def test_isa_rdf_download_requires_a_dataset(make_client):
    client, _settings, _state = make_client()  # empty state
    assert client.get("/seek/isa-rdf").status_code == 400


def test_isa_rdf_exports_the_current_dataset(make_client):
    client, _settings, _state = make_client()
    client.post(
        "/entity",
        data={"_entity_type": "Investigation", "identifier": "INV1", "title": "T"},
    )
    response = client.get("/seek/isa-rdf")
    assert response.status_code == 200
    assert "text/turtle" in response.headers["content-type"]
    assert "jerm:Investigation" in response.text
    assert response.headers["content-disposition"].endswith('-seek.ttl"')


def test_download_filename_is_sanitized(make_client):
    # A dataset name with quotes/unicode/newlines must not break the header.
    client, _settings, state = make_client()
    client.post(
        "/entity",
        data={"_entity_type": "Investigation", "identifier": "INV1", "title": "T"},
    )
    from metaseed.ui.datasets import set_current_dataset_name

    set_current_dataset_name(state, 'ev"il\nΩ name')
    response = client.get("/seek/isa-rdf")
    assert response.status_code == 200
    disposition = response.headers["content-disposition"]
    assert disposition.isascii()  # no latin-1 encode crash
    filename = disposition.split("filename=", 1)[1].strip('"')
    assert '"' not in filename and "\n" not in filename  # no header injection
    assert filename == "ev-il-name-seek.ttl"


def test_the_page_offers_one_profile_choice_not_two(make_client):
    """Two "Model (profile)" dropdowns could disagree -- provisioning one profile
    while handing an admin the Extended Metadata of another. There is now a single
    selector, and the Extended Metadata form mirrors it via a hidden field."""
    client, _settings, _state = make_client()
    html = client.get("/seek").text

    assert html.count('id="seek-profile"') == 1
    assert html.count('id="seek-emt-profile"') == 1
    assert "Model (profile)" not in html  # the old, duplicated label is gone


def test_the_page_does_not_pass_a_default_profile_off_as_a_loaded_dataset(make_client):
    """The page reported "loaded now: <profile>", which was the app's default
    profile whether or not any dataset was open. The sync step now speaks to the
    actual dataset, and says plainly when none is loaded."""
    client, _settings, _state = make_client()
    html = client.get("/seek").text

    assert "loaded now" not in html
    assert 'data-testid="seek-sync-empty"' in html
    assert "No dataset is loaded" in html


def test_the_page_avoids_the_worst_jargon(make_client):
    client, _settings, _state = make_client()
    html = client.get("/seek").text

    assert "Idempotent" not in html and "idempotent" not in html
    assert "sample-bearing" not in html
    assert "closed value lists" not in html


def test_the_page_lets_you_choose_a_version(make_client):
    """Provisioning always used a profile's latest version, so a profile with
    several -- miappe 1.1/1.2 -- could not be set up at an older one, even when a
    dataset was built on it. The setup step now offers a version selector."""
    client, _settings, _state = make_client()
    html = client.get("/seek").text

    assert 'data-testid="seek-model-version"' in html
    assert 'name="version"' in html


def test_the_model_download_honours_the_requested_version(make_client):
    """A version that is not the latest must actually load that version, not be
    silently replaced by the newest."""
    client, _settings, _state = make_client()

    v11 = client.get("/seek/model-ttl", params={"profile": "miappe", "version": "1.1"})
    v12 = client.get("/seek/model-ttl", params={"profile": "miappe", "version": "1.2"})

    assert v11.status_code == 200 and v12.status_code == 200
    # The two versions differ, so honouring the request produces different output;
    # ignoring it and loading the latest for both would make them identical.
    assert v11.content != v12.content


def _sync_result(created=8, skipped=0, errored=0):
    from metaseed.seek.sync import SyncResult

    r = SyncResult()
    r.investigations = {f"i{n}": str(n) for n in range(min(created, 1))}
    r.samples = {f"s{n}": str(n) for n in range(max(created - 1, 0))}
    r.skipped = [(f"k{n}", "no SEEK role") for n in range(skipped)]
    r.errors = [(f"e{n}", "boom") for n in range(errored)]
    return r


def test_a_partial_sync_warns_rather_than_reporting_success(make_client):
    """Syncing 8 of 49 entities used to show a green 'Synced 8 resources' with
    the 41 that failed greyed out below -- reading as full success. A sync that
    left anything behind must say so, and how much."""
    from jinja2 import Environment, FileSystemLoader

    # Render the template directly with a partial result.
    import metaseed.ui.app as appmod

    env = Environment(
        loader=FileSystemLoader(str(appmod.TEMPLATES_DIR)), autoescape=True
    )
    html = env.get_template("seek/index.html").render(
        base_url="",
        profile="p",
        version="1.0",
        profiles=["p"],
        profile_versions={"p": ["1.0"]},
        dataset_name="d",
        exportable_count=0,
        entity_counts=[],
        api_key_configured=True,
        projects=[("1", "P")],
        seek_url="http://x",
        provision_result=None,
        action_error=None,
        sync_result=_sync_result(created=8, skipped=28, errored=9),
    )
    assert "not uploaded" in html
    assert "notification-warning" in html
    assert "notification-success" not in html.split("seek-sync-result")[1][:400]
    assert "37" in html  # 28 skipped + 9 errored


def test_a_complete_sync_still_reads_as_success(make_client):
    from jinja2 import Environment, FileSystemLoader

    import metaseed.ui.app as appmod

    env = Environment(
        loader=FileSystemLoader(str(appmod.TEMPLATES_DIR)), autoescape=True
    )
    html = env.get_template("seek/index.html").render(
        base_url="",
        profile="p",
        version="1.0",
        profiles=["p"],
        profile_versions={"p": ["1.0"]},
        dataset_name="d",
        exportable_count=0,
        entity_counts=[],
        api_key_configured=True,
        projects=[("1", "P")],
        seek_url="http://x",
        provision_result=None,
        action_error=None,
        sync_result=_sync_result(created=8, skipped=0, errored=0),
    )
    # The success banner, not the warning one.
    assert "notification-success" in html
    assert "notification-warning" not in html
    assert "not uploaded" not in html


def test_seek_page_shows_model_preview_panel(make_client):
    # The page carries the browsable "what will be created" panel on load.
    client, _settings, _state = make_client()  # default profile isa/1.0
    response = client.get("/seek")
    assert response.status_code == 200
    assert 'data-testid="seek-preview"' in response.text
    assert "Sample Types" in response.text
    assert "Extended Metadata" in response.text


def test_seek_preview_endpoint_lists_sample_types_and_extended_metadata(make_client):
    # The HTMX partial projects a chosen profile/version: Sample Types with
    # their columns, and the Extended Metadata records with their fields.
    client, _settings, _state = make_client()
    response = client.get(
        "/seek/preview", params={"profile": "seek-ready-template", "version": "1.0"}
    )
    assert response.status_code == 200
    body = response.text
    assert "Sample" in body  # the Sample-role sample type
    assert "organism" in body  # one of its columns
    assert "Study" in body  # an ISA record under Extended Metadata
    assert "study_design_type" in body  # a Study Extended-Metadata field


def test_seek_preview_endpoint_degrades_on_unknown_profile(make_client):
    client, _settings, _state = make_client()
    response = client.get("/seek/preview", params={"profile": "no-such-profile"})
    assert response.status_code == 200  # never 500 — the panel just hides
    assert 'data-testid="seek-preview-empty"' in response.text


def test_the_page_preselects_the_saved_project(make_client, monkeypatch):
    import metaseed.ui.routes.seek as seek_routes
    from metaseed.seek.connection import ConnectionCheck

    client, settings, _state = make_client()
    settings.set_adapter_config(
        "seek", {"url": "http://seek.test", "api_key": "k", "project_id": "2"}
    )
    monkeypatch.setattr(
        seek_routes,
        "check_connection",
        lambda _config, **_kw: ConnectionCheck(
            ok=True, message="Connected", projects=[("1", "Plants"), ("2", "Soil")]
        ),
    )
    page = client.get("/seek").text
    assert '<option value="2" selected' in page


def test_the_page_explains_why_there_are_no_projects(make_client, monkeypatch):
    import metaseed.ui.routes.seek as seek_routes
    from metaseed.seek.connection import ConnectionCheck

    client, settings, _state = make_client()
    settings.set_adapter_config("seek", {"url": "http://seek.test", "api_key": "bad"})
    monkeypatch.setattr(
        seek_routes,
        "check_connection",
        lambda _config, **_kw: ConnectionCheck(
            ok=False, message="SEEK rejected the API key.", projects=[]
        ),
    )
    page = client.get("/seek").text
    assert 'data-testid="seek-no-projects"' in page
    assert "rejected the API key" in page


def test_an_action_keeps_the_profile_you_chose(make_client):
    # The loaded dataset is ISA; the user provisions MIAPPE. The page that comes
    # back must still show MIAPPE, not fall back to the dataset's profile.
    client, _settings, _state = make_client()
    page = client.post(
        "/seek/provision",
        data={"project_id": "", "profile": "miappe", "version": "1.2"},
    ).text
    assert 'data-testid="seek-action-error"' in page  # no SEEK configured
    assert '<option value="miappe" selected' in page
    assert '<option value="1.2" selected' in page


def test_seek_page_offers_the_isa_templates_download(make_client):
    # The sync refuses to run without the profile's ISA Templates installed and
    # its error says to download them "from the SEEK page" — so the page must
    # actually offer that download, wired to the chosen profile and version.
    client, _settings, _state = make_client()
    response = client.get("/seek")
    assert response.status_code == 200
    assert 'data-testid="seek-isa-templates"' in response.text
    assert "/seek/isa-templates" in response.text
    assert 'id="seek-tpl-profile"' in response.text  # kept in step with the chooser
    assert 'id="seek-tpl-version"' in response.text


def test_the_preview_of_a_template_bound_profile_names_its_templates(
    make_client, tmp_path, monkeypatch
):
    # A profile installed under the user data dir whose entities name installed
    # ISA Templates: the preview lists the templates with levels and tags, and
    # swaps the step-1 button label to say provisioning creates only the
    # Controlled Vocabularies (the Sample Types come from the templates).
    import yaml

    from tests.test_seek.test_template_bound import _SPEC

    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    spec_dir = tmp_path / "metaseed" / "specs" / "cropxr-mini" / "1.0"
    spec_dir.mkdir(parents=True)
    (spec_dir / "profile.yaml").write_text(yaml.safe_dump(_SPEC, sort_keys=False))
    client, _settings, _state = make_client()
    response = client.get(
        "/seek/preview", params={"profile": "cropxr-mini", "version": "1.0"}
    )
    assert response.status_code == 200
    assert "CropXR phenotyping observation unit" in response.text
    assert "assay - material" in response.text
    assert 'id="seek-provision-label" hx-swap-oob' in response.text
    assert "Set up Controlled Vocabularies" in response.text


def test_a_value_left_out_of_a_pushed_record_is_a_note_not_a_missing_entity(
    make_client,
):
    """An attribute the Extended Metadata Type cannot take (a record reference)
    is left out of a Study or Assay that DID reach SEEK. The page used to count
    it as an entity that was not uploaded and declare the copy incomplete."""
    from jinja2 import Environment, FileSystemLoader

    import metaseed.ui.app as appmod

    result = _sync_result(created=8)
    result.notes = [
        ("a1", "'X' holds a reference to a SEEK record, not a value, for: f")
    ]
    env = Environment(
        loader=FileSystemLoader(str(appmod.TEMPLATES_DIR)), autoescape=True
    )
    html = env.get_template("seek/index.html").render(
        base_url="",
        profile="p",
        version="1.0",
        profiles=["p"],
        profile_versions={"p": ["1.0"]},
        dataset_name="d",
        exportable_count=0,
        entity_counts=[],
        api_key_configured=True,
        projects=[("1", "P")],
        seek_url="http://x",
        provision_result=None,
        action_error=None,
        sync_result=result,
    )
    assert "not uploaded" not in html
    assert "did not reach SEEK" not in html
    assert "notification-success" in html
    assert "seek-sync-notes" in html and "Values not sent" in html
