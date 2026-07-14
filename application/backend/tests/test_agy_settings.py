from __future__ import annotations

from pathlib import Path

from books_cli.agy_settings import (
    credentials_present,
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


def test_parse_eligibility_failure_is_not_reported_as_ready() -> None:
    parsed = parse_quota_output("Eligibility check failed: verify your account\n" + QUOTA)

    assert parsed["state"] == "needs_verification"
    assert parsed["raw_has_quota"] is True
    assert "verification" in parsed["message"].lower()


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
