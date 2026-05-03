# Logging

Metaseed uses Python's standard logging module for diagnostic output.

## CLI Logging

Use the `--verbose` or `-V` flag to enable debug logging:

```bash
# Normal output (warnings only)
metaseed compare miappe/1.1 isa/1.0

# Verbose output (debug messages)
metaseed --verbose compare miappe/1.1 isa/1.0
metaseed -V merge miappe/1.1 isa/1.0 -o merged.yaml
```

## Environment Variable

Set `METASEED_LOG_LEVEL` to control logging without the flag:

```bash
# Enable debug logging globally
export METASEED_LOG_LEVEL=DEBUG

# Available levels: DEBUG, INFO, WARNING, ERROR, CRITICAL
export METASEED_LOG_LEVEL=INFO
```

## Python API

Configure logging programmatically:

```python
from metaseed.logging import configure_logging

# Debug logging to stderr
configure_logging(level="DEBUG")

# Info logging with CLI-friendly format
configure_logging(level="INFO", cli_mode=True)

# Custom stream
import sys
configure_logging(level="INFO", stream=sys.stdout)
```

## Log Format

**Standard format** (UI/library):
```
2024-01-15 10:30:45 INFO     metaseed.specs.merge.comparator: Comparing 2 profiles
```

**CLI format** (`cli_mode=True`):
```
INFO: Comparing 2 profiles
```

## Module Loggers

Each module uses its own logger via `logging.getLogger(__name__)`:

| Logger | Description |
|--------|-------------|
| `metaseed.specs.loader` | Profile loading and caching |
| `metaseed.specs.merge.comparator` | Profile comparison |
| `metaseed.specs.merge.merger` | Profile merging |
| `metaseed.ui.app` | Web UI startup |
| `metaseed.ui.routes.validation` | Form validation |

## Log Levels

| Level | Usage |
|-------|-------|
| DEBUG | Detailed diagnostic info (file paths, cache hits, entity counts) |
| INFO | General operational messages (comparison started, merge complete) |
| WARNING | Potential issues (failed to load profile, empty file) |
| ERROR | Errors preventing specific operations |
| CRITICAL | Severe errors that may cause shutdown |
