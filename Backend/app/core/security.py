import hashlib
import hmac
import secrets
import base64
from datetime import datetime, timezone
from app.core.config import settings


def hash_token(token: str) -> str:
    """Returns SHA-256 hash of token for secure indexed storage."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def generate_secure_opaque_token(prefix: str = "SOS") -> str:
    """Generates an unguessable opaque random token for physical QR labels."""
    random_bytes = secrets.token_bytes(24)
    token_str = base64.urlsafe_b64encode(random_bytes).decode("utf-8").rstrip("=")
    return f"{prefix}_{token_str}"


def sign_qr_payload(token: str) -> str:
    """Generates an HMAC-SHA256 signature for client tamper detection."""
    mac = hmac.new(
        settings.QR_HMAC_SECRET.encode("utf-8"),
        token.encode("utf-8"),
        hashlib.sha256
    )
    return mac.hexdigest()[:16]


def verify_qr_signature(token: str, signature: str) -> bool:
    """Verifies that the HMAC signature matches the token."""
    expected = sign_qr_payload(token)
    return hmac.compare_digest(expected, signature)

