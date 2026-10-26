"""Centralized logging initialization for all entry points.

Provides a single source of truth for lib_log_rich runtime configuration,
eliminating duplication between module entry (__main__.py) and console script
(cli.py) while ensuring initialization happens exactly once.

Contents:
    * :func:`init_logging` - idempotent logging initialization from the ``[lib_log_rich]``
      section and the ``LOG_*`` variables (the environment, plus the ``.env`` it loads).
    * :func:`check_logging_config` - refuse another configuration's logging settings without touching the runtime.
    * :func:`log_variables_hidden` - remove every ``LOG_*`` variable for a block, then put each back.
    * :func:`run_logdemo` - lib_log_rich's demo, refusing a ``LOG_*`` variable as :func:`init_logging` does.
    * :class:`InvalidLoggingConfigError` - the ``[lib_log_rich]`` section or a ``LOG_*`` variable
      cannot configure logging.
    * :func:`_build_runtime_config` - constructs RuntimeConfig from layered sources.
    * :func:`_quiet_http_loggers` - keeps httpx2's one-line-per-request INFO log off the console.

System Role:
    Lives in the adapters/platform layer. All entry points (module execution,
    console scripts, tests) delegate to this module for logging setup, ensuring
    consistent runtime behavior across invocation paths.
"""

from __future__ import annotations

import logging
import os
from contextlib import contextmanager
from typing import TYPE_CHECKING, cast

import lib_log_rich
import lib_log_rich.config
import lib_log_rich.runtime
from lib_layered_config import Config
from pydantic import BaseModel, ConfigDict, ValidationError

from btx_skill_jev_judge import __init__conf__
from btx_skill_jev_judge.domain.errors import ConfigurationError

if TYPE_CHECKING:
    from collections.abc import Generator

    from lib_log_rich.demo import LogDemoResult
    from lib_log_rich.domain import ConsoleTheme


class LoggingConfigModel(BaseModel):
    """Pydantic model for [lib_log_rich] config section validation.

    Used at the boundary to parse configuration dictionaries into typed fields.
    Extra fields are allowed to pass through to lib_log_rich.RuntimeConfig.

    Example:
        >>> model = LoggingConfigModel(service="myapp", environment="staging")
        >>> model.service
        'myapp'
        >>> model.environment
        'staging'

        >>> default = LoggingConfigModel()
        >>> default.environment
        'prod'
    """

    service: str | None = None
    environment: str = "prod"

    # lib_layered_config reads an unquoted all-digit value as an int; the conversion is lossless,
    # so turning it back into text keeps a service or environment name made of digits valid.
    model_config = ConfigDict(extra="allow", coerce_numbers_to_str=True)


def _build_runtime_config(config: Config) -> lib_log_rich.runtime.RuntimeConfig:
    """Build RuntimeConfig from a Config object.

    Centralizes the mapping from lib_layered_config to lib_log_rich
    RuntimeConfig. Uses Pydantic for single-parse validation at the boundary.

    Args:
        config: Already-loaded layered configuration object.

    Returns:
        Fully configured runtime settings ready for lib_log_rich.init().

    Note:
        Configuration is read from the [lib_log_rich] section. All parameters
        documented in defaultconfig.toml can be specified. Unspecified values
        use lib_log_rich's built-in defaults. The service and environment
        parameters default to package metadata when not configured.
    """
    log_raw: object = config.get("lib_log_rich", default={})
    parsed = LoggingConfigModel.model_validate(cast("dict[str, object]", log_raw) if log_raw else {})

    # Apply defaults for required fields
    service = parsed.service or __init__conf__.name
    environment = parsed.environment

    # Get extra fields passed through by Pydantic
    extra_config = parsed.model_dump(exclude={"service", "environment"}, exclude_none=True)

    return lib_log_rich.runtime.RuntimeConfig(
        service=service,
        environment=environment,
        **extra_config,
    )


#: The loggers of the ``httpx2`` dependency, which writes one INFO line per HTTP request. ``run``
#: sends one request per item, and the agent driving the command reads its stderr, so at INFO a
#: large run would put a line per item back into the context the command exists to keep it out of.
#: The names are httpx2's own (``logging.getLogger("httpx2")``), not the classic ``httpx``.
_PER_REQUEST_LOGGERS = ("httpx2", "httpcore2")


def _asks_for_debug(console_level: object) -> bool:
    """Whether a ``console_level``, given as a name or a lib_log_rich level, is DEBUG or lower.

    Args:
        console_level: ``"DEBUG"``-style name, a stdlib number, or a ``LogLevel`` member.

    Returns:
        True for DEBUG and anything more verbose.

    Example:
        >>> _asks_for_debug("debug"), _asks_for_debug("INFO"), _asks_for_debug(10)
        (True, False, True)
    """
    value: object = getattr(console_level, "value", console_level)
    if isinstance(value, int):
        return value <= logging.DEBUG
    return str(value).strip().upper() == "DEBUG"


