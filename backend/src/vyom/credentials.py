"""Credential references: configuration names where a secret lives, never the secret.

A reference is ``file:/absolute/path`` or ``env:NAME``. It is resolved each time the
credential is needed, so a rotated value is picked up without a restart.
"""

import os  # os.environ holds the process's environment variables
import re  # regular expressions (pattern matching on text)
from pathlib import Path  # object-style file paths

# Pattern for a valid reference: either ``file:/...`` or ``env:NAME`` (NAME in CAPITAL_SNAKE).
_CREDENTIAL_REF = re.compile(r"^(file:/[^\0]+|env:[A-Z][A-Z0-9_]*)$")


# A custom exception type. Making your own lets callers catch exactly this failure.
class CredentialUnavailable(Exception):
    """The referenced credential could not be read. Carries no path or value."""


def check_reference(ref: str) -> str:
    """Pydantic field check. The input is not echoed: a pasted secret must not reach an error."""
    # fullmatch: the whole string must fit the pattern, not just a part of it.
    if not _CREDENTIAL_REF.fullmatch(ref):
        # The message deliberately does not include ``ref``, which might be a real secret.
        raise ValueError("credential_ref must be 'file:/absolute/path' or 'env:NAME'")
    return ref


def read_credential(ref: str) -> str:
    # partition splits at the first ":" into (before, separator, after). "file:/a/b" gives
    # scheme="file", target="/a/b". ``_`` is the usual name for a value we don't need.
    scheme, _, target = ref.partition(":")
    try:
        # Read from a file or from an environment variable depending on the scheme.
        value = Path(target).read_text() if scheme == "file" else os.environ[target]
    except (OSError, KeyError):  # file missing/unreadable, or env variable not set
        # ``from None`` hides the original error, whose text could contain a path.
        raise CredentialUnavailable() from None
    value = value.strip()  # drop surrounding whitespace such as a trailing newline
    # Reject an empty value or one with spaces/newlines inside; real tokens have none.
    if not value or any(character.isspace() for character in value):
        raise CredentialUnavailable()
    return value
