
import os
from pathlib import Path
import sqlite3

DATA_DIR = Path(__file__).parents[1].resolve() / 'data'

def get_db_connection(db_path: Path, sql_schema: str) -> sqlite3.Connection:
    db_needs_init = not os.path.exists(db_path)
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = 1")
    if not os.path.exists(db_path):
        print(f"Database '{db_path}' does not exist. Creating from schema file...")
        conn = sqlite3.connect(db_path)
        conn.execute("PRAGMA foreign_keys = 1")
        cursor = conn.cursor()
        cursor.executescript(sql_schema)
        conn.commit()
        print(f"Database '{db_path}' created successfully.")
    return conn
