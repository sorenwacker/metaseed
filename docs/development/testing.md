# Testing

MIAPPE-API uses pytest for testing with a multi-layered approach covering unit tests, integration tests, and end-to-end UI tests.

## Running Tests

```bash
# Run all tests (excluding UI tests)
make test

# Run tests with coverage
make test-cov

# Run UI tests (NiceGUI native tests)
make test-ui
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
│   ├── test_nicegui.py # NiceGUI native tests (primary)
│   ├── test_selenium.py # Selenium E2E tests (fallback)
│   ├── conftest.py     # UI test fixtures
│   └── main_test.py    # NiceGUI test entry point
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

## E2E UI Tests

### NiceGUI Native Tests (Recommended)

NiceGUI provides a built-in testing framework that simulates user interactions in Python without requiring a browser. This is faster and more reliable than Selenium.

#### Test Configuration

Tests use NiceGUI's `user_plugin` fixture:

```python
from nicegui import ui
from nicegui.testing import User

pytest_plugins = ["nicegui.testing.user_plugin"]

async def test_page_loads(user: User, app) -> None:
    await user.open("/")
    await user.should_see("MIAPPE-API")
```

#### Element Markers

Input elements are marked for easy selection:

```python
# In app.py - add markers to inputs
ui.input(label="title").mark("title")

# In tests - find by marker
title_input = user.find(kind=ui.input, marker="title")
title_input.type("My Title")
```

#### Test Patterns

```python
async def test_create_investigation(user: User, app) -> None:
    _ = app  # Ensure app fixture is loaded
    await user.open("/")

    # Click button by text content
    user.find("+ Investigation").click()

    # Fill form fields by marker
    user.find(kind=ui.input, marker="unique_id").type("INV-001")
    title_input = user.find(kind=ui.input, marker="title")
    title_input.type("Test Investigation")

    # Click create
    user.find("Create").click()

    # Assert results
    await user.should_see("Test Investigation")
    await user.should_not_see("No entities created")
```

### Selenium Tests (Alternative)

For testing browser-specific behaviors, Selenium tests are available.

#### Prerequisites

- Chrome browser installed
- ChromeDriver (automatically managed by webdriver-manager)

#### Test ID Convention

All interactive UI elements have `data-testid` attributes for reliable Selenium selection:

| Pattern | Description | Example |
|---------|-------------|---------|
| `select-profile` | Profile dropdown | `[data-testid='select-profile']` |
| `btn-new-{entity}` | New entity button | `[data-testid='btn-new-investigation']` |
| `btn-create-{entity}` | Form create button | `[data-testid='btn-create-investigation']` |
| `btn-save-{entity}` | Nested form save | `[data-testid='btn-save-study']` |
| `btn-clear-{entity}` | Form clear button | `[data-testid='btn-clear-investigation']` |
| `btn-cancel-{entity}` | Dialog cancel | `[data-testid='btn-cancel-study']` |
| `btn-add-{entity}` | Add nested entity | `[data-testid='btn-add-study']` |
| `btn-add-child-{entity}` | Add child entity | `[data-testid='btn-add-child-study']` |
| `btn-explore-{entity}` | Explore entity type | `[data-testid='btn-explore-study']` |
| `btn-set-{entity}` | Set single reference | `[data-testid='btn-set-location']` |
| `input-{field}` | Form input field | `[data-testid='input-unique-id']` |
| `tree-node-{id}` | Tree node | `[data-testid='tree-node-abc123']` |

#### Writing Selenium Tests

```python
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

def test_create_entity(driver, app_server):
    driver.get("http://127.0.0.1:8099")

    # Click new entity button
    btn = driver.find_element(By.CSS_SELECTOR, "[data-testid='btn-new-investigation']")
    btn.click()

    # Fill form field (note: input is nested inside NiceGUI component)
    container = driver.find_element(By.CSS_SELECTOR, "[data-testid='input-unique-id']")
    input_field = container.find_element(By.TAG_NAME, "input")
    input_field.send_keys("INV-001")

    # Submit
    create_btn = driver.find_element(By.CSS_SELECTOR, "[data-testid='btn-create-investigation']")
    create_btn.click()

    # Wait for result
    WebDriverWait(driver, 10).until(
        EC.presence_of_element_located((By.CSS_SELECTOR, "[data-testid^='tree-node-']"))
    )
```

### Debugging UI Tests

For NiceGUI tests, failed assertions print the full DOM tree.

For Selenium tests, take screenshots on failure:

```python
def test_something(driver):
    try:
        # test code
    except Exception:
        driver.save_screenshot("debug_screenshot.png")
        raise
```

## Markers

Tests are marked for selective execution:

- `@pytest.mark.ui` - UI tests (both NiceGUI and Selenium)

Run specific markers:

```bash
uv run pytest -m ui           # Only UI tests
uv run pytest -m "not ui"     # Exclude UI tests
```
