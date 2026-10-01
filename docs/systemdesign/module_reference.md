# Module Reference: Architecture & File Index

## Status

Complete (v0.2.0)

---

## Related Files

### Domain Layer
- `src/btx_jev_judge/domain/models.py`  -  Questions, items, answers, rows and outcomes
- `src/btx_jev_judge/domain/redaction.py`  -  Secret redaction and string capping
- `src/btx_jev_judge/domain/summary.py`  -  Run summary: distribution, uncertain rows, flat questions
- `src/btx_jev_judge/domain/enums.py`  -  Type-safe enums (QuestionType, OutputFormat, DeployTarget)
- `src/btx_jev_judge/domain/errors.py`  -  InputError and ConfigurationError

### Application Layer
- `src/btx_jev_judge/application/judge.py`  -  The judge use case: redact each state, ask the client, collect one row per item
- `src/btx_jev_judge/application/ports.py`  -  Callable Protocol definitions for adapter functions

### Adapters Layer
- `src/btx_jev_judge/adapters/jev/client.py`  -  Pooled, rate-limited, retrying Jev HTTP client; loopback-only base URL override
- `src/btx_jev_judge/adapters/jev/limiter.py`  -  Request spacing shared by every worker thread
- `src/btx_jev_judge/adapters/key/lookup.py`  -  API key from `TYPESAFE_API_KEY` or `~/.credentials/typesafe.key`
- `src/btx_jev_judge/adapters/files/`  -  JSONL items, JSON questions and JSONL result rows on disk
- `src/btx_jev_judge/adapters/config/loader.py`  -  Configuration loading with LRU caching
- `src/btx_jev_judge/adapters/config/judge_settings.py`  -  Typed `[judge]` and `[summary]` sections
- `src/btx_jev_judge/adapters/config/deploy.py`  -  Configuration deployment
- `src/btx_jev_judge/adapters/config/display.py`  -  Configuration display (TOML/JSON output, redaction)
- `src/btx_jev_judge/adapters/config/overrides.py`  -  CLI `--set` override parsing and deep-merge
- `src/btx_jev_judge/adapters/logging/setup.py`  -  lib_log_rich initialization
- `src/btx_jev_judge/adapters/cli/`  -  CLI adapter package:
  - `__init__.py`  -  Public facade
  - `constants.py`  -  Shared constants
  - `safe_console.py`  -  Encode-safe terminal output; use `safe_console.echo` instead of `click.echo`
  - `exit_codes.py`  -  POSIX exit codes (ExitCode IntEnum)
  - `context.py`  -  Click context helpers
  - `config_load.py`  -  Configuration load for the CLI; records a load failure, `require_config` refuses with exit 78
  - `root.py`  -  Root command group
  - `main.py`  -  Entry point
  - `typed_click.py`  -  Strictly typed wrappers for rich-click decorators
  - `commands/judge.py`  -  run, summarize, check-key commands
  - `commands/judge_output.py`  -  JSON envelope, bare JSON and human rendering
  - `commands/info.py`  -  info command
  - `commands/config.py`  -  config, config-deploy, config-generate-examples commands
  - `commands/logging.py`  -  logdemo command

### Adapters Layer (In-Memory / Testing)
- `src/btx_jev_judge/adapters/memory/__init__.py`  -  Public facade + Protocol conformance assertions
- `src/btx_jev_judge/adapters/memory/config.py`  -  In-memory config adapters
- `src/btx_jev_judge/adapters/memory/logging.py`  -  In-memory logging (a quiet lib_log_rich runtime for tests)

### Composition Layer
- `src/btx_jev_judge/composition/__init__.py`  -  Wires adapters to ports (`build_production`, `build_testing`)

### Entry Points
- `src/btx_jev_judge/entry.py`  -  Console-script entry point (`jev-judge`, `btx-jev-judge`)
- `src/btx_jev_judge/__main__.py`  -  Thin shim for `python -m`
- `src/btx_jev_judge/__init__.py`  -  Public API exports
- `src/btx_jev_judge/__init__conf__.py`  -  Package metadata constants