def _quiet_http_loggers(console_level: object) -> None:
    """Raise the per-request HTTP loggers to WARNING unless the console asks for DEBUG.

    At DEBUG the request lines are what someone diagnosing the connection wants, so they stay.

    Args:
        console_level: The configured console level, as lib_log_rich holds it.
    """
    if _asks_for_debug(console_level):
        return
    for name in _PER_REQUEST_LOGGERS:
        logging.getLogger(name).setLevel(logging.WARNING)


class InvalidLoggingConfigError(ConfigurationError):
    """lib_log_rich refuses its settings: one ``<key>: <reason>`` in :attr:`problems` per problem.

    The settings are the ``[lib_log_rich]`` section plus any ``LOG_*`` variable. A problem the
    type check of the section finds names the key and never repeats the refused value; one no
    single key owns (TLS over UDP for Graylog) reads ``lib_log_rich: <reason>``. A value only
    lib_log_rich itself refuses, such as an unknown level in ``LOG_CONSOLE_LEVEL`` or in the
    section's ``console_level``, is reported in lib_log_rich's own words, which name the setting
    and repeat the value (``lib_log_rich: Invalid runtime settings: LOG_CONSOLE_LEVEL: Unknown log
    level: 'bogus'``).

    Attributes:
        problems: One line per refused setting.

    Example:
        >>> try:
        ...     _build_runtime_config(Config({"lib_log_rich": {"rate_limit": "100:60"}}, {}))
        ... except ValidationError as exc:
        ...     print(InvalidLoggingConfigError(_problems(exc)))
        lib_log_rich.rate_limit: Input should be a valid tuple
    """

    def __init__(self, problems: list[str]) -> None:
        super().__init__("; ".join(problems))
        self.problems = problems


#: The variables lib_log_rich reads itself, on every start.
_LOG_VARIABLE_PREFIX = "LOG_"


def _problems(error: BaseException) -> list[str]:
    """One line per problem: key and reason from the first pydantic error in ``error``'s chain.

    A pydantic problem never repeats the refused value; one no single key owns (a model-wide
    check) has no key and reads ``lib_log_rich: <reason>``. Without a pydantic error in the chain,
    the line is lib_log_rich's own first line, which may repeat the value
    (``Invalid runtime settings: console_level: Unknown log level: 'bogus'``).
    """
    cause: BaseException | None = error
    while cause is not None and not isinstance(cause, ValidationError):
        cause = cause.__cause__ or cause.__context__
    if cause is None:
        # Not a pydantic error (e.g. an unknown level name in a LOG_* variable): lib_log_rich's
        # own first line.
        return [f"lib_log_rich: {str(error).splitlines()[0]}"]
    return [f"{_problem_key(item['loc'])}: {item['msg']}" for item in cause.errors()]


def _problem_key(loc: tuple[int | str, ...]) -> str:
    """``lib_log_rich.<key>`` for a problem located at a key, bare ``lib_log_rich`` for a model-wide one.

    Example:
        >>> _problem_key(("rate_limit",))
        'lib_log_rich.rate_limit'
        >>> _problem_key(())
        'lib_log_rich'
    """
    return ".".join(["lib_log_rich", *(str(part) for part in loc)])


@contextmanager
def log_variables_hidden() -> Generator[None]:
    """Remove every ``LOG_*`` variable from the environment for the block, then put each back.

    Example:
        >>> os.environ["LOG_HIDDEN_PROBE"] = "x"
        >>> with log_variables_hidden():
        ...     "LOG_HIDDEN_PROBE" in os.environ
        False
        >>> os.environ.pop("LOG_HIDDEN_PROBE")
        'x'
    """
    names = [name for name in os.environ if name.startswith(_LOG_VARIABLE_PREFIX)]
    hidden = {name: os.environ.pop(name) for name in names}
    try:
        yield
    finally:
        os.environ.update(hidden)


def _start_default_logging() -> lib_log_rich.runtime.RuntimeConfig:
    """Start lib_log_rich with the package defaults; without the ``LOG_*`` variables only if needed.

    lib_log_rich reads the ``LOG_*`` variables from the environment on every init. When the
    refused setting came from the ``[lib_log_rich]`` section, the defaults start with them and
    a valid ``LOG_CONSOLE_LEVEL`` still applies. When one of them is the refused setting, that
    start is refused again, and only then do the defaults start with every ``LOG_*`` hidden.

    Returns:
        The settings logging was started with.
    """
    defaults = _build_runtime_config(Config({}, {}))
    try:
        lib_log_rich.runtime.init(defaults)
    except ValueError:  # pydantic's ValidationError is a ValueError
        with log_variables_hidden():
            lib_log_rich.runtime.init(defaults)
    return defaults


