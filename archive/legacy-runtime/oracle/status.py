"""Module entrypoint for `python -m oracle.status`."""

from __future__ import annotations

import sys

from oracle.cli import main as cli_main


def main() -> None:
    """Run the CLI status command."""
    sys.argv = [sys.argv[0], "status"]
    cli_main()


if __name__ == "__main__":
    main()
