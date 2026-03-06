"""Standalone entrypoint for packaged SpotDL runtime builds."""

from __future__ import annotations

from spotdl import console_entry_point


def main() -> int:
    """Invoke the SpotDL console entrypoint."""
    result = console_entry_point()
    return int(result) if isinstance(result, int) else 0


if __name__ == "__main__":
    raise SystemExit(main())