### Configuration Defaults
- `src/btx_jev_judge/adapters/config/defaultconfig.toml`  -  Base defaults and layer documentation
- `src/btx_jev_judge/adapters/config/defaultconfig.d/40-layered-config.toml`  -  lib_layered_config integration docs
- `src/btx_jev_judge/adapters/config/defaultconfig.d/60-judge.toml`  -  `[judge]` and `[summary]` defaults
- `src/btx_jev_judge/adapters/config/defaultconfig.d/90-logging.toml`  -  Logging defaults

### Tests
- `tests/test_application_judge.py`  -  The use case with a fake client
- `tests/test_jev_client.py`  -  The client against a loopback HTTP stub: retries, redaction, base URL
- `tests/test_key.py`  -  Key lookup, keyfile permissions and secrecy
- `tests/test_files.py`  -  Items, questions and rows files
- `tests/test_domain_models.py`, `tests/test_domain_redaction.py`, `tests/test_domain_summary.py`  -  Domain behaviour
- `tests/test_cli_judge.py`  -  run, summarize and check-key through `CliRunner`
- `tests/test_cli_validation.py`  -  Flag and input validation
- `tests/test_cli_exit_codes.py`, `tests/test_cli_main_exit.py`  -  Exit codes and stderr through the real `main()` entry point
- `tests/test_judge_config.py`  -  `[judge]` and `[summary]` sections, unknown keys, ranges
- `tests/test_cli_config_errors.py`  -  Which commands refuse and which still run when the configuration cannot be loaded
- `tests/test_config_overrides.py`  -  `--set` parsing tests
- `tests/test_deploy_mode_safety.py`  -  `--dir-mode`/`--file-mode` literal, range and safety checks
- `tests/test_permission_defaults.py`  -  `config-deploy` hands permissions to lib_layered_config
- `tests/test_safe_console.py`  -  Legacy-codepage output tests, plus the guard forbidding direct `click.echo`
- `tests/test_display.py`  -  Config display formatting tests
- `tests/test_memory_logging.py`  -  Testing-composition logging runtime and the per-test logging reset
- `tests/test_metadata.py`, `tests/test_metadata_sync.py`  -  Package metadata and its sync with `pyproject.toml`
- `tests/test_module_reference_sync.py`  -  The field tables below match the models
- `tests/test_module_entry.py`  -  `python -m` entry tests
- `tests/test_ports.py`  -  Protocol conformance tests

---

## Architecture

### Layer Assignments

| Directory/Module    | Layer       | Responsibility                                             |
|---------------------|-------------|------------------------------------------------------------|
| `domain/`           | Domain      | Pure logic  -  no I/O, logging, or frameworks              |
| `application/`      | Application | The judge use case and Protocol definitions for adapters   |
| `adapters/jev/`     | Adapters    | HTTP client for the Jev API                                |
| `adapters/key/`     | Adapters    | API key lookup                                             |
| `adapters/files/`   | Adapters    | Items, questions and rows on disk                          |
| `adapters/config/`  | Adapters    | Configuration loading, deployment, display, typed sections |
| `adapters/logging/` | Adapters    | lib_log_rich initialization                                |
| `adapters/cli/`     | Adapters    | Click CLI framework integration                            |
| `adapters/memory/`  | Adapters    | In-memory implementations for testing                      |
| `composition/`      | Composition | Wires adapters to ports                                    |

### Import Enforcement

Layer boundaries enforced via `import-linter` contracts in `pyproject.toml`:
- **Domain is pure**: Cannot import from adapters or composition
- **Clean Architecture layers**: Validates dependency direction (composition -> adapters -> application -> domain)

Run `lint-imports` to verify compliance.

---

## Exit Codes

| Code | Meaning                                                                                                   |
|------|-----------------------------------------------------------------------------------------------------------|
| 0    | Yes: every item answered, no flat question, a key is present                                              |
| 1    | No: a row failed, a question looks flat, or `check-key` found no key                                      |
| 2    | Usage, input or IO error, also an out-of-range flag; stderr `jev-judge: <reason>`; click usage errors too |
| 78   | Broken configuration; stderr `Error: <reason>`                                                            |

