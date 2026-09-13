"""Consistent SQLite backup, including committed WAL data. No automatic deletion."""
import argparse
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
import sqlite3
import tempfile


def backup_database(source: Path, output_dir: Path) -> Path:
    source = source.resolve(strict=True)
    output_dir.mkdir(parents=True, exist_ok=True)
    destination = output_dir / (source.stem + "-" + datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S-%f") + ".db")
    with tempfile.NamedTemporaryFile(dir=output_dir, suffix=".partial", delete=False) as file:
        partial = Path(file.name)
    try:
        # Read-only URI prevents accidentally creating an empty source database.
        with closing(sqlite3.connect(source.as_uri() + "?mode=ro", uri=True)) as connection, closing(sqlite3.connect(partial)) as backup:
            connection.backup(backup)
            if backup.execute("PRAGMA quick_check").fetchone() != ("ok",):
                raise RuntimeError("SQLite backup integrity check failed")
        partial.replace(destination)
        return destination
    finally:
        partial.unlink(missing_ok=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("database", type=Path)
    parser.add_argument("--output-dir", type=Path, default=Path(__file__).resolve().parents[1] / "backups")
    args = parser.parse_args()
    print(backup_database(args.database, args.output_dir))
