"""One ticket per live run; test stubs are not a CLI fallback mode."""

import argparse
from pathlib import Path

from .workflow import OUTPUT_ROOT, run_ticket


def main(argv: list[str] | None = None, *, output_root: Path = OUTPUT_ROOT) -> int:
    parser = argparse.ArgumentParser(description="Support triage: fixed stages, bounded AI retrieval, mandatory human review.")
    parser.add_argument("ticket", type=Path, help="One synthetic UTF-8 .json ticket")
    args = parser.parse_args(argv)
    try:
        return run_ticket(args.ticket, output_root=output_root).exit_code
    except OSError:
        print("[RESULT] Technical failure: could not complete run artifacts; no saved-result guarantee.")
        return 1
