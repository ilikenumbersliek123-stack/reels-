"""Install the weekly job into the user's crontab.

Deliberately thin: it writes one marked line and can remove exactly that line
again. Anything more (systemd timers, launchd plists) is better done by hand
than badly by a tool, and the GitHub Actions workflow covers the case where you
do not want a machine that has to be awake on Monday morning.
"""

from __future__ import annotations

import os
import subprocess
import sys

MARKER = "# reels-tracker weekly"
DEFAULT_CRON = "0 9 * * 1"  # Mondays at 09:00 local time


class CronUnavailable(RuntimeError):
    pass


def _repo_root() -> str:
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def command(db_path: str, window_days: int, llm: str, ideas: int) -> str:
    root = _repo_root()
    log = os.path.join(root, "reports", "cron.log")
    return (
        f"cd {root} && {sys.executable} -m app --db {db_path} weekly "
        f"--window-days {window_days} --llm {llm} --ideas {ideas} >> {log} 2>&1"
    )


def _read() -> list[str]:
    try:
        result = subprocess.run(["crontab", "-l"], capture_output=True, text=True)
    except FileNotFoundError as exc:
        raise CronUnavailable(
            "no `crontab` on this system. Use the GitHub Actions workflow in "
            ".github/workflows/weekly.yml, or your platform's scheduler, calling: "
            "python -m app weekly"
        ) from exc
    # An empty crontab exits non-zero on most platforms; that is not an error.
    return result.stdout.splitlines() if result.returncode == 0 else []


def _write(lines: list[str]) -> None:
    body = "\n".join(lines).strip() + "\n"
    try:
        subprocess.run(["crontab", "-"], input=body, text=True, check=True)
    except FileNotFoundError as exc:
        raise CronUnavailable("no `crontab` on this system") from exc


def _without_ours(lines: list[str]) -> list[str]:
    kept, skip_next = [], False
    for line in lines:
        if line.strip() == MARKER:
            skip_next = True
            continue
        if skip_next:
            skip_next = False
            continue
        kept.append(line)
    return kept


def install(
    db_path: str,
    cron: str = DEFAULT_CRON,
    window_days: int = 90,
    llm: str = "auto",
    ideas: int = 12,
) -> str:
    os.makedirs(os.path.join(_repo_root(), "reports"), exist_ok=True)
    entry = f"{cron} {command(db_path, window_days, llm, ideas)}"
    lines = _without_ours(_read()) + [MARKER, entry]
    _write(lines)
    return entry


def remove() -> bool:
    lines = _read()
    trimmed = _without_ours(lines)
    if len(trimmed) == len(lines):
        return False
    _write(trimmed)
    return True


def show() -> list[str]:
    lines = _read()
    return [line for i, line in enumerate(lines) if line.strip() == MARKER or (i and lines[i - 1].strip() == MARKER)]
