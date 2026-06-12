from __future__ import annotations

from pathlib import Path

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
        "review_extract",
        1,
    )

    assert cmd[0] == "/usr/local/bin/agy"
    assert cmd[1:3] == ["--print", "--dangerously-skip-permissions"]
    assert "--add-dir" in cmd
    assert str(book_root) in cmd
    assert cmd[-1] == f"@{prompt}"
    assert "run" not in cmd
    assert "--prompt-file" not in cmd
