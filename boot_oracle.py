"""
Lyra Oracle — Boot Launcher
Double-click (or run via boot_oracle.bat) to start all services.

Starts in order:
  1. Docker Desktop (if daemon not running)
  2. docker compose up -d  (prowlarr, rdtclient, slskd, qobuz)
  3. LM Studio server + model load
  4. Prints a final health table and exits
"""

from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path

# Allow running from project root without installing the package
PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT))

# Load .env before importing oracle modules
try:
    from dotenv import load_dotenv
    load_dotenv(PROJECT_ROOT / ".env")
except ImportError:
    pass

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from oracle.bootstrap import (
    _http_ready,
    ensure_docker_services,
    ensure_lmstudio,
)

console = Console()

# ---------------------------------------------------------------------------
# Docker Desktop paths (Windows)
# ---------------------------------------------------------------------------

def _find_docker_desktop() -> Path | None:
    candidates = [
        Path(os.environ.get("ProgramFiles", r"C:\Program Files"))
        / "Docker" / "Docker" / "Docker Desktop.exe",
        Path(os.environ.get("LOCALAPPDATA", ""))
        / "Docker Desktop" / "Docker Desktop.exe",
        Path(os.environ.get("ProgramW6432", r"C:\Program Files"))
        / "Docker" / "Docker" / "Docker Desktop.exe",
    ]
    for p in candidates:
        if p and p.exists():
            return p
    return None


def _docker_daemon_ready(timeout: float = 5.0) -> bool:
    try:
        r = subprocess.run(
            ["docker", "info"],
            capture_output=True,
            timeout=timeout,
        )
        return r.returncode == 0
    except Exception:
        return False


def _start_docker_desktop() -> bool:
    """Launch Docker Desktop and wait up to 90s for the daemon."""
    exe = _find_docker_desktop()
    if not exe:
        return False
    console.print(f"  [dim]Launching {exe.name}...[/]")
    subprocess.Popen(
        [str(exe)],
        cwd=str(exe.parent),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    for _ in range(90):
        time.sleep(1)
        if _docker_daemon_ready(timeout=3):
            return True
    return False


# ---------------------------------------------------------------------------
# Health endpoints
# ---------------------------------------------------------------------------

SERVICE_URLS: dict[str, str] = {
    "Prowlarr":    "http://localhost:9696/health",
    "Real-Debrid": "http://localhost:6500",
    "Slskd":       "http://localhost:5030/api/v0/application",
    "Qobuz":       "http://localhost:7700/health",
    "LM Studio":   "http://127.0.0.1:1234/v1/models",
}


# ---------------------------------------------------------------------------
# Main boot sequence
# ---------------------------------------------------------------------------

def main() -> None:
    console.print()
    console.print(Panel.fit(
        "[bold magenta]Lyra Oracle[/]  [dim]boot sequence[/]",
        border_style="magenta",
    ))
    console.print()

    errors: list[str] = []

    # ── Step 1: Docker daemon ────────────────────────────────────────────────
    console.print("[bold cyan]1/3  Docker daemon[/]")
    if _docker_daemon_ready():
        console.print("     [green]already running[/]\n")
    else:
        console.print("     [yellow]not running — starting Docker Desktop...[/]")
        if _find_docker_desktop() is None:
            msg = "Docker Desktop not found on this machine"
            console.print(f"     [red]{msg}[/]\n")
            errors.append(msg)
        else:
            ok = _start_docker_desktop()
            if ok:
                console.print("     [green]daemon ready[/]\n")
            else:
                msg = "Docker daemon did not start within 90 s"
                console.print(f"     [red]{msg}[/]\n")
                errors.append(msg)

    # ── Step 2: Docker services ──────────────────────────────────────────────
    console.print("[bold cyan]2/3  Docker services  [dim](prowlarr · rdtclient · slskd · qobuz)[/][/]")
    with console.status("     starting containers…"):
        d = ensure_docker_services(
            services=["prowlarr", "rdtclient", "slskd", "qobuz"],
            timeout_seconds=60,
        )
    if d.get("ready"):
        label = "already running" if not d.get("started") else "started"
        console.print(f"     [green]{label}[/]\n")
    else:
        msg = d.get("error") or "docker compose up failed"
        console.print(f"     [red]{msg}[/]\n")
        errors.append(f"Docker services: {msg}")

    # ── Step 3: LM Studio ───────────────────────────────────────────────────
    console.print("[bold cyan]3/3  LM Studio[/]")
    with console.status("     starting server…"):
        lm = ensure_lmstudio(timeout_seconds=60)
    if lm.get("ready"):
        model_info = ""
        if lm.get("model_boot_ok"):
            model_info = f"  [dim]model: {lm.get('model_boot_detail', '')}[/]"
        label = "already running" if not lm.get("started") else "started"
        console.print(f"     [green]{label}[/]{model_info}\n")
    else:
        msg = lm.get("error") or "LM Studio did not respond"
        console.print(f"     [yellow]{msg}[/]  [dim](non-blocking)[/]\n")
        # LM Studio is optional — don't add to hard errors

    # ── Final health table ───────────────────────────────────────────────────
    table = Table(title="Service Health", border_style="blue", title_style="bold blue")
    table.add_column("Service", style="cyan", min_width=14)
    table.add_column("Status", min_width=6)
    table.add_column("URL", style="dim")

    all_up = True
    for name, url in SERVICE_URLS.items():
        up = _http_ready(url, timeout=4)
        if not up and name != "LM Studio":
            all_up = False
        status_str = "[green]  UP  [/]" if up else "[red] DOWN [/]"
        table.add_row(name, status_str, url)

    console.print(table)
    console.print()

    if errors:
        console.print("[bold red]Errors:[/]")
        for e in errors:
            console.print(f"  [red]• {e}[/]")
        console.print()

    if all_up:
        console.print("[bold green]All services ready.[/]  You can now run [cyan]oracle[/] commands.")
    else:
        console.print("[yellow]Some services are down — check errors above.[/]")

    console.print()
    console.print("[dim]Press Enter to close...[/]")
    try:
        input()
    except (EOFError, KeyboardInterrupt):
        pass


if __name__ == "__main__":
    main()
