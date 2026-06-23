"""Build a small executable zipapp for OpenPandora releases."""

from __future__ import annotations

import argparse
import zipapp
from pathlib import Path

DEFAULT_OUTPUT = Path("dist") / "openpandora.pyz"


def build_release(output_path: str | Path = DEFAULT_OUTPUT) -> Path:
    """Create the release artifact users can download and run."""
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    zipapp.create_archive(
        "src",
        target=output,
        main="openpandora.cli:main",
        interpreter="/usr/bin/env python3.11",
        compressed=True,
    )
    return output


def build_parser() -> argparse.ArgumentParser:
    """Build the release script parser."""
    parser = argparse.ArgumentParser(description="Build OpenPandora release zipapp.")
    parser.add_argument(
        "--output",
        default=str(DEFAULT_OUTPUT),
        help="Where to write the executable zipapp.",
    )
    return parser


def main() -> int:
    """Run the release builder."""
    args = build_parser().parse_args()
    output = build_release(args.output)
    print(f"Built {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
