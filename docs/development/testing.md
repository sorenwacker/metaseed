# Testing

MIAPPE-API uses pytest for testing with a multi-layered approach covering unit tests, integration tests, and end-to-end UI tests.

## Running Tests

```bash
# Run all tests (excluding UI tests)
make test

# Run tests with coverage
make test-cov

# Run UI tests (requires Chrome)
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
├── test_ui/            # Selenium E2E tests
│   └── test_selenium.py
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

## E2E UI Tests (Selenium)

End-to-end tests verify the complete user workflow through the web interface.

### Prerequisites

- Chrome browser installed
- ChromeDriver (automatically managed by webdriver-manager)

### Test ID Convention

All interactive UI elements have `data-testid` attributes for reliable Selenium selection:

| Pattern | Description | Example |
|---------|-------------|---------|
| `select-profile` | Profile dropdown | `[data-testid='select-profile']` |
| `btn-new-{entity}` | New entity button in sidebar | `[data-testid='btn-new-investigation']` |
| `btn-create-{entity}` | Form create button | `[data-testid='btn-create-investigation']` |
| `btn-save-{entity}` | Nested form save button | `[data-testid='btn-save-study']` |
| `btn-clear-{entity}` | Form clear button | `[data-testid='btn-clear-investigation']` |
| `btn-cancel-{entity}` | Dialog cancel button | `[data-testid='btn-cancel-study']` |
| `btn-add-{entity}` | Add nested entity button | `[data-testid='btn-add-study']` |
| `btn-add-child-{entity}` | Add child in detail view | `[data-testid='btn-add-child-study']` |
| `btn-explore-{entity}` | Explore entity type | `[data-testid='btn-explore-study']` |
| `btn-set-{entity}` | Set single entity ref | `[data-testid='btn-set-location']` |
| `input-{field}` | Form input field | `[data-testid='input-unique-id']` |
| `tree-node-{id}` | Tree node in sidebar | `[data-testid='tree-node-abc123']` |

### Writing UI Tests

```python
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

def test_create_entity(driver, app_server):
    driver.get("http://127.0.0.1:8099")

    # Click new entity button
    btn = driver.find_element(By.CSS_SELECTOR, "[data-testid='btn-new-investigation']")
    btn.click()

    # Fill form field (note: input is nested inside the component)
    input_field = driver.find_element(By.CSS_SELECTOR, "[data-testid='input-unique-id'] input")
    input_field.send_keys("INV-001")

    # Submit
    create_btn = driver.find_element(By.CSS_SELECTOR, "[data-testid='btn-create-investigation']")
    create_btn.click()

    # Verify backend state
    assert len(app_server.entity_tree) == 1
    assert app_server.entity_tree[0].instance.unique_id == "INV-001"
```

### Test Architecture

The UI tests use a class-scoped fixture pattern:

1. `app_server` fixture starts NiceGUI in a daemon thread
2. `driver` fixture creates a headless Chrome WebDriver
3. Tests interact with the UI and verify backend state via `app_server`

```python
@pytest.fixture(scope="class")
def app_server():
    app = MIAPPEApp()
    thread = threading.Thread(target=lambda: app.run(port=8099), daemon=True)
    thread.start()
    time.sleep(2)  # Wait for server
    yield app

@pytest.fixture(scope="class")
def driver(app_server):
    options = Options()
    options.add_argument("--headless")
    driver = webdriver.Chrome(options=options)
    yield driver
    driver.quit()
```

### Debugging UI Tests

Run tests with visible browser:

```python
# Remove --headless from options
options = Options()
# options.add_argument("--headless")  # Comment out for debugging
```

Take screenshots on failure:

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

- `@pytest.mark.ui` - UI tests requiring Chrome

Run specific markers:

```bash
uv run pytest -m ui           # Only UI tests
uv run pytest -m "not ui"     # Exclude UI tests
```
