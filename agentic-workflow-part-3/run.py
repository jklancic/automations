"""Run one support ticket, using shared infrastructure from the repository root."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from support_demo.cli import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())
