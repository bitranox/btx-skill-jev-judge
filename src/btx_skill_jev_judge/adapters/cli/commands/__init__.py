"""CLI command implementations.

Collects all subcommand functions and re-exports them for registration
with the root CLI group.

Contents:
    * Info commands from :mod:`.info`
    * Config commands from :mod:`.config`
    * Judge commands from :mod:`.judge`
    * Logging commands from :mod:`.logging`
"""

from __future__ import annotations

from .config import cli_config, cli_config_deploy, cli_config_generate_examples
from .info import cli_info
from .judge import cli_check_key, cli_run, cli_summarize
from .logging import cli_logdemo

__all__ = [
    "cli_check_key",
    "cli_config",
    "cli_config_deploy",
    "cli_config_generate_examples",
    "cli_info",
    "cli_logdemo",
    "cli_run",
    "cli_summarize",
]
