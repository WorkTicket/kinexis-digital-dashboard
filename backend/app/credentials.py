import json
import logging
from cryptography.fernet import Fernet, InvalidToken
from app.config import FERNET_KEY

_fernet = Fernet(FERNET_KEY.encode())
logger = logging.getLogger(__name__)

# Prefix so we can detect encrypted AppSetting values vs legacy plaintext.
_SECRET_PREFIX = "fernet:"


class CredentialsDecryptError(Exception):
    """Raised when Fernet decrypt fails — caller must mark reauth_required, not treat as empty."""

    pass


def encrypt_credentials(data: dict) -> str:
    return _fernet.encrypt(json.dumps(data).encode()).decode()


def decrypt_credentials(encrypted: str) -> dict:
    if not encrypted:
        return {}
    try:
        return json.loads(_fernet.decrypt(encrypted.encode()).decode())
    except (InvalidToken, ValueError, json.JSONDecodeError) as e:
        logger.warning("Failed to decrypt credentials: %s", e)
        raise CredentialsDecryptError(
            "Credentials could not be decrypted — reconnect this account"
        ) from e


def encrypt_secret(value: str) -> str:
    """Encrypt a single secret string for AppSetting storage."""
    if value is None:
        return ""
    raw = str(value)
    if not raw:
        return ""
    if raw.startswith(_SECRET_PREFIX):
        return raw
    token = _fernet.encrypt(raw.encode("utf-8")).decode()
    return f"{_SECRET_PREFIX}{token}"


def decrypt_secret(stored: str) -> str:
    """Decrypt AppSetting secret; passthrough legacy plaintext."""
    if not stored:
        return ""
    if not stored.startswith(_SECRET_PREFIX):
        return stored
    token = stored[len(_SECRET_PREFIX) :]
    try:
        return _fernet.decrypt(token.encode()).decode("utf-8")
    except (InvalidToken, ValueError) as e:
        logger.warning("Failed to decrypt secret: %s", e)
        raise CredentialsDecryptError("Secret could not be decrypted") from e


def mask_secret(value: str) -> str:
    """UI-safe mask; empty if unset."""
    if not value:
        return ""
    if len(value) <= 4:
        return "••••"
    return f"••••{value[-4:]}"


def is_masked_placeholder(value: str) -> bool:
    """True when a PUT body is echoing a masked GET value (do not overwrite)."""
    if value is None:
        return True
    s = str(value).strip()
    if not s:
        return False
    if s.startswith("••••") or s.startswith("****"):
        return True
    return False
