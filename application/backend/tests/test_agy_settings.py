from __future__ import annotations

from pathlib import Path

from books_cli.agy_settings import (
    credentials_present,
    extract_oauth_url,
    keychain_credential_present,
    parse_quota_output,
    remove_credentials,
)


QUOTA = """
Antigravity CLI 1.1.2
person@example.com
└ Models & Quota
  Account: person@example.com
GEMINI MODELS
  Models within this group: Gemini Flash, Gemini Pro
  Weekly Limit
    [██████] 46.88%
    47% remaining · Refreshes in 13h
  Five Hour Limit
    [██████] 100.00%
    Quota available
CLAUDE AND GPT MODELS
  Models within this group: Claude Opus, Claude Sonnet, GPT-OSS
  Weekly Limit
    [██████] 93.49%
    93% remaining · Refreshes in 20h
"""


def test_parse_connected_quota_snapshot() -> None:
    parsed = parse_quota_output(QUOTA)

    assert parsed["state"] == "connected"
    assert parsed["quota"]["account"] == "person@example.com"
    assert len(parsed["quota"]["groups"]) == 2
    assert parsed["quota"]["groups"][0]["limits"][0]["percent"] == 46.88


def test_parse_eligibility_failure_does_not_override_authorization() -> None:
    parsed = parse_quota_output("Eligibility check failed: verify your account\n" + QUOTA)

    assert parsed["state"] == "connected"
    assert parsed["raw_has_quota"] is True


def test_parse_account_header_is_enough_to_confirm_authorization() -> None:
    parsed = parse_quota_output(
        "Antigravity CLI 1.1.3\nperson@example.com\nEligibility check failed: unknown reason"
    )

    assert parsed["state"] == "connected"
    assert parsed["quota"]["account"] == "person@example.com"
    assert parsed["message"] == "AGY authorization completed."


def test_parse_signed_out_snapshot() -> None:
    parsed = parse_quota_output(
        "Welcome to the Antigravity CLI. You are currently not signed in.\n"
        "Select login method:\n1. Google OAuth"
    )

    assert parsed["state"] == "disconnected"
    assert parsed["raw_has_quota"] is False


def test_remove_credentials_preserves_noncredential_cli_state(tmp_path: Path) -> None:
    auth_dir = tmp_path / ".gemini" / "antigravity-cli"
    auth_dir.mkdir(parents=True)
    token = auth_dir / "antigravity-oauth-token"
    state = auth_dir / "jetski_state.pbtxt"
    token.write_text("token", encoding="utf-8")
    state.write_text("state", encoding="utf-8")

    assert credentials_present(tmp_path)
    removed = remove_credentials(tmp_path)

    assert removed == [token]
    assert not credentials_present(tmp_path)
    assert state.read_text(encoding="utf-8") == "state"


def test_extract_oauth_url_from_osc8_terminal_link() -> None:
    url = (
        "https://accounts.google.com/signin/continue?continue="
        "https://developers.google.com/gemini-code-assist/auth/success&authuser"
    )
    output = f"Open \x1b]8;id=url;{url}\x07Google sign-in\x1b]8;;\x07"

    assert extract_oauth_url(output) == url


def test_extract_oauth_url_accepts_non_google_oauth_host() -> None:
    url = "https://login.example.test/oauth/authorize?client_id=agy&amp;scope=openid"

    assert extract_oauth_url(f"Continue at {url}.\n") == url.replace("&amp;", "&")


def test_keychain_check_uses_agy_service_without_reading_secret(monkeypatch) -> None:
    calls = []

    class Result:
        returncode = 0

    monkeypatch.setattr("books_cli.agy_settings.sys.platform", "darwin")
    monkeypatch.setattr("books_cli.agy_settings.shutil.which", lambda name: "/usr/bin/security")
    monkeypatch.setattr(
        "books_cli.agy_settings.subprocess.run",
        lambda *args, **kwargs: calls.append((args, kwargs)) or Result(),
    )

    assert keychain_credential_present() is True
    command = calls[0][0][0]
    assert command == [
        "security",
        "find-generic-password",
        "-a",
        "antigravity",
        "-s",
        "gemini",
    ]
    assert "-w" not in command


def test_remove_credentials_deletes_current_agy_keychain_item(monkeypatch) -> None:
    calls = []

    class Result:
        returncode = 0

    monkeypatch.setattr("books_cli.agy_settings.sys.platform", "darwin")
    monkeypatch.setattr("books_cli.agy_settings.shutil.which", lambda name: "/usr/bin/security")
    monkeypatch.setattr("books_cli.agy_settings.credential_paths", lambda home=None: [])
    monkeypatch.setattr(
        "books_cli.agy_settings.subprocess.run",
        lambda *args, **kwargs: calls.append((args, kwargs)) or Result(),
    )

    assert remove_credentials() == []
    assert calls[0][0][0] == [
        "security",
        "delete-generic-password",
        "-a",
        "antigravity",
        "-s",
        "gemini",
    ]
