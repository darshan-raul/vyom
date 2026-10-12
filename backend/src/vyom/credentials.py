"""Credential references: configuration names where a secret lives, never the secret.

A reference is ``file:/absolute/path`` or ``env:NAME``. It is resolved each time the
credential is needed, so a rotated value is picked up without a restart.
"""

import os
import re
from pathlib import Path

_CREDENTIAL_REF = re.compile(r"^(file:/[^\0]+|env:[A-Z][A-Z0-9_]*)$")


class CredentialUnavailable(Exception):
    """The referenced credential could not be read. Carries no path or value."""


def check_reference(ref: str) -> str:
    """Pydantic field check. The input is not echoed: a pasted secret must not reach an error."""
    if not _CREDENTIAL_REF.fullmatch(ref):
        raise ValueError("credential_ref must be 'file:/absolute/path' or 'env:NAME'")
    return ref


def read_credential(ref: str) -> str:
    scheme, _, target = ref.partition(":")
    try:
        value = Path(target).read_text() if scheme == "file" else os.environ[target]
    except (OSError, KeyError):
        raise CredentialUnavailable() from None
    value = value.strip()
    if not value or any(character.isspace() for character in value):
        raise CredentialUnavailable()
    return value
