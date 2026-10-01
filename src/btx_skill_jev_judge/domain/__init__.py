"""Domain layer - pure business logic with no I/O or framework dependencies.

Contains entities, value objects, and domain services that form the core
business logic of the application.

Contents:
    * :mod:`.enums` - Domain enumerations (OutputFormat, DeployTarget, QuestionType)
    * :mod:`.errors` - Domain exception types
    * :mod:`.models` - Questions, items, answers, rows and outcomes
    * :mod:`.redaction` - Secret redaction and string capping for item states
    * :mod:`.summary` - Per-question summary of a run
"""

from __future__ import annotations

from .enums import DeployTarget, OutputFormat, QuestionType
from .errors import ConfigurationError, InputError
from .models import (
    QUESTIONS_ADAPTER,
    Answer,
    ChoiceQuestion,
    Item,
    NoulCriteria,
    NoulQuestion,
    Outcome,
    Question,
    Row,
    ScoreQuestion,
    describe_validation_error,
    parse_questions,
)
from .redaction import DEFAULT_CAP, REDACTED, cap_text, prepare_state, redact
from .summary import (
    DEFAULT_BAND,
    DEFAULT_MIN_CONFIDENCE,
    FLAT_MIN_ROWS,
    FLAT_STDEV,
    PRICE_PER_MTOK,
    summarize,
)

__all__ = [
    "DEFAULT_BAND",
    "DEFAULT_CAP",
    "DEFAULT_MIN_CONFIDENCE",
    "FLAT_MIN_ROWS",
    "FLAT_STDEV",
    "PRICE_PER_MTOK",
    "QUESTIONS_ADAPTER",
    "REDACTED",
    "Answer",
    "ChoiceQuestion",
    "ConfigurationError",
    "DeployTarget",
    "InputError",
    "Item",
    "NoulCriteria",
    "NoulQuestion",
    "Outcome",
    "OutputFormat",
    "Question",
    "QuestionType",
    "Row",
    "ScoreQuestion",
    "cap_text",
    "describe_validation_error",
    "parse_questions",
    "prepare_state",
    "redact",
    "summarize",
]