Under `--json-bare` an input or configuration error still prints `{"error": "<reason>"}` on stdout;
a click usage error (bad option type, unknown option, `--json` with `--json-bare`) prints no JSON.
The `ExitCode` enum in `adapters/cli/exit_codes.py` also names the errno-derived codes (13, 22, 110)
and the signal codes (130, 141, 143) used by the framework.

---

## CLI Commands

### Root Command

**Command:** `jev-judge` (also `btx-jev-judge`)

| Option                         | Description                                 |
|--------------------------------|---------------------------------------------|
| `--version`                    | Show version and exit                       |
| `--traceback / --no-traceback` | Show full Python traceback on errors        |
| `--profile NAME`               | Load configuration from a named profile     |
| `--set SECTION.KEY=VALUE`      | Override configuration setting (repeatable) |
| `--env-file FILE`              | Explicit `.env` for configuration values    |
| `-h, --help`                   | Show help and exit                          |

### run

Judge every item; one row per item is written to `--out`.

| Option                | Description                                         |
|-----------------------|-----------------------------------------------------|
| `--items PATH`        | JSONL of `{"id": ..., "state": {...}}`  -  required |
| `--questions PATH`    | JSON list of questions  -  required                 |
| `--out PATH`          | JSONL rows, written as they arrive  -  required     |
| `--pilot N`           | Judge only the first N items                        |
| `--rate`, `--workers` | Override `judge.rate`, `judge.workers`              |
| `--attempts`          | Override `judge.attempts`                           |
| `--timeout`, `--cap`  | Override `judge.timeout`, `judge.cap`               |
| `--model`             | Override `judge.model`                              |
| `--json`              | `{ok, command, data, skipped}` envelope             |
| `--json-bare`         | Data only, also on failure                          |

**Exit codes:** 0, 1 (some row failed), 2, 78

### summarize

Distribution, uncertain rows and flat questions of a run.

| Option                  | Description                                         |
|-------------------------|-----------------------------------------------------|
| `--rows PATH`           | JSONL rows written by `run`  -  required            |
| `--band LOW HIGH`       | Override `summary.band_low` and `summary.band_high` |
| `--min-confidence`      | Override `summary.min_confidence`                   |
| `--json`, `--json-bare` | As for `run`                                        |

**Exit codes:** 0, 1 (a question looks flat), 2 (unreadable or malformed rows file, bad flag), 78

### check-key

Reports whether a usable key is configured and where it came from; never prints the key. It does
not read the configuration.

**Exit codes:** 0 (present), 1 (none)

### info

Print resolved package metadata.

**Exit codes:** 0

### config

Display merged configuration from all sources.

| Option                   | Description                    |
|--------------------------|--------------------------------|
| `--format [human\|json]` | Output format (default: human) |
| `--section NAME`         | Show only specific section     |

**Exit codes:** 0, 2 (usage error), 22 (section not found), 78 (configuration not loadable)

### config-deploy

Deploy default configuration to system or user directories.

| Option                             | Description                                                      |
|------------------------------------|------------------------------------------------------------------|
| `--target [app\|host\|user]`       | Target layer(s)  -  required, repeatable                         |
| `--force`                          | Overwrite existing files                                         |
| `--profile NAME`                   | Deploy to profile subdirectory                                   |
| `--permissions / --no-permissions` | Set Unix permissions (default: `enabled` from the configuration) |
| `--dir-mode MODE`                  | Directory mode for every target (octal)                          |
| `--file-mode MODE`                 | File mode for every target (octal)                               |

**Exit codes:** 0, 1, 2 (usage error, including a refused mode or profile name), 13 (permission denied), 78 (lib_layered_config refused the permission settings)

### config-generate-examples

Generate example configuration files.

| Option              | Description                   |
|---------------------|-------------------------------|
| `--destination DIR` | Target directory  -  required |
| `--force`           | Overwrite existing files      |

**Exit codes:** 0, 1

