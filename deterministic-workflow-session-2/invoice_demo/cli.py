"""The CLI always uses the live SDK; stubs are available only through test injection."""

import argparse
from pathlib import Path

from .workflow import DEFAULT_OUTPUT_ROOT, run_invoice


def main(argv: list[str] | None = None, *, output_root: Path = DEFAULT_OUTPUT_ROOT) -> int:
    parser = argparse.ArgumentParser(description="Fixed invoice pipeline: AI extracts; code validates and routes.")
    parser.add_argument("invoice", type=Path, help="One synthetic UTF-8 .txt invoice")
    args = parser.parse_args(argv)
    try:
        return run_invoice(args.invoice, output_root=output_root).exit_code
    except OSError:
        # Artifact failures may prevent an error record; never claim it was saved.
        print("[RESULT] Technical failure: could not complete run artifacts; no saved-result guarantee.")
        return 1
