from __future__ import annotations

import os
import subprocess
import threading
from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Callable

from books_agent.detect import DetectResult, detect_binary
from books_agent.phases import AgentPhase


@dataclass
class RunResult:
    provider: str
    phase: str
    exit_code: int
    command: list[str]
    stdout: str
    stderr: str
    log_path: str
    suggested_shell: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class Provider(ABC):
    id: str
    label: str
    binary_names: list[str]

    def detect(self) -> DetectResult:
        return detect_binary(self.id, self.label, self.binary_names)

    @abstractmethod
    def build_run_command(
        self,
        binary: str,
        book_root: Path,
        session_dir: Path,
        phase: AgentPhase,
        page: int,
    ) -> list[str]:
        """Argv for subprocess; inherits user environment (auth)."""

    def suggested_shell_command(
        self,
        binary: str,
        book_root: Path,
        session_dir: Path,
        phase: AgentPhase,
        page: int,
    ) -> str:
        argv = self.build_run_command(binary, book_root, session_dir, phase, page)
        quoted = " ".join(_shell_quote(a) for a in argv)
        return f"cd {_shell_quote(str(book_root))} && {quoted}"

    def run(
        self,
        book_root: Path,
        session_dir: Path,
        phase: AgentPhase,
        page: int,
        *,
        timeout_s: int | None = None,
        on_log_line: Callable[[str], None] | None = None,
    ) -> RunResult:
        det = self.detect()
        if not det.installed or not det.path:
            raise RuntimeError(det.message)
        binary = det.path
        cmd = self.build_run_command(binary, book_root, session_dir, phase, page)
        shell_line = self.suggested_shell_command(binary, book_root, session_dir, phase, page)
        (session_dir / "run.sh").write_text(
            "#!/usr/bin/env bash\nset -euo pipefail\n" + shell_line + "\n",
            encoding="utf-8",
        )

        def emit(line: str, stream: str) -> None:
            if on_log_line:
                on_log_line(f"[{stream}] {line.rstrip()}")

        stdout_chunks: list[str] = []
        stderr_chunks: list[str] = []

        try:
            proc = subprocess.Popen(
                cmd,
                cwd=book_root,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                env=os.environ.copy(),
            )

            def pump(pipe, chunks: list[str], stream: str) -> None:
                if pipe is None:
                    return
                for line in pipe:
                    chunks.append(line)
                    emit(line, stream)

            threads = [
                threading.Thread(target=pump, args=(proc.stdout, stdout_chunks, "stdout"), daemon=True),
                threading.Thread(target=pump, args=(proc.stderr, stderr_chunks, "stderr"), daemon=True),
            ]
            for t in threads:
                t.start()
            import time
            import json
            from books_core.validation import validate_draft_html

            expected_output = None
            try:
                context_path = session_dir / "context.json"
                if context_path.is_file():
                    ctx_data = json.loads(context_path.read_text(encoding="utf-8"))
                    lang = ctx_data.get("lang")
                    expected_output = book_root / "output" / lang / f"page_{page:04d}.html"
            except Exception:
                pass

            completed_successfully = False
            try:
                start_time = time.time()
                while proc.poll() is None:
                    if expected_output and expected_output.is_file() and expected_output.stat().st_mtime >= start_time - 1 and expected_output.stat().st_size > 0:
                        try:
                            content = expected_output.read_text(encoding="utf-8")
                            validate_draft_html(content)
                            completed_successfully = True
                            proc.terminate()
                            try:
                                proc.wait(timeout=2)
                            except subprocess.TimeoutExpired:
                                proc.kill()
                            break
                        except Exception:
                            pass
                    time.sleep(1)
                    if timeout_s and (time.time() - start_time > timeout_s):
                        raise subprocess.TimeoutExpired(cmd, timeout_s)
            except subprocess.TimeoutExpired as exc:
                proc.kill()
                proc.wait()
                exc.stdout = "".join(stdout_chunks)
                exc.stderr = "".join(stderr_chunks)
                raise exc
            for t in threads:
                t.join(timeout=5)

            # The process can write its output immediately before exiting, after
            # the polling loop's last iteration. Validate once more before
            # deciding whether an otherwise-zero exit was successful.
            if not completed_successfully and expected_output and expected_output.is_file():
                try:
                    content = expected_output.read_text(encoding="utf-8")
                    validate_draft_html(content)
                    completed_successfully = expected_output.stat().st_mtime >= start_time - 1
                except Exception:
                    completed_successfully = False

            if completed_successfully or proc.returncode == 0:
                returncode = 0
            else:
                returncode = proc.returncode if proc.returncode is not None else -1

            if returncode == 0 and expected_output and not completed_successfully:
                diagnostic = (
                    "Agent exited with code 0 but did not create a fresh, valid output file at "
                    f"{expected_output}. Check authentication and the agent stdout/stderr above."
                )
                stderr_chunks.append(diagnostic + "\n")
                emit(diagnostic, "system")
                returncode = 3
        except subprocess.TimeoutExpired as exc:
            log = session_dir / "log.txt"
            log.write_text(f"TIMEOUT\n{exc}\n", encoding="utf-8")
            if on_log_line:
                on_log_line("[system] Agent timed out")
            return RunResult(
                provider=self.id,
                phase=phase,
                exit_code=-1,
                command=cmd,
                stdout=exc.stdout or "",
                stderr=exc.stderr or "",
                log_path=str(log),
                suggested_shell=shell_line,
            )

        stdout = "".join(stdout_chunks)
        stderr = "".join(stderr_chunks)
        log_body = "\n".join(
            [
                f"# command: {' '.join(cmd)}",
                f"# exit: {returncode}",
                "",
                "## stdout",
                stdout,
                "",
                "## stderr",
                stderr,
            ]
        )
        log = session_dir / "log.txt"
        log.write_text(log_body, encoding="utf-8")
        return RunResult(
            provider=self.id,
            phase=phase,
            exit_code=returncode,
            command=cmd,
            stdout=stdout,
            stderr=stderr,
            log_path=str(log),
            suggested_shell=shell_line,
        )


def _shell_quote(s: str) -> str:
    if not s:
        return "''"
    if all(c.isalnum() or c in "/._-:" for c in s):
        return s
    return "'" + s.replace("'", "'\"'\"'") + "'"
