"""Security and auth helper tests."""

import os

from app.credentials import (
    CredentialsDecryptError,
    encrypt_secret,
    decrypt_secret,
    mask_secret,
    is_masked_placeholder,
    encrypt_credentials,
    decrypt_credentials,
)
from app.url_safety import assert_safe_fetch_url, is_public_http_url
from app.local_auth import is_loopback


def test_secret_roundtrip_and_mask():
    enc = encrypt_secret("super-secret-key-1234")
    assert enc.startswith("fernet:")
    assert decrypt_secret(enc) == "super-secret-key-1234"
    assert mask_secret("super-secret-key-1234").endswith("1234")
    assert is_masked_placeholder("••••1234")
    assert not is_masked_placeholder("brand-new-key")


def test_legacy_plaintext_secret_passthrough():
    assert decrypt_secret("legacy-plain") == "legacy-plain"


def test_credentials_dict_roundtrip():
    blob = encrypt_credentials({"access_token": "abc", "refresh_token": "xyz"})
    data = decrypt_credentials(blob)
    assert data["access_token"] == "abc"
    assert "client_secret" not in data


def test_credentials_decrypt_error_on_bad_token():
    import pytest

    with pytest.raises(CredentialsDecryptError):
        decrypt_credentials("not-a-valid-fernet-token")
    with pytest.raises(CredentialsDecryptError):
        decrypt_secret("fernet:totally-bogus-ciphertext")


def test_url_safety_blocks_localhost_and_metadata():
    assert assert_safe_fetch_url("http://127.0.0.1/x") is not None
    assert assert_safe_fetch_url("http://localhost/admin") is not None
    assert assert_safe_fetch_url("not-a-url") is not None
    assert assert_safe_fetch_url("ftp://example.com") is not None


def test_url_safety_allows_public_https():
    # example.com resolves publicly
    assert is_public_http_url("https://example.com/page") is True
    assert assert_safe_fetch_url("https://example.com/page") is None


def test_loopback_hosts():
    assert is_loopback("127.0.0.1")
    assert is_loopback("::1")
    assert is_loopback("localhost")
    assert not is_loopback("8.8.8.8")


def test_api_token_required_flag_off_in_tests():
    assert os.getenv("KINEAXIS_REQUIRE_API_TOKEN") == "0"


def test_auth_required_and_token_compare():
    from app.local_auth import auth_required, _tokens_equal, _is_api_path, _is_public_pulse_get

    # Default test env has token requirement off
    assert auth_required() is False
    assert _tokens_equal("abc", "abc") is True
    assert _tokens_equal("abc", "abd") is False
    assert _tokens_equal("", "abc") is False
    assert _is_api_path("/clients/") is True
    assert _is_api_path("/experiments/") is True
    assert _is_api_path("/pulse/share") is True
    assert _is_public_pulse_get("/pulse/abc123token/html", "GET") is True
    assert _is_public_pulse_get("/pulse/share", "POST") is False


def test_auth_middleware_returns_401_when_token_required(monkeypatch):
    """With token required, API paths without a token must 401."""
    from starlette.applications import Starlette
    from starlette.requests import Request
    from starlette.responses import JSONResponse
    from starlette.routing import Route
    from starlette.testclient import TestClient

    import app.local_auth as local_auth

    token = "beta-test-token-32chars-minimum!!"
    monkeypatch.setenv("KINEAXIS_REQUIRE_API_TOKEN", "1")
    monkeypatch.setenv("KINEAXIS_ALLOW_REMOTE", "0")
    monkeypatch.setattr(local_auth, "API_TOKEN", token)

    async def ok(_request: Request):
        return JSONResponse({"ok": True})

    app = Starlette(routes=[Route("/clients/", ok)])
    app.add_middleware(local_auth.LocalAuthMiddleware)
    client = TestClient(app)

    denied = client.get("/clients/")
    assert denied.status_code == 401

    allowed = client.get("/clients/", headers={"X-Kinexis-Token": token})
    assert allowed.status_code == 200
