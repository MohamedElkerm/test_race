#!/usr/bin/env python3
"""Restore October 28 events, heats and results from backups/."""
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKUPS_DIR = ROOT / 'backups'

def restore(db_rel_path: str):
    db_path = ROOT / db_rel_path
    backup_file = BACKUPS_DIR / f"{db_path.stem}_20261028_october.sqlite3"
    if not backup_file.exists():
        print(f"No backup found at {backup_file}")
        return
    shutil.copy2(backup_file, db_path)
    print(f"Restored {db_rel_path} from {backup_file.name}")

if __name__ == '__main__':
    for db in ['runtime/single_test.sqlite3', 'runtime/test.sqlite3']:
        restore(db)
