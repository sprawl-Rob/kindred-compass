"""Runtime configuration: where data lives.

All research data lives under a single data directory so it can be backed up
as one unit:

    <data_dir>/kindred.sqlite3     SQLite database (research data, directory, settings)
    <data_dir>/attachments/        user attachments, content-addressed subfolders
    <data_dir>/backups/            backups created from the app
    <data_dir>/imports/<id>/       original GEDCOM uploads (byte-for-byte) and staged media for each import

Default data dir is ./data next to the project; override with KINDRED_DATA_DIR.
API credentials are NOT stored here (see app/ai/credentials.py).
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
APP_NAME = "Kindred Compass"
APP_VERSION = "1.0.0"


@dataclass(frozen=True)
class Settings:
    data_dir: Path

    @property
    def db_path(self) -> Path:
        return self.data_dir / "kindred.sqlite3"

    @property
    def attachments_dir(self) -> Path:
        return self.data_dir / "attachments"

    @property
    def backups_dir(self) -> Path:
        return self.data_dir / "backups"

    @property
    def imports_dir(self) -> Path:
        return self.data_dir / "imports"

    def ensure(self) -> None:
        for d in (self.data_dir, self.attachments_dir, self.backups_dir, self.imports_dir):
            d.mkdir(parents=True, exist_ok=True)


def load_settings(data_dir: str | os.PathLike | None = None) -> Settings:
    raw = data_dir or os.environ.get("KINDRED_DATA_DIR") or (PROJECT_ROOT / "data")
    s = Settings(Path(raw).expanduser().resolve())
    s.ensure()
    return s
