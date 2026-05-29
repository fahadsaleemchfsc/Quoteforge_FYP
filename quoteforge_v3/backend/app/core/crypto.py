"""Symmetric encryption for Salesforce OAuth tokens at rest.

A Fernet key (URL-safe base64-encoded 32 bytes) is loaded from
TOKEN_ENCRYPTION_KEY. If the env var is empty — only acceptable in local
dev — we generate an ephemeral key for the process and log a loud warning;
tokens encrypted under that key cannot be read after a restart, which is
the intended pain so nobody ships a deploy without setting the var.

Usage:
    from app.core.crypto import encrypt_str, decrypt_str
    cipher = encrypt_str("00DXX...!AQ...refresh_token...")
    plain  = decrypt_str(cipher)
"""

from __future__ import annotations

import logging
import os

from cryptography.fernet import Fernet, InvalidToken

from app.core.config import settings

_logger = logging.getLogger(__name__)
_fernet: Fernet | None = None


def _load_fernet() -> Fernet:
    global _fernet
    if _fernet is not None:
        return _fernet

    key = settings.TOKEN_ENCRYPTION_KEY.strip() or os.environ.get(
        "TOKEN_ENCRYPTION_KEY", ""
    ).strip()

    if not key:
        # Dev fallback — generate once per process. Restarting invalidates
        # every previously stored token, which is exactly the right signal
        # that you forgot to set TOKEN_ENCRYPTION_KEY before deploying.
        generated = Fernet.generate_key()
        _logger.warning(
            "TOKEN_ENCRYPTION_KEY unset — using ephemeral Fernet key %s. "
            "Persisted Salesforce OAuth tokens WILL be unreadable after "
            "restart. Set TOKEN_ENCRYPTION_KEY in env for any real deploy.",
            generated.decode(),
        )
        _fernet = Fernet(generated)
        return _fernet

    try:
        _fernet = Fernet(key.encode() if isinstance(key, str) else key)
    except (ValueError, TypeError) as exc:
        raise RuntimeError(
            "TOKEN_ENCRYPTION_KEY is not a valid Fernet key. Generate one "
            "with: python -c \"from cryptography.fernet import Fernet; "
            "print(Fernet.generate_key().decode())\""
        ) from exc
    return _fernet


def encrypt_str(plaintext: str) -> str:
    """Encrypt plaintext → opaque base64 token string."""
    if plaintext is None:
        return ""
    return _load_fernet().encrypt(plaintext.encode("utf-8")).decode("utf-8")


def decrypt_str(token: str) -> str:
    """Inverse of encrypt_str. Raises InvalidToken if the ciphertext was
    written under a different key (e.g. dev ephemeral key lost on restart)."""
    if not token:
        return ""
    try:
        return _load_fernet().decrypt(token.encode("utf-8")).decode("utf-8")
    except InvalidToken:
        raise
