"""Type-safe domain enums for output formats, deployment targets and question types."""

from __future__ import annotations

from enum import Enum


class OutputFormat(str, Enum):
    """Output format options for configuration display.

    Defines valid output format choices for the config command.
    Inherits from str to allow direct string comparison and Click integration.

    Attributes:
        HUMAN: Human-readable TOML-like output format.
        JSON: Machine-readable JSON output format.

    Example:
        >>> OutputFormat.HUMAN.value
        'human'
        >>> OutputFormat.JSON == "json"
        True
    """

    HUMAN = "human"
    JSON = "json"


class DeployTarget(str, Enum):
    """Configuration deployment target layers.

    Defines valid target layers for configuration file deployment.
    Inherits from str to allow direct string comparison and Click integration.

    Attributes:
        APP: System-wide application configuration (requires privileges).
        HOST: System-wide host-specific configuration (requires privileges).
        USER: User-specific configuration (~/.config on Linux).

    Example:
        >>> DeployTarget.USER.value
        'user'
        >>> DeployTarget.APP == "app"
        True
    """

    APP = "app"
    HOST = "host"
    USER = "user"


class QuestionType(str, Enum):
    """The three Jev primitives.

    Attributes:
        NOUL: A yes/no question; the answer is the probability of yes.
        CHOICE: Pick one of several named options.
        SCORE: A position on a few ordered levels.

    Example:
        >>> QuestionType("noul") is QuestionType.NOUL
        True
    """

    NOUL = "noul"
    CHOICE = "choice"
    SCORE = "score"


__all__ = [
    "DeployTarget",
    "OutputFormat",
    "QuestionType",
]
