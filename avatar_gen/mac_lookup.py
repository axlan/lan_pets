
import json
from pathlib import Path
import sys
import sqlite3
import os

_REPO_PATH = Path(__file__).parents[1].resolve()
_DB_PATH = _REPO_PATH / 'data/mac_lookup.sqlite3'

_SCHEMA_SQL = '''\
CREATE TABLE mac_oui_info (
    mac_oui INT NOT NULL,    -- MAC oui as integer
    vendor TEXT NOT NULL     -- Name of the client
);
'''


def strip_separator(mac_str: str):
    mac_str = mac_str.replace(':', '')
    return mac_str.replace('-', '')


def get_oui_integer(mac_str: str):
    mac_str = strip_separator(mac_str)
    return int(mac_str[:6], 16)


# https://maclookup.app/downloads/json-database
def convert_json(json_path: Path):
    mac_entries = json.load(open(json_path))
    if _DB_PATH.exists():
        os.remove(_DB_PATH)

    conn = sqlite3.connect(_DB_PATH)
    cursor = conn.cursor()

    try:
        cursor.executescript(_SCHEMA_SQL)
        conn.commit()
        rows = [(get_oui_integer(v['macPrefix']), v['vendorName'])
                for v in mac_entries]
        cursor.executemany("INSERT INTO mac_oui_info VALUES(?,?)", rows)
        conn.commit()
        print(f"Database '{_DB_PATH}' created successfully.")
    except sqlite3.Error as e:
        print(f"An error occurred while creating the database: {e}")
    finally:
        conn.close()


def get_vendor_name(mac_str: str) -> str:
    oui_integer = get_oui_integer(mac_str)
    if not _DB_PATH.exists():
        raise RuntimeError('OUI DB not found.')

    with sqlite3.connect(_DB_PATH) as conn:
        cursor = conn.execute(
            'SELECT vendor FROM mac_oui_info WHERE mac_oui=? LIMIT 1', (oui_integer,))
        result = cursor.fetchone()
        if result is None:
            return f'UNKNOWN({strip_separator(mac_str)[:6].upper()})'
        else:
            return result[0]


if __name__ == '__main__':
    # convert_json(Path(sys.argv[1]))
    print(get_vendor_name(sys.argv[1]))