def init_logging(config: Config) -> None:
    """Initialize lib_log_rich runtime with the provided configuration.

    All entry points need logging configured, but the runtime should only
    be initialized once regardless of how many times this function is called.
    Loads .env files (to make LOG_* variables available), checks if lib_log_rich
    is already initialized, and configures it with settings from the provided
    Config object. Bridges standard Python logging to lib_log_rich for domain
    code compatibility.

    Args:
        config: Already-loaded layered configuration object containing logging
            settings in the [lib_log_rich] section.

    Raises:
        InvalidLoggingConfigError: The ``[lib_log_rich]`` section or a ``LOG_*`` variable holds
            a value lib_log_rich refuses. Logging is started anyway, with the package defaults
            and the ``LOG_*`` variables (every one of them ignored if the defaults are refused
            with them too), so the caller can record the failure and run the commands that do
            not read the configuration. Only the first call can raise: logging is running after
            it, so a later call returns at once, also with the same refused configuration.

    Side Effects:
        Loads .env files into the process environment on first invocation.
        May initialize the global lib_log_rich runtime on first invocation.
        Subsequent calls have no effect.

    Note:
        This function is safe to call multiple times. The first call loads .env
        and initializes the runtime; subsequent calls check the initialization
        state and return immediately if already initialized.

        The .env loading enables lib_log_rich to read LOG_* environment variables
        from .env files in the current directory or parent directories. This
        provides the highest precedence override mechanism for logging configuration.

    Example:
        >>> from lib_layered_config import Config
        >>> config = Config({"lib_log_rich": {"environment": "test"}}, {})
        >>> init_logging(config)  # doctest: +SKIP
    """
    if lib_log_rich.runtime.is_initialised():
        return
    lib_log_rich.config.enable_dotenv()
    try:
        runtime_config = _build_runtime_config(config)
        lib_log_rich.runtime.init(runtime_config)
    except ValueError as exc:  # pydantic's ValidationError is a ValueError
        # The type check of the section and lib_log_rich's own range checks (which also see the
        # LOG_* variables) both refuse here; neither has started the runtime.
        defaults = _start_default_logging()
        lib_log_rich.runtime.attach_std_logging()
        _quiet_http_loggers(defaults.console_level)
        raise InvalidLoggingConfigError(_problems(exc)) from exc
    lib_log_rich.runtime.attach_std_logging()
    _quiet_http_loggers(runtime_config.console_level)


def check_logging_config(config: Config) -> None:
    """Refuse ``config``'s logging settings as :func:`init_logging` would, without touching the runtime.

    :func:`init_logging` returns at once while a runtime is running, so a configuration loaded
    after logging started (``config --profile``'s reload) would never have its logging settings
    judged. lib_log_rich's ``validate_config`` refuses exactly what its ``init`` refuses, with the
    same message and the same ``LOG_*`` overrides, and neither reads nor replaces the running
    runtime, so logging keeps running with the settings it started with, on every thread.

    Args:
        config: Already-loaded layered configuration object.

    Raises:
        InvalidLoggingConfigError: As for :func:`init_logging`, with the same problem lines.

    Example:
        >>> check_logging_config(Config({"lib_log_rich": {"console_level": "info"}}, {}))
        >>> try:
        ...     check_logging_config(Config({"lib_log_rich": {"rate_limit": "100:60"}}, {}))
        ... except InvalidLoggingConfigError as exc:
        ...     print(exc)
        lib_log_rich.rate_limit: Input should be a valid tuple
    """
    try:
        lib_log_rich.runtime.validate_config(_build_runtime_config(config))
    except ValueError as exc:  # pydantic's ValidationError is a ValueError
        raise InvalidLoggingConfigError(_problems(exc)) from exc


def run_logdemo(theme: ConsoleTheme) -> LogDemoResult:
    """Run lib_log_rich's demo; a ``LOG_*`` variable it refuses is refused as :func:`init_logging` refuses it.

    The demo needs the runtime stopped, so a running one is shut down first. It builds its own
    runtime and reads the ``LOG_*`` variables itself, so an invalid one surfaces here as
    lib_log_rich's ``ValueError``, which would otherwise reach ``main()``'s catch-all and exit
    with the OS errno (22 on POSIX, 87 on Windows).

    Args:
        theme: The console theme to preview.

    Returns:
        lib_log_rich's report of the demo run.

    Raises:
        InvalidLoggingConfigError: A ``LOG_*`` variable lib_log_rich refuses, in the same line
            :func:`init_logging` writes for it.
    """
    if lib_log_rich.runtime.is_initialised():
        lib_log_rich.runtime.shutdown()
    try:
        return lib_log_rich.logdemo(theme=theme)
    except ValueError as exc:  # pydantic's ValidationError is a ValueError
        raise InvalidLoggingConfigError(_problems(exc)) from exc


__all__ = [
    "InvalidLoggingConfigError",
    "LoggingConfigModel",
    "check_logging_config",
    "init_logging",
    "log_variables_hidden",
    "run_logdemo",
]