### logdemo

Run logging demonstration.

| Option         | Description                      |
|----------------|----------------------------------|
| `--theme NAME` | Logging theme (default: classic) |

**Exit codes:** 0

---

## Profile Validation

Profile names (`--profile` option) are validated using `lib_layered_config.validate_profile_name()`.

### validate_profile()

**Location:** `adapters/config/loader.py`

```python
def validate_profile(profile: str, max_length: int | None = None) -> None:
    """Validate profile name using lib_layered_config."""
```

| Parameter    | Type          | Default  | Description                                 |
|--------------|---------------|----------|---------------------------------------------|
| `profile`    | `str`         | required | Profile name to validate                    |
| `max_length` | `int \| None` | 64       | Maximum length (DEFAULT_MAX_PROFILE_LENGTH) |

### Validation Rules

| Rule             | Description                                          |
|------------------|------------------------------------------------------|
| Maximum length   | 64 characters (configurable via `max_length`)        |
| Character set    | ASCII alphanumeric, hyphens (`-`), underscores (`_`) |
| Start character  | Must start with alphanumeric character               |
| Empty string     | Rejected                                             |
| Windows reserved | CON, PRN, AUX, NUL, COM1-9, LPT1-9 rejected          |
| Path traversal   | `/`, `\`, `..` rejected                              |
| Control chars    | Rejected                                             |

Raises `ValueError` with a descriptive message on invalid input.

---

## Judge Configuration

`adapters/config/judge_settings.py` reads the `[judge]` and `[summary]` sections into two frozen
Pydantic models that reject unknown keys (which keeps the API key out of configuration: a
`judge.api_key` entry is refused with exit 78). A CLI flag wins over every configuration layer.
`tests/test_module_reference_sync.py` keeps the two tables below in step with the models.

### RunConfig

| Field      | Type    | Default        | Constraint  |
|------------|---------|----------------|-------------|
| `rate`     | `float` | `20.0`         | `> 0`       |
| `workers`  | `int`   | `8`            | `>= 1`      |
| `attempts` | `int`   | `4`            | `1` to `10` |
| `timeout`  | `float` | `30.0`         | `> 0`       |
| `cap`      | `int`   | `60000`        | `>= 100`    |
| `model`    | `str`   | `'jev-latest'` | non-empty   |

### SummaryConfig

| Field            | Type    | Default | Constraint                    |
|------------------|---------|---------|-------------------------------|
| `band_low`       | `float` | `0.2`   | `0` to `1`, below `band_high` |
| `band_high`      | `float` | `0.8`   | `0` to `1`                    |
| `min_confidence` | `float` | `0.6`   | `0` to `1`                    |

---

## Testing Infrastructure

### In-Memory Adapters

The `adapters/memory/` package provides lightweight implementations for testing:

| Module              | Protocols Satisfied                                                         |
|---------------------|-----------------------------------------------------------------------------|
| `memory/config.py`  | `GetConfig`, `GetDefaultConfigPath`, `DeployConfiguration`, `DisplayConfig` |
| `memory/logging.py` | `InitLogging`                                                               |

Use `composition.build_testing()` to wire them. The key lookup and the Jev client stay real,
bound to the `env` and `home` the test passes, so a test reaches a loopback stub of Jev and never
the developer's own key.

### Test Fixtures (conftest.py)

| Fixture                   | Purpose                                                                                                               |
|---------------------------|-----------------------------------------------------------------------------------------------------------------------|
| `config_factory`          | Creates real `Config` instances from test data                                                                        |
| `inject_config`           | Injects config into CLI path                                                                                          |
| `cli_runner`              | Fresh `CliRunner` per test                                                                                            |
| `strip_ansi`              | Strips ANSI escape codes from output                                                                                  |
| `clear_config_cache`      | Clears LRU cache before tests                                                                                         |
| `managed_traceback_state` | Resets/restores traceback configuration                                                                               |
| `isolated_logging_state`  | Autouse: after every test, shuts the lib_log_rich runtime down and restores the root logger; yields that restore step |
