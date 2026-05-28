# Testing Best Practices

Guidelines for writing meaningful, maintainable tests in metaseed.

## Assertion Quality

### Avoid OR Conditions in Assertions

OR conditions can mask failures by passing when either condition matches.

```python
# Bad - passes if either matches, hiding specific failures
assert "error" in output or "warning" in output

# Good - be specific about expected output
assert "validation error" in output

# Good - if both should be present, use AND
assert "error" in output and "field: title" in output
```

### Use Exact Counts When Deterministic

Use `>=` only when the count can legitimately vary.

```python
# Bad - passes with any count >= 1
assert len(result["nodes"]) >= 1

# Good - verify exact expected count
assert len(result["nodes"]) == 3

# Good - use >= only when count varies (e.g., profiles may add entities)
assert len(profiles) >= 5  # At least the core profiles
```

### Avoid Trivial Type Checks

Type checks alone don't verify behavior.

```python
# Bad - trivial, always passes if object exists
assert hasattr(result, "total_entities")
assert isinstance(stats.total_entities, int)

# Good - verify meaningful values
assert hasattr(result, "total_entities")
assert isinstance(stats.total_entities, int)
assert stats.total_entities >= 0  # Meaningful constraint
```

### Verify Structure, Not Just String Presence

String presence checks are fragile and can match unintended content.

```python
# Bad - "table" could appear anywhere
assert "table" in response.text

# Good - check actual structure
assert response.text.count("<table") == 1
soup = BeautifulSoup(response.text, "html.parser")
assert soup.find("table", class_="data-table") is not None

# Good - for JSON, parse and verify
data = response.json()
assert "entities" in data
assert len(data["entities"]) == 3
```

## Test Organization

### Document Edge Case Behavior

Tests should document how code handles edge cases.

```python
def test_zero_value_is_valid(self):
    """Zero is treated as valid, not missing.

    RequiredFieldsRule only checks for None or empty string.
    Integer 0 and boolean False are valid values.
    """
    rule = RequiredFieldsRule(["count"])
    errors = rule.validate({"count": 0})
    assert len(errors) == 0
```

### Use Fixtures for Setup, Not Conditional Skips

Avoid `pytest.skip()` in error paths - use fixtures that guarantee setup.

```python
# Bad - silently skips if profile not available
def test_something(self):
    data = load_profile("miappe")
    if "error" in data:
        pytest.skip("Profile not available")
    # ... test code

# Good - fixture ensures profile is available
@pytest.fixture
def miappe_profile():
    """Load MIAPPE profile, fail if unavailable."""
    data = load_profile("miappe")
    assert "error" not in data, f"Profile unavailable: {data.get('error')}"
    return data

def test_something(self, miappe_profile):
    # Profile guaranteed to be available
    assert miappe_profile["name"] == "miappe"
```

### Use Decorators for Expected Failures

Use `@pytest.mark.xfail` decorator instead of conditional xfail.

```python
# Bad - conditional xfail inside test
def test_known_bug(self):
    result = do_something()
    if result.has_bug:
        pytest.xfail("Known issue")

# Good - decorator documents expected failure
@pytest.mark.xfail(reason="Known issue: orphan references remain after deletion")
def test_orphan_cleanup(self):
    """Deleting parent should clean up child references."""
    delete_parent(parent_id)
    # Assert the expected (correct) behavior
    assert child.parent_ref is None
```

### Verify Mock Calls

When using mocks, verify the code actually made the expected calls.

```python
# Bad - mock exists but never verified
def test_api_call(self):
    with patch("httpx.post") as mock_post:
        mock_post.return_value = Mock(json=lambda: {"ok": True})
        result = my_function()
        assert result["ok"] is True
        # Never verified mock was called!

# Good - verify mock was called correctly
def test_api_call(self):
    with patch("httpx.post") as mock_post:
        mock_post.return_value = Mock(json=lambda: {"ok": True})
        result = my_function()
        assert result["ok"] is True
        mock_post.assert_called_once_with(
            "https://api.example.com/endpoint",
            json={"key": "value"}
        )
```

## Test Coverage

### Test Both Valid and Invalid Cases

```python
class TestEmailValidation:
    def test_valid_email_accepted(self):
        """Valid email format passes validation."""
        assert validate_email("user@example.com") is True

    def test_invalid_email_rejected(self):
        """Invalid email format fails validation."""
        assert validate_email("not-an-email") is False

    def test_empty_email_rejected(self):
        """Empty string fails validation."""
        assert validate_email("") is False

    def test_none_email_rejected(self):
        """None value fails validation."""
        assert validate_email(None) is False
```

### Test Error Messages, Not Just Error Existence

```python
# Bad - only checks error exists
def test_validation_error(self):
    with pytest.raises(ValidationError):
        validate(invalid_data)

# Good - verify error message is helpful
def test_validation_error(self):
    with pytest.raises(ValidationError) as exc_info:
        validate({"title": ""})
    assert "title" in str(exc_info.value)
    assert "required" in str(exc_info.value).lower()
```

### Test Boundary Conditions

```python
class TestListCardinality:
    def test_exactly_min_items(self):
        """List with exactly min_items is valid."""
        rule = ListCardinalityRule("items", min_items=2)
        assert rule.validate({"items": ["a", "b"]}) == []

    def test_one_below_min_items(self):
        """List with min_items - 1 is invalid."""
        rule = ListCardinalityRule("items", min_items=2)
        errors = rule.validate({"items": ["a"]})
        assert len(errors) == 1

    def test_exactly_max_items(self):
        """List with exactly max_items is valid."""
        rule = ListCardinalityRule("items", max_items=3)
        assert rule.validate({"items": ["a", "b", "c"]}) == []

    def test_one_above_max_items(self):
        """List with max_items + 1 is invalid."""
        rule = ListCardinalityRule("items", max_items=3)
        errors = rule.validate({"items": ["a", "b", "c", "d"]})
        assert len(errors) == 1
```

## Naming Conventions

### Test Names Should Describe Behavior

```python
# Bad - vague names
def test_validation(self): ...
def test_error(self): ...
def test_success(self): ...

# Good - describes what is being tested and expected outcome
def test_missing_required_field_returns_validation_error(self): ...
def test_valid_email_format_passes_validation(self): ...
def test_empty_list_treated_as_missing_for_required_field(self): ...
```

### Use Consistent Class Organization

```python
class TestInvestigationValidation:
    """Tests for Investigation entity validation."""

    # Setup fixtures first
    @pytest.fixture
    def valid_investigation(self):
        return {"unique_id": "INV-001", "title": "Test"}

    # Test valid cases
    def test_valid_investigation_passes(self, valid_investigation): ...

    # Test invalid cases
    def test_missing_unique_id_fails(self): ...
    def test_missing_title_fails(self): ...

    # Test edge cases
    def test_empty_string_title_fails(self): ...
    def test_whitespace_only_title_fails(self): ...
```

## Running Tests

```bash
# Run all tests
uv run pytest

# Run with coverage
uv run pytest --cov=src/metaseed --cov-report=term-missing

# Run specific test file
uv run pytest tests/test_validators/test_rules.py -v

# Run tests matching pattern
uv run pytest -k "test_validation" -v

# Run and stop on first failure
uv run pytest -x

# Run with parallel execution
uv run pytest -n auto
```
