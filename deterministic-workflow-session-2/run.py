"""Run from the repository root: uv run python deterministic-workflow-session-2/run.py INPUT"""

import sys
from pathlib import Path

# Make root-level infrastructure importable when running this file directly.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from invoice_demo.cli import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())
