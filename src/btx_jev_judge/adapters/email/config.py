"""Email configuration model and loader.

Provides the EmailConfig Pydantic model for validated, immutable email settings
and the loader function to create it from configuration dictionaries.
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any, cast

from btx_lib_mail import validate_email_address, validate_smtp_host
from btx_lib_mail.lib_mail import ConfMail
from pydantic import BaseModel, ConfigDict, Field, SecretStr, ValidationError, field_validator, model_validator


def _credential_text(value: object) -> str | None:
    """Return a user name or password as text, refusing a type that cannot be one.

    The environment layer of lib_layered_config reads an all-digit value as an integer, so
    an all-digit password arrives as an ``int``: it is read back as its digits (a leading
    zero is already gone by then). Any other type is refused, and the message names only the
    type: this runs for the password, whose value must never reach an error message.

    Examples:
        >>> _credential_text(98979695)
        '98979695'
        >>> _credential_text(SecretStr("abc"))
        'abc'
        >>> _credential_text(True)
        Traceback (most recent call last):
        ...
        ValueError: expected a string, got bool
    """
    if value is None or isinstance(value, str):
        return value
    if isinstance(value, SecretStr):
        return value.get_secret_value()
    if isinstance(value, int) and not isinstance(value, bool):
        return str(value)
    # A float is refused rather than printed: str(1.50) is "1.5" and str(1e3) is "1000.0",
    # so the text would silently differ from what was written.
    raise ValueError(f"expected a string, got {type(value).__name__}")


class EmailConfig(BaseModel):
    """Validated, immutable email configuration.

    Example:
        >>> config = EmailConfig(
        ...     smtp_hosts=["smtp.example.com:587"],
        ...     from_address="noreply@example.com"
        ... )
        >>> config.smtp_hosts
        ['smtp.example.com:587']
    """

    # hide_input_in_errors: pydantic otherwise prints the input it refused, the offending
    # value for a field error and the whole input mapping for a model-level one, and that
    # input holds the SMTP password.
    model_config = ConfigDict(frozen=True, hide_input_in_errors=True)

    smtp_hosts: list[str] = Field(default_factory=list)
    from_address: str | None = None
    recipients: list[str] = Field(default_factory=list)
    smtp_username: str | None = None
    # SecretStr so str(), repr(), format() and model_dump_json() show '**********'; the value is
    # unwrapped only where it is handed to the SMTP login (transport._build_credentials).
    smtp_password: SecretStr | None = None
    use_starttls: bool = True
    timeout: float = 30.0
    raise_on_missing_attachments: bool = True
    raise_on_invalid_recipient: bool = True

    # Attachment security settings (None = use btx_lib_mail defaults)
    attachment_allowed_extensions: frozenset[str] | None = None
    attachment_blocked_extensions: frozenset[str] | None = None
    attachment_allowed_directories: frozenset[Path] | None = None
    attachment_blocked_directories: frozenset[Path] | None = None
    attachment_max_size_bytes: int | None = 26_214_400  # 25 MiB
    attachment_allow_symlinks: bool = False
    attachment_raise_on_security_violation: bool = True

    @field_validator("smtp_hosts", "recipients", mode="before")
    @classmethod
    def _coerce_string_to_list(cls, v: Any) -> list[str]:
        """Coerce single strings to single-element lists.

        Handles environment variables and .env files that provide single strings
        instead of TOML arrays. Empty strings become empty lists.

        Examples:
            >>> EmailConfig._coerce_string_to_list("smtp.example.com:587")
            ['smtp.example.com:587']
            >>> EmailConfig._coerce_string_to_list(["a@example.com", "b@example.com"])
            ['a@example.com', 'b@example.com']
            >>> EmailConfig._coerce_string_to_list("")
            []
        """
        if isinstance(v, str):
            return [v] if v.strip() else []
        if isinstance(v, list):
            return cast("list[str]", v)
        return []

    @field_validator("from_address", mode="before")
    @classmethod
    def _coerce_empty_string_to_none(cls, v: object) -> object:
        """Coerce an empty or whitespace-only string to None ("not configured")."""
        if isinstance(v, str) and not v.strip():
            return None
        return v

    @field_validator("smtp_username", "smtp_password", mode="before")
    @classmethod
    def _read_credential(cls, v: object) -> object:
        """Read the SMTP login's user name or password, or None when it is not configured.

        An empty or whitespace-only value means "not configured", so no login is attempted
        with empty credentials. An all-digit value from the environment arrives as an
        integer and is read as its digits (see :func:`_credential_text`). A non-ASCII value
        is refused: smtplib encodes the AUTH exchange as ASCII, so the login could never
        succeed, and its UnicodeEncodeError would carry the attempt into the delivery log.
        No message names the value.

        Examples:
            >>> EmailConfig._read_credential("   ") is None
            True
            >>> EmailConfig._read_credential(1234)
            '1234'
        """
        text = _credential_text(v)
        if text is None or not text.strip():
            return None
        if not text.isascii():
            raise ValueError("must be ASCII: smtplib sends the SMTP login as ASCII, so it could never log in")
        return v if isinstance(v, SecretStr) else text

    @field_validator(
        "attachment_allowed_extensions",
        "attachment_blocked_extensions",
        mode="before",
    )
    @classmethod
    def _coerce_extension_lists(cls, v: Any) -> frozenset[str] | None:
        """Convert lists to frozensets, empty lists to None (use library defaults).

        Frozensets are preserved as-is (including empty ones) to allow explicit
        override from Python code. Empty lists from TOML config become None.
        """
        if v is None:
            return None
        if isinstance(v, frozenset):
            # Preserve frozensets as-is (allows explicit empty frozenset to disable)
            return cast("frozenset[str]", v)
        if isinstance(v, list):
            # Empty list from config = use library defaults
            ext_list = cast("list[str]", v)
            return frozenset(ext_list) if ext_list else None
        return None  # Unsupported type, let Pydantic handle validation error

    @field_validator(
        "attachment_allowed_directories",
        "attachment_blocked_directories",
        mode="before",
    )
    @classmethod
    def _coerce_directory_lists(cls, v: Any) -> frozenset[Path] | None:
        """Convert lists of strings/paths to frozenset[Path], empty lists to None.

        Frozensets are preserved as-is (including empty ones) to allow explicit
        override from Python code. Empty lists from TOML config become None.
        """
        if v is None:
            return None
        if isinstance(v, frozenset):
            # Preserve frozensets as-is (allows explicit empty frozenset to disable)
            return cast("frozenset[Path]", v)
        if isinstance(v, list):
            # Empty list from config = use library defaults
            dir_list = cast("list[str | Path]", v)
            if not dir_list:
                return None
            return frozenset(Path(p) if isinstance(p, str) else p for p in dir_list)
        return None  # Unsupported type, let Pydantic handle validation error

    @field_validator("attachment_max_size_bytes", mode="before")
    @classmethod
    def _coerce_max_size_zero_to_none(cls, v: Any) -> int | None:
        """Convert 0 to None (disable size checking)."""
        if v == 0:
            return None
        return v

    @model_validator(mode="after")
    def _validate_config(self) -> EmailConfig:
        """Validate configuration values.

        Catch common configuration mistakes early with clear error messages
        rather than allowing invalid values to cause obscure failures later.

        Raises:
            ValueError: When configuration values are invalid.

        Example:
            >>> EmailConfig(timeout=-5.0)  # doctest: +IGNORE_EXCEPTION_DETAIL
            Traceback (most recent call last):
            ...
            ValidationError: ...

            >>> EmailConfig(from_address="not-an-email")  # doctest: +IGNORE_EXCEPTION_DETAIL
            Traceback (most recent call last):
            ...
            ValidationError: ...
        """
        if self.timeout <= 0:
            raise ValueError(f"timeout must be positive, got {self.timeout}")

        if self.from_address is not None:
            validate_email_address(self.from_address)

        for recipient in self.recipients:
            validate_email_address(recipient)

        for host in self.smtp_hosts:
            validate_smtp_host(host)

        return self

    def __repr__(self) -> str:
        """Return string representation with smtp_password redacted.

        Prevents accidental credential exposure in logs, error messages,
        and debugging output. The password is shown as '[REDACTED]' when set.

        Example:
            >>> config = EmailConfig(
            ...     smtp_hosts=["smtp.example.com:587"],
            ...     smtp_password="secret123"
            ... )
            >>> "secret123" in repr(config)
            False
            >>> "[REDACTED]" in repr(config)
            True
        """
        fields: list[str] = []
        for name, value in self:
            if name == "smtp_password" and value is not None:
                fields.append(f"{name}='[REDACTED]'")
            else:
                fields.append(f"{name}={value!r}")
        return f"EmailConfig({', '.join(fields)})"

    def to_conf_mail(self) -> ConfMail:
        """Convert to btx_lib_mail ConfMail object.

        Isolates the adapter dependency on btx_lib_mail types from the
        rest of the application.

        Returns:
            ConfMail instance configured with current settings.

        Example:
            >>> config = EmailConfig(smtp_hosts=["smtp.example.com"])
            >>> conf = config.to_conf_mail()
            >>> conf.smtphosts
            ['smtp.example.com']
        """
        # Build kwargs, omitting None values to use library defaults
        kwargs: dict[str, Any] = {
            "smtphosts": self.smtp_hosts,
            "smtp_username": self.smtp_username,
            "smtp_password": self.smtp_password,
            "smtp_use_starttls": self.use_starttls,
            "smtp_timeout": self.timeout,
            "raise_on_missing_attachments": self.raise_on_missing_attachments,
            "raise_on_invalid_recipient": self.raise_on_invalid_recipient,
            "attachment_allow_symlinks": self.attachment_allow_symlinks,
            "attachment_raise_on_security_violation": self.attachment_raise_on_security_violation,
        }

        # Only pass attachment security settings when explicitly configured
        # (None = use btx_lib_mail's OS-specific defaults)
        if self.attachment_allowed_extensions is not None:
            kwargs["attachment_allowed_extensions"] = self.attachment_allowed_extensions
        if self.attachment_blocked_extensions is not None:
            kwargs["attachment_blocked_extensions"] = self.attachment_blocked_extensions
        if self.attachment_allowed_directories is not None:
            kwargs["attachment_allowed_directories"] = self.attachment_allowed_directories
        if self.attachment_blocked_directories is not None:
            kwargs["attachment_blocked_directories"] = self.attachment_blocked_directories
        if self.attachment_max_size_bytes is not None:
            kwargs["attachment_max_size_bytes"] = self.attachment_max_size_bytes

        return ConfMail(**kwargs)


def load_email_config_from_dict(config_dict: Mapping[str, Any]) -> EmailConfig:
    """Load EmailConfig from a configuration dictionary.

    Bridges lib_layered_config's dictionary output with the typed
    EmailConfig Pydantic model. Single-parse validation at the boundary
    with no intermediate conversions.

    Handles the nested `[email.attachments]` TOML section by flattening
    it with an `attachment_` prefix to match EmailConfig field names.

    Args:
        config_dict: Configuration dictionary typically from lib_layered_config.
            Expected to have an 'email' section with email settings.

    Returns:
        Configured email settings with defaults for missing values.

    Example:
        >>> config_dict = {
        ...     "email": {
        ...         "smtp_hosts": ["smtp.example.com:587"],
        ...         "from_address": "test@example.com"
        ...     }
        ... }
        >>> email_config = load_email_config_from_dict(config_dict)
        >>> email_config.from_address
        'test@example.com'
        >>> email_config.use_starttls
        True

        >>> config_dict_with_attachments = {
        ...     "email": {
        ...         "smtp_hosts": ["smtp.example.com:587"],
        ...         "attachments": {
        ...             "max_size_bytes": 10485760,
        ...             "allow_symlinks": True,
        ...         }
        ...     }
        ... }
        >>> config = load_email_config_from_dict(config_dict_with_attachments)
        >>> config.attachment_max_size_bytes
        10485760
        >>> config.attachment_allow_symlinks
        True
    """
    email_section: Any = config_dict.get("email", {})

    # Handle non-dict email section (e.g. "email": "invalid")
    if not isinstance(email_section, Mapping):
        return EmailConfig.model_validate(email_section)

    email_raw: dict[str, Any] = dict(cast("Mapping[str, Any]", email_section))

    # Flatten nested [email.attachments] section with prefix
    attachments_raw: dict[str, Any] = email_raw.pop("attachments", {})
    for key, value in attachments_raw.items():
        email_raw[f"attachment_{key}"] = value

    return EmailConfig.model_validate(email_raw if email_raw else {})


#: The configuration section EmailConfig is read from, and the field prefix that stands for
#: its nested ``[email.attachments]`` table (see :func:`load_email_config_from_dict`).
_SECTION = "email"
_ATTACHMENT_PREFIX = "attachment_"


def _configuration_key(loc: tuple[int | str, ...]) -> str:
    """Spell a validation error's location as the dotted key a user writes in the file.

    Examples:
        >>> _configuration_key(("timeout",))
        'email.timeout'
        >>> _configuration_key(("attachment_max_size_bytes",))
        'email.attachments.max_size_bytes'
        >>> _configuration_key(())
        'email'
    """
    parts = [str(part) for part in loc]
    if parts and parts[0].startswith(_ATTACHMENT_PREFIX):
        parts[0:1] = ["attachments", parts[0].removeprefix(_ATTACHMENT_PREFIX)]
    return ".".join((_SECTION, *parts))


def describe_validation_error(error: ValidationError) -> list[str]:
    """Render an EmailConfig validation error as one ``<key>: <reason>`` line per problem.

    The refused input is never part of a line: it can be the SMTP password.

    Args:
        error: The error ``EmailConfig`` validation raised.

    Returns:
        One line per problem; the key is ``email`` alone for a problem with the whole section.

    Example:
        >>> try:
        ...     EmailConfig(timeout=-5.0)
        ... except ValidationError as exc:
        ...     describe_validation_error(exc)
        ['email: timeout must be positive, got -5.0']
    """
    lines: list[str] = []
    for item in error.errors(include_url=False, include_input=False):
        # pydantic prefixes the message of a ValueError raised by a validator with
        # "Value error, "; the exception it carries holds the message as written.
        raised = item.get("ctx", {}).get("error")
        reason = str(raised) if isinstance(raised, ValueError) else item["msg"]
        lines.append(f"{_configuration_key(item['loc'])}: {reason}".replace("\n", " "))
    return lines


__all__ = [
    "EmailConfig",
    "describe_validation_error",
    "load_email_config_from_dict",
]
