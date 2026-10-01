"""Composition root wiring adapters to application ports."""

from __future__ import annotations

import os
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from ..adapters.config.deploy import deploy_configuration
from ..adapters.config.display import display_config

# Configuration services
from ..adapters.config.loader import get_config, get_default_config_path
from ..adapters.jev import JevClient, JevSettings, RateLimiter, resolve_base_url

# Key lookup
from ..adapters.key import load_key

# Logging services
from ..adapters.logging.setup import init_logging

# Static conformance assertions - pyright verifies that each adapter function
# structurally satisfies its corresponding Protocol at type-check time.
if TYPE_CHECKING:
    from collections.abc import Callable, Mapping
    from contextlib import AbstractContextManager

    from ..adapters.config.judge_settings import RunConfig
    from ..application.ports import (
        DeployConfiguration,
        DisplayConfig,
        GetConfig,
        GetDefaultConfigPath,
        InitLogging,
        JudgeClient,
        KeySource,
    )

    #: Builds the judge for one run: ``(key, run settings)``. The client is a context manager so
    #: the command closes its connection pool however the run ends.
    MakeClient = Callable[[str, RunConfig], AbstractContextManager[JudgeClient]]

    _assert_get_config: GetConfig = get_config
    _assert_get_default_config_path: GetDefaultConfigPath = get_default_config_path
    _assert_deploy_configuration: DeployConfiguration = deploy_configuration
    _assert_display_config: DisplayConfig = display_config
    _assert_init_logging: InitLogging = init_logging


@dataclass(frozen=True, slots=True)
class AppServices:
    """Frozen container holding all application port implementations."""

    get_config: GetConfig
    get_default_config_path: GetDefaultConfigPath
    deploy_configuration: DeployConfiguration
    display_config: DisplayConfig
    init_logging: InitLogging
    load_key: KeySource
    make_client: MakeClient
    env: Mapping[str, str]


def _key_source(env: Mapping[str, str], home: Path) -> KeySource:
    """Bind the environment and home directory to the key lookup, which the port takes bare."""

    def _lookup() -> tuple[str | None, str]:
        return load_key(env, home)

    return _lookup


def _client_factory(env: Mapping[str, str], sleep: Callable[[float], object]) -> MakeClient:
    """Build the factory that turns a key and the run settings into a Jev client.

    Args:
        env: The environment; its ``JEV_JUDGE_BASE_URL`` may redirect the client to a loopback host.
        sleep: The wait used between retries and by the rate limiter.

    Returns:
        A factory returning an unopened :class:`JevClient`, itself a context manager.
    """

    def _make(key: str, settings: RunConfig) -> JevClient:
        return JevClient(
            key=key,
            base_url=resolve_base_url(env),
            settings=JevSettings(
                model=settings.model,
                timeout=settings.timeout,
                attempts=settings.attempts,
                workers=settings.workers,
            ),
            limiter=RateLimiter(settings.rate, sleep=sleep),
            sleep=sleep,
        )

    return _make


def build_production() -> AppServices:
    """Wire production adapters into an AppServices container."""
    return AppServices(
        get_config=get_config,
        get_default_config_path=get_default_config_path,
        deploy_configuration=deploy_configuration,
        display_config=display_config,
        init_logging=init_logging,
        load_key=_key_source(os.environ, Path.home()),
        make_client=_client_factory(os.environ, time.sleep),
        env=os.environ,
    )


def _nonexistent_home() -> Path:
    """A home directory that does not exist and whose name nobody could have planted.

    The directory is created only to draw a unique name from the OS, then removed.

    Returns:
        A path that no keyfile lookup can find anything under.
    """
    unique = Path(tempfile.mkdtemp(prefix="btx-jev-judge-no-home-"))
    unique.rmdir()
    return unique


def build_testing(
    *,
    env: Mapping[str, str] | None = None,
    home: Path | None = None,
    sleep: Callable[[float], object] = time.sleep,
) -> AppServices:
    """Wire in-memory adapters into an AppServices container.

    The key lookup and the Jev client are the real adapters, pointed at what the caller supplies:
    an ``env`` carrying ``JEV_JUDGE_BASE_URL`` reaches a loopback stand-in for Jev, and ``home``
    holds (or lacks) the keyfile. Nothing is read from the real environment or home directory.

    Args:
        env: The environment the key lookup and the client see; empty when omitted.
        home: The home directory the keyfile is looked up in; a path that does not exist when omitted.
        sleep: The wait used between retries and by the rate limiter.

    Returns:
        AppServices container with in-memory adapters.
    """
    from ..adapters.memory import (  # noqa: PLC0415 - deferred: keeps in-memory test doubles out of the production import path
        deploy_configuration_in_memory,
        display_config_in_memory,
        get_config_in_memory,
        get_default_config_path_in_memory,
        init_logging_in_memory,
    )

    environment: Mapping[str, str] = {} if env is None else env
    home_dir = _nonexistent_home() if home is None else home
    return AppServices(
        get_config=get_config_in_memory,
        get_default_config_path=get_default_config_path_in_memory,
        deploy_configuration=deploy_configuration_in_memory,
        display_config=display_config_in_memory,
        init_logging=init_logging_in_memory,
        load_key=_key_source(environment, home_dir),
        make_client=_client_factory(environment, sleep),
        env=environment,
    )


__all__ = [
    # Composition
    "AppServices",
    "build_production",
    "build_testing",
    "deploy_configuration",
    "display_config",
    # Configuration
    "get_config",
    "get_default_config_path",
    # Logging
    "init_logging",
]
