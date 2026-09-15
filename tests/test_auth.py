import json

import pytest

from youtube_studio_mcp import auth
from youtube_studio_mcp.auth import NotAuthenticatedError
from youtube_studio_mcp.config import SCOPES, Settings


def _settings(tmp_path) -> Settings:
    return Settings(
        data_dir=tmp_path,
        client_secret_file=tmp_path / "client_secret.json",
        token_file=tmp_path / "token.json",
        cache_file=tmp_path / "cache.db",
        cache_ttl_seconds=3600,
        pillars_file=tmp_path / "pilares.json",
    )


def _write_token(path, scopes, expiry="2999-01-01T00:00:00Z"):
    path.write_text(
        json.dumps(
            {
                "token": "tok",
                "refresh_token": "refresh",
                "token_uri": "https://oauth2.googleapis.com/token",
                "client_id": "cid",
                "client_secret": "secret",
                "scopes": scopes,
                "expiry": expiry,
            }
        )
    )


def test_insufficient_scopes_requires_reconsent(tmp_path, monkeypatch):
    # A token minted before Phase 1 only has the Data API scope.
    _write_token(tmp_path / "token.json", ["https://www.googleapis.com/auth/youtube.readonly"])
    # Guard: never open a browser during this check.
    monkeypatch.setattr(auth, "login", lambda *a, **k: pytest.fail("must not open a browser"))

    with pytest.raises(NotAuthenticatedError) as exc:
        auth.load_credentials(_settings(tmp_path))

    assert "consent" in str(exc.value).lower() or "consentimento" in str(exc.value).lower()


def test_all_scopes_present_does_not_require_reconsent(tmp_path):
    # A still-valid token carrying both scopes loads without a browser or refresh.
    _write_token(tmp_path / "token.json", SCOPES)
    creds = auth.load_credentials(_settings(tmp_path))
    assert creds.has_scopes(SCOPES)
