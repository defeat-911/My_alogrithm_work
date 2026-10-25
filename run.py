"""Convenience launcher so the project works without installing the package.

    python run.py solve --packages data/packages_300.json --method alns
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))

from campus_express.cli import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())
