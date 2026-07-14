from __future__ import annotations

import subprocess
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from books_agent.detect import DetectResult
from books_agent.providers import antigravity
from books_agent.providers.antigravity import AntigravityProvider


def test_antigravity_build_run_command_uses_print_mode(tmp_path: Path):
    book_root = tmp_path / "book"
    session_dir = book_root / "work" / "page_0001" / "agent"
    session_dir.mkdir(parents=True)
    prompt = session_dir / "prompt.md"
    prompt.write_text("# test", encoding="utf-8")

    cmd = AntigravityProvider().build_run_command(
        "/usr/local/bin/agy",
        book_root,
        session_dir,
        "render_page",
        1,
    )

    assert cmd[0] == "/usr/local/bin/agy"
    assert cmd[1:4] == ["--print-timeout", "15m", "--dangerously-skip-permissions"]
    assert "--print" in cmd
    assert "--add-dir" in cmd
    assert str(book_root) in cmd
    assert cmd[-1] == f"@{prompt}"
    assert "run" not in cmd
    assert "--prompt-file" not in cmd


def test_antigravity_auth_probe_is_shared_across_batch_threads(monkeypatch) -> None:
    provider = AntigravityProvider()
    model_calls: list[int] = []

    monkeypatch.setattr(
        antigravity,
        "detect_binary",
        lambda *_args: DetectResult(
            id="antigravity",
            label="Antigravity CLI",
            installed=True,
            path="/usr/local/bin/agy",
            version="test",
            runnable=True,
            message="found",
        ),
    )

    def fake_run(*_args, **_kwargs):
        model_calls.append(1)
        time.sleep(0.03)
        return subprocess.CompletedProcess(
            ["agy", "models"], 0, stdout="Gemini 2.5 Pro", stderr=""
        )

    monkeypatch.setattr(antigravity.subprocess, "run", fake_run)

    with ThreadPoolExecutor(max_workers=12) as executor:
        results = list(executor.map(lambda _index: provider.detect(), range(24)))

    assert len(model_calls) == 1
    assert all(result.runnable for result in results)


def test_antigravity_probe_timeout_is_shared_across_waiting_threads(monkeypatch) -> None:
    provider = AntigravityProvider()
    model_calls: list[int] = []
    monkeypatch.setattr(
        antigravity,
        "detect_binary",
        lambda *_args: DetectResult(
            id="antigravity",
            label="Antigravity CLI",
            installed=True,
            path="/usr/local/bin/agy",
            version="test",
            runnable=True,
            message="found",
        ),
    )

    def timeout(*_args, **_kwargs):
        model_calls.append(1)
        time.sleep(0.03)
        raise subprocess.TimeoutExpired(["agy", "models"], 8)

    monkeypatch.setattr(antigravity.subprocess, "run", timeout)
    with ThreadPoolExecutor(max_workers=12) as executor:
        results = list(executor.map(lambda _index: provider.detect(), range(12)))

    assert len(model_calls) == 1
    assert all(not result.runnable for result in results)
    assert all("Could not verify" in result.message for result in results)
