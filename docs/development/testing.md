# Testing

MIAPPE-API uses pytest for testing with a multi-layered approach covering unit tests, integration tests, and end-to-end UI tests.

## Running Tests

```bash
# Run all tests
uv run pytest

# Run tests with coverage
uv run pytest --cov=miappe_api

# Run only UI tests
uv run pytest tests/test_ui/ -v

# Run Selenium tests (visible browser)
uv run pytest tests/test_ui/test_selenium.py -v
```

## Test Structure

```
tests/
├── test_api/           # REST API endpoint tests
├── test_cli/           # CLI command tests
├── test_facade.py      # ProfileFacade tests
├── test_models/        # Pydantic model factory tests
├── test_specs/         # YAML spec loading tests
├── test_storage/       # JSON/YAML storage tests
├── test_validators/    # Validation rule tests
├── test_ui/            # UI tests
│   ├── test_htmx.py    # HTMX route tests (FastAPI TestClient)
│   └── test_selenium.py # Selenium E2E tests (visible browser)
└── test_version.py
```

## Unit Tests

Unit tests cover individual components in isolation:

- **Models**: Test Pydantic model generation from specs
- **Validators**: Test validation rules (required fields, date ranges, entity references)
- **Storage**: Test JSON/YAML serialization and loading
- **Specs**: Test YAML spec parsing and entity loading

## Integration Tests

Integration tests verify component interactions:

- **CLI**: Test command execution with real file I/O
- **API**: Test REST endpoints with TestClient
- **Facade**: Test entity creation through the facade pattern

## UI Tests

The UI is built with HTMX + FastAPI + Jinja2 templates. Two test approaches are used:

### HTMX Route Tests (TestClient)

Fast, headless tests using FastAPI's TestClient to verify route behavior and HTML responses.

```python
from fastapi.testclient import TestClient
from miappe_api.ui.routes import AppState, create_app

def test_create_entity(client):
    response = client.post(
        "/entity",
        data={
            "_entity_type": "Investigation",
            "unique_id": "INV-001",
            "title": "Test Investigation",
        },
    )
    assert response.status_code == 200
    assert "Created Investigation" in response.text
```

### Selenium E2E Tests (Visible Browser)

End-to-end tests with a visible Chrome browser for demonstrating and verifying UI interactions.

#### Prerequisites

- Chrome browser installed
- ChromeDriver (managed by selenium)

#### Running Selenium Tests

```bash
# Run all Selenium tests
uv run pytest tests/test_ui/test_selenium.py -v

# Stop on first failure
uv run pytest tests/test_ui/test_selenium.py -v -x --tb=short
```

#### Test Configuration

Tests use a module-scoped server fixture that starts uvicorn on port 8081:

```python
@pytest.fixture(scope="module")
def server():
    """Start the MIAPPE-API server for testing."""
    proc = subprocess.Popen(
        ["uv", "run", "uvicorn", "miappe_api.ui.routes:app", "--port", "8081"],
        ...
    )
    # Wait for server to be ready
    yield proc
    proc.terminate()

@pytest.fixture
def browser(_server):
    """Create a visible Chrome browser for testing."""
    options = Options()
    options.add_argument("--window-size=1280,900")
    driver = webdriver.Chrome(options=options)
    yield driver
    driver.quit()
```

#### Test ID Convention

All interactive UI elements have `data-testid` attributes for reliable selection:

| Element | Pattern | Example |
|---------|---------|---------|
| Create entity button | `btn-create-{EntityType}` | `btn-create-Investigation` |
| Tree node | `tree-node-{node_id}` | `tree-node-abc123` |
| Delete node button | `btn-delete-{node_id}` | `btn-delete-abc123` |
| Entity form | `form-entity` | `form-entity` |
| Input field | `input-{field-name}` | `input-unique-id` |
| Create button | `btn-create` | `btn-create` |
| Update button | `btn-update` | `btn-update` |
| Optional fields toggle | `section-optional-toggle` | `section-optional-toggle` |
| Nested field button | `btn-nested-{field-name}` | `btn-nested-contacts` |
| Table add row | `table-add-row` | `table-add-row` |
| Table save | `table-save` | `table-save` |
| Table count | `table-count` | `table-count` |
| Table cell | `cell-{row}-{column}` | `cell-0-name` |
| Notification | `notification` | `notification` |

#### Helper Functions

The test file provides helper functions for common operations:

```python
def fill_field(driver, testid: str, value: str, trigger_change: bool = False):
    """Fill a form field by data-testid."""

def click_button(driver, testid: str):
    """Click a button by data-testid and wait."""

def element_exists(driver, testid: str) -> bool:
    """Check if an element with given data-testid exists."""

def expand_optional_fields(driver):
    """Expand the optional fields section if collapsed."""
```

#### Example Test

```python
@pytest.mark.ui
class TestCreateInvestigation:
    def test_create_investigation(self, browser):
        browser.get("http://127.0.0.1:8081")

        # Click create button
        click_button(browser, "btn-create-Investigation")

        # Fill required fields
        fill_field(browser, "input-unique-id", "INV-001")
        fill_field(browser, "input-title", "Test Investigation")

        # Submit
        click_button(browser, "btn-create")

        # Verify entity appears in sidebar
        sidebar = browser.find_element(By.ID, "sidebar")
        assert "Test Investigation" in sidebar.text
```

#### Date Input Handling

For date inputs, JavaScript is used to set values directly (avoids locale-specific formatting issues):

```python
if element.get_attribute("type") == "date":
    driver.execute_script("arguments[0].value = arguments[1]", element, "2024-03-15")
```

#### Triggering HTMX Events

When filling table cells that have HTMX handlers, trigger the change event:

```python
fill_field(browser, "cell-0-name", "Dr. Smith", trigger_change=True)
```

## Selenium Test Coverage

The following end-to-end tests are implemented:

| Test Class | Test Method | Description |
|------------|-------------|-------------|
| `TestCreateInvestigationRequiredFields` | `test_create_investigation_required_fields` | Create Investigation with only required fields |
| `TestCreateInvestigationAllFields` | `test_create_investigation_all_fields` | Create Investigation with all optional fields |
| `TestAddNestedContacts` | `test_add_nested_contacts` | Add contacts through nested table |
| `TestEditInvestigation` | `test_edit_investigation` | Edit existing entity and verify persistence |
| `TestDeleteInvestigation` | `test_delete_investigation` | Delete entity and verify removal |
| `TestAddNestedStudy` | `test_add_nested_study` | Add Study through nested table |
| `TestValidationError` | `test_validation_error_missing_required` | Verify HTML5 validation on required fields |
| `TestProfileSwitch` | `test_switch_profile_clears_state` | Switch profile and verify state cleared |

## Markers

Tests are marked for selective execution:

- `@pytest.mark.ui` - UI tests (Selenium)

Run specific markers:

```bash
uv run pytest -m ui           # Only UI tests
uv run pytest -m "not ui"     # Exclude UI tests
```
