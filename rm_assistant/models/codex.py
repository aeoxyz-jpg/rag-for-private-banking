"""Codex CLI as the "smart" LLM (reuses the user's existing GPT auth, no API key).

NOTE: `codex exec` runs an *agent*, not a plain chat-completion endpoint — each
call spins up a session, so it is slower/heavier than a direct API. Use it for the
low-frequency high-quality role (LLM-judge, final answers), not bulk synthesis.
Runs read-only sandbox so it cannot mutate the workspace.
"""
from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path


class CodexLLM:
    def __init__(self, model: str = "", timeout: int = 600):
        self.name = f"codex:{model or 'default'}"
        self.model = model
        self.timeout = timeout

    def complete(
        self, prompt: str, *, system: str | None = None, temperature: float = 0.2
    ) -> str:
        full = f"{system}\n\n{prompt}" if system else prompt
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "last_message.txt"
            cmd = [
                "codex", "exec",
                "--skip-git-repo-check",
                "-s", "read-only",
                "-o", str(out),
            ]
            if self.model:
                cmd += ["-m", self.model]
            cmd.append(full)
            proc = subprocess.run(
                cmd, capture_output=True, text=True, timeout=self.timeout
            )
            if proc.returncode != 0:
                raise RuntimeError(f"codex exec failed: {proc.stderr.strip()[:500]}")
            return out.read_text().strip() if out.exists() else proc.stdout.strip()
