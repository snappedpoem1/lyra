"""Standalone entrypoint for packaged Streamrip runtime builds."""

from __future__ import annotations

from streamrip.rip import rip


def main() -> int:
    """Invoke the Streamrip CLI entrypoint."""
    result = rip()
    return int(result) if isinstance(result, int) else 0


if __name__ == "__main__":
    raise SystemExit(main())
