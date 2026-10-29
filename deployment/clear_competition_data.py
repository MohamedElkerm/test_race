#!/usr/bin/env python3
"""Clear all events, heats, entries and results from SQLite databases.
Saves a full timestamped backup of current data into backups/ directory first.
"""
import shutil
import sqlite3
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKUPS_DIR = ROOT / 'backups'
BACKUPS_DIR.mkdir(parents=True, exist_ok=True)

TABLES_TO_CLEAR = [
    'approvals',
    'jury_decisions',
    'results',
    'timings',
    'entries',
    'relay_members',
    'heats',
    'events',
    'sessions',
    'championships',
    'teams',
    'athletes',
    'universities',
]

def backup_and_clear(db_rel_path: str):
    db_path = ROOT / db_rel_path
    if not db_path.exists():
        print(f"Skipping {db_rel_path} (does not exist)")
        return

    # 1. Create backup
    timestamp = time.strftime('%Y%m%d_%H%M%S')
    backup_file = BACKUPS_DIR / f"{db_path.stem}_{timestamp}.sqlite3"
    oct28_backup_file = BACKUPS_DIR / f"{db_path.stem}_20261028_october.sqlite3"
    
    shutil.copy2(db_path, backup_file)
    if not oct28_backup_file.exists():
        shutil.copy2(db_path, oct28_backup_file)
    print(f"Backed up {db_rel_path} -> {backup_file.name}")

    # 2. Clear tables
    conn = sqlite3.connect(str(db_path))
    c = conn.cursor()
    c.execute("PRAGMA foreign_keys = OFF")
    c.execute("BEGIN IMMEDIATE")
    
    cleared_counts = {}
    for table in TABLES_TO_CLEAR:
        c.execute(f"SELECT COUNT(*) FROM {table}")
        count = c.fetchone()[0]
        c.execute(f"DELETE FROM {table}")
        cleared_counts[table] = count

    # Reset graphics, routes, and selected_heat
    c.execute("UPDATE graphics SET preview=NULL, program=NULL, held=0 WHERE id='tv'")
    c.execute("UPDATE routes SET heat_id=NULL, content='idle'")
    c.execute("UPDATE meta SET value='' WHERE key='selected_heat'")
    c.execute("UPDATE meta SET value=CAST(value AS INTEGER)+1 WHERE key='revision'")

    conn.commit()
    c.execute("PRAGMA foreign_keys = ON")
    c.execute("VACUUM")
    conn.close()

    print(f"Cleared {db_rel_path}: {cleared_counts}")

if __name__ == '__main__':
    print("=" * 60)
    print(" Hiding & Clearing All Events, Heats & Athletes Data")
    print("=" * 60)
    for db in ['runtime/single_test.sqlite3', 'runtime/test.sqlite3']:
        backup_and_clear(db)
    print("=" * 60)
    print("Done! All old events, heats, and athletes are cleared.")
    print("The system is now clean and ready for the new day's program.")
    print("=" * 60)
