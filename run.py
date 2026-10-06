"""Convenience launcher: `python run.py` (same as `python -m app`) from any working directory."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from app.__main__ import main  # noqa: E402

if __name__ == "__main__":
    main()
