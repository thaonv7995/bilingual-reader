from __future__ import annotations

import asyncio
import subprocess

from books_cli import server


def test_auth_status_uses_credentials_not_models(monkeypatch) -> None:
    monkeypatch.setattr(server, "credentials_present", lambda: False)
    monkeypatch.setattr(server, "_set_auth_state", lambda state, **kwargs: server._auth_cache.update({
        "state": state,
        "logged_in": state == "connected",
        "email": kwargs.get("email"),
        "message": kwargs.get("message") or "",
    }))
    server._auth_cache.update({"state": "connected", "logged_in": True})

    result = asyncio.run(server.get_auth_status())

    assert result["state"] == "disconnected"
    assert result["logged_in"] is False
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
