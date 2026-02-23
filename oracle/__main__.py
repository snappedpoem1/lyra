"""Oracle module entry point."""

from dotenv import load_dotenv

from oracle.cli import main


if __name__ == "__main__":
    load_dotenv(override=True)
    main()
