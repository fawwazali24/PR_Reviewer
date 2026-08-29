"""Semgrep runner.

Runs Semgrep over the PR's changed files and parses results. These are used
inside the pipeline as *corroborating* evidence for LLM findings — never
surfaced as standalone findings (CI already runs this class of check).

Degrades gracefully: if Semgrep is missing or errors, we log and return [] so
a review still completes.
"""
from __future__ import annotations

import json
import logging
import subprocess
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

DEFAULT_CONFIG = "p/python"
_TIMEOUT_SECONDS = 180


@dataclass
class SemgrepFinding:
    rule_id: str
    path: str            # relative to the scanned root
    start_line: int
    end_line: int
    severity: str | None
    message: str | None
    raw: dict = field(default_factory=dict)


def run_semgrep(
    paths: list[str],
    *,
    cwd: str | None = None,
    config: str = DEFAULT_CONFIG,
) -> list[SemgrepFinding]:
    """Scan ``paths`` (relative to ``cwd``) with Semgrep; return parsed findings."""
    if not paths:
        return []

    cmd = [
        "semgrep",
        "scan",
        "--json",
        "--quiet",
        "--disable-version-check",
        "--metrics=off",
        f"--config={config}",
        *paths,
    ]
    try:
        proc = subprocess.run(
            cmd,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=_TIMEOUT_SECONDS,
        )
    except FileNotFoundError:
        logger.warning("semgrep not installed; skipping static analysis")
        return []
    except subprocess.TimeoutExpired:
        logger.warning("semgrep timed out after %ss; skipping", _TIMEOUT_SECONDS)
        return []

    if not proc.stdout:
        if proc.returncode != 0:
            logger.warning("semgrep exited %s: %s", proc.returncode, proc.stderr[:500])
        return []

    try:
        data = json.loads(proc.stdout)
    except json.JSONDecodeError:
        logger.warning("could not parse semgrep JSON output")
        return []

    findings: list[SemgrepFinding] = []
    for r in data.get("results", []):
        extra = r.get("extra", {}) or {}
        start = r.get("start", {}) or {}
        end = r.get("end", {}) or {}
        findings.append(
            SemgrepFinding(
                rule_id=r.get("check_id", "unknown"),
                path=r.get("path", ""),
                start_line=start.get("line", 0),
                end_line=end.get("line", start.get("line", 0)),
                severity=extra.get("severity"),
                message=extra.get("message"),
                raw=r,
            )
        )
    return findings
