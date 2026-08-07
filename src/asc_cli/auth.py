"""JWT authentication for the App Store Connect API."""

from __future__ import annotations

import os
import time
from pathlib import Path

DEFAULT_PRIVATE_KEY = (
    Path.home() / ".config" / "app-store-connect-cli" / "AuthKey_PRIVATE_KEY_ID.p8"
)


class AuthError(RuntimeError):
    """Raised when App Store Connect credentials are incomplete."""


def private_key_path(value: str | None = None) -> Path:
    configured = value or os.environ.get("ASC_PRIVATE_KEY")
    return Path(configured).expanduser() if configured else DEFAULT_PRIVATE_KEY


def required_value(value: str | None, env_name: str, label: str) -> str:
    resolved = value or os.environ.get(env_name)
    if not resolved:
        raise AuthError(f"{label} is required. Pass --{label.replace('_', '-')} or set {env_name}.")
    return resolved


def load_config(
    *,
    issuer_id: str | None = None,
    key_id: str | None = None,
    private_key: str | None = None,
    vendor_number: str | None = None,
) -> dict[str, str]:
    config = {
        "issuer_id": required_value(issuer_id, "ASC_ISSUER_ID", "issuer_id"),
        "key_id": required_value(key_id, "ASC_KEY_ID", "key_id"),
        "private_key": str(private_key_path(private_key)),
        "vendor_number": vendor_number or os.environ.get("ASC_VENDOR_NUMBER", ""),
    }
    key_path = Path(config["private_key"])
    if not key_path.exists():
        raise AuthError(
            f"Private key not found at {key_path}. Download the App Store Connect .p8 key "
            "and set ASC_PRIVATE_KEY or pass --private-key."
        )
    if key_path.stat().st_mode & 0o077:
        raise AuthError(
            f"Private key {key_path} is readable by other users. Run `chmod 600 {key_path}` first."
        )
    return config


def create_token(config: dict[str, str], *, now: int | None = None) -> str:
    try:
        import jwt
    except ImportError as exc:  # pragma: no cover - installation error path
        raise AuthError("PyJWT is missing. Install the project with `python -m pip install -e .`.") from exc

    issued_at = now or int(time.time())
    try:
        private_key = Path(config["private_key"]).read_text(encoding="utf-8")
        return jwt.encode(
            {
                "iss": config["issuer_id"],
                "iat": issued_at,
                "exp": issued_at + 1_200,
                "aud": "appstoreconnect-v1",
            },
            private_key,
            algorithm="ES256",
            headers={"kid": config["key_id"], "typ": "JWT"},
        )
    except (OSError, ValueError) as exc:
        raise AuthError(f"Could not create an App Store Connect JWT: {exc}") from exc

