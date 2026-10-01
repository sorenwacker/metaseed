"""Every shipped example loads through the UI's Load Example route (#287).

The example tests validate each file against its root model, but the UI loads
it through the facade, which follows containment and references differently
from a Pydantic model: an example that validates and still cannot be loaded
is coverage that looks like a feature.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from metaseed.ui.app import create_app
from metaseed.ui.state import AppState
from tests.test_examples import get_all_example_files


@pytest.mark.parametrize(
    "profile,version,example_file",
    get_all_example_files(),
    ids=lambda x: x.name if hasattr(x, "name") else str(x),
)
def test_the_example_loads_and_opens_its_root(profile, version, example_file) -> None:
    state = AppState()
    client = TestClient(create_app(state), follow_redirects=True)

    response = client.get(f"/load-example/{profile}/{version}")

    assert response.status_code == 200, response.text[:300]
    assert state.facade is not None and state.facade.get_roots(), "nothing was loaded"
