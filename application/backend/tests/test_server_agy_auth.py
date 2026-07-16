from __future__ import annotations

import asyncio
import subprocess

from books_cli import server


def test_auth_status_keeps_probed_session_when_legacy_files_are_missing(monkeypatch) -> None:
    monkeypatch.setattr(server, "credentials_present", lambda: False)
    monkeypatch.setattr(server, "_set_auth_state", lambda state, **kwargs: server._auth_cache.update({
        "state": state,
        "logged_in": state == "connected",
        "email": kwargs.get("email"),
        "message": kwargs.get("message") or "",
    }))
    server._auth_cache.update({"state": "connected", "logged_in": True})

    result = asyncio.run(server.get_auth_status())

    assert result["state"] == "connected"
    assert result["logged_in"] is True
    assert result["credential_present"] is False


def test_logout_clears_local_credentials_when_cli_logout_fails(tmp_path, monkeypatch) -> None:
    (tmp_path / "logout_agy.exp").write_text("#!/usr/bin/expect -f\n", encoding="utf-8")
    removed = []
    reset = []

    monkeypatch.setattr(server, "repo_root", lambda: tmp_path)
    monkeypatch.setattr(server.shutil, "which", lambda _name: "/usr/bin/expect")
    monkeypatch.setattr(
        server.subprocess,
        "run",
        lambda *_args, **_kwargs: subprocess.CompletedProcess([], 1, "", "failed"),
    )
    monkeypatch.setattr(server, "remove_credentials", lambda: removed.append(True))
    monkeypatch.setattr(server, "_reset_agy_caches", lambda **kwargs: reset.append(kwargs))
    server.login_session = server.LoginSession()

    result = asyncio.run(server.logout_agy_cli())

    assert result["success"] is True
    assert result["state"] == "disconnected"
    assert result["warning"]
    assert removed == [True]
    assert reset == [{"state": "disconnected", "message": "AGY CLI is not signed in."}]


def test_quota_probe_is_not_blocked_by_missing_legacy_credential_files(monkeypatch) -> None:
    class FakeProcess:
        returncode = 0

        async def communicate(self):
            return (
                b"Account: person@example.com\n"
                b"GEMINI MODELS\n"
                b"Models within this group: Gemini Flash\n"
                b"Weekly Limit\n"
                b"[bar] 50%\n"
                b"50% remaining\n",
                b"",
            )

    async def fake_subprocess(*_args, **_kwargs):
        return FakeProcess()

    monkeypatch.setattr(server, "credentials_present", lambda: False)
    monkeypatch.setattr(server.asyncio, "create_subprocess_exec", fake_subprocess)
    monkeypatch.setattr(server, "_set_auth_state", lambda state, **kwargs: server._auth_cache.update({
        "state": state,
        "logged_in": state == "connected",
        "email": kwargs.get("email"),
        "message": kwargs.get("message") or "",
    }))
    server._quota_cache.update({"data": None, "last_updated": 0.0, "is_updating": False})

    asyncio.run(server.refresh_quota_cache_async())

    assert server._quota_cache["data"]["success"] is True
    assert server._auth_cache["state"] == "connected"


def test_quota_does_not_spawn_agy_again_after_explicit_logout(monkeypatch) -> None:
    spawned = []

    async def fake_subprocess(*args, **kwargs):
        spawned.append((args, kwargs))
        raise AssertionError("AGY should not be started for passive quota polling")

    monkeypatch.setattr(server.asyncio, "create_subprocess_exec", fake_subprocess)
    server._auth_cache.update({"state": "disconnected", "logged_in": False})
    server._quota_cache.update({"data": None, "last_updated": 0.0, "is_updating": False})

    result = asyncio.run(server.get_auth_quota(force=False))

    assert result["state"] == "disconnected"
    assert spawned == []
