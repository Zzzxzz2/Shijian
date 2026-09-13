"""Release configuration and backup regression checks; no production credentials."""
import os
from pathlib import Path
import runpy
import sqlite3
import subprocess
import sys
import tempfile

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("secret", ["", "short", "replace-with-a-random-secret", "shijian-dev-secret-key-change-in-production"])
def test_production_rejects_example_jwt(secret):
    result = subprocess.run([sys.executable, "-c", "import config"], cwd=ROOT / "backend",
                            env={**os.environ, "ENV": "production", "JWT_SECRET": secret}, capture_output=True)
    assert result.returncode != 0
    assert b"JWT_SECRET must be" in result.stderr


def test_production_accepts_generated_jwt():
    import secrets
    result = subprocess.run([sys.executable, "-c", "import config"], cwd=ROOT / "backend",
                            env={**os.environ, "ENV": "production", "JWT_SECRET": secrets.token_urlsafe(48)}, capture_output=True)
    assert result.returncode == 0


@pytest.mark.parametrize("key", ["", "00" * 32])
def test_production_rejects_missing_or_development_aes(monkeypatch, key):
    from services.crypto import _get_key
    monkeypatch.setenv("ENV", "production")
    monkeypatch.setenv("API_KEY_ENCRYPTION_KEY", key)
    with pytest.raises(RuntimeError, match="API_KEY_ENCRYPTION_KEY"):
        _get_key()


@pytest.mark.asyncio
@pytest.mark.parametrize("production", [True, False])
async def test_bootstrap_requires_nonproduction_explicit_database(monkeypatch, production):
    # Importing the script must not create/reset any users.
    module = runpy.run_path(str(ROOT / "backend/bootstrap_e2e.py"))
    monkeypatch.setenv("ENV", "production" if production else "development")
    monkeypatch.delenv("DATABASE_URL", raising=False)
    with pytest.raises(RuntimeError, match="production" if production else "DATABASE_URL"):
        await module["main"]()


def test_backup_restores_committed_wal_data():
    module = runpy.run_path(str(ROOT / "scripts/backup_sqlite.py"))
    parent = ROOT / "test-results"
    parent.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(dir=parent) as folder:
        source = Path(folder) / "source.db"
        with sqlite3.connect(source) as writer:
            writer.execute("PRAGMA journal_mode=WAL")
            writer.execute("CREATE TABLE evidence (value TEXT)")
            writer.execute("INSERT INTO evidence VALUES ('committed')")
            writer.commit()
            writer.execute("INSERT INTO evidence VALUES ('uncommitted')")
            backup = module["backup_database"](source, Path(folder) / "backups")
            with sqlite3.connect(backup) as restored:
                assert restored.execute("SELECT value FROM evidence").fetchall() == [("committed",)]
                assert restored.execute("PRAGMA quick_check").fetchone() == ("ok",)
            writer.rollback()
        writer.close()
        restored.close()
        with pytest.raises(FileNotFoundError):
            module["backup_database"](Path(folder) / "missing.db", Path(folder) / "backups")
