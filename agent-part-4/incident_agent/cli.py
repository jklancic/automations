"""One local alert per live run; no stub fallback or production action mode."""

import argparse
from pathlib import Path

from .investigation import OUTPUT_ROOT, investigate


def main(argv: list[str] | None = None, *, output_root: Path = OUTPUT_ROOT) -> int:
    parser = argparse.ArgumentParser(description="Read-only incident agent: model-directed tools, code-enforced scope and limits.")
    parser.add_argument("alert", type=Path, help="One synthetic UTF-8 .json incident alert")
    args = parser.parse_args(argv)
    try:
        return investigate(args.alert, output_root=output_root).exit_code
    except OSError:
        print("[RESULT] Technical failure: could not complete run artifacts; no saved-result guarantee.")
        return 1
