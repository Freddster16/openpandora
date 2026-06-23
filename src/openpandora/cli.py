"""Command line interface for OpenPandora."""

from __future__ import annotations

import argparse
from collections.abc import Sequence

from openpandora import __version__


def run_check() -> int:
    """Run local QA feedback before a user pushes code."""
    print("OpenPandora is ready.")
    print("No QA checks are connected yet. Next, this command will inspect your repo.")
    return 0


def build_parser() -> argparse.ArgumentParser:
    """Build the CLI parser so commands stay small and testable."""
    parser = argparse.ArgumentParser(
        prog="openpandora",
        description="Run beginner-friendly QA feedback for your code.",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
    )

    subparsers = parser.add_subparsers(dest="command", required=True)
    check_parser = subparsers.add_parser(
        "check",
        help="Check the current project before you push.",
    )
    check_parser.set_defaults(command_handler=run_check)

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run the OpenPandora command line interface."""
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.command_handler()
