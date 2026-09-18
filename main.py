"""Backwards-compatible entry point. Prefer `bot-run` after install."""
import sys

from bot.cli import main

if __name__ == "__main__":
    sys.exit(main())