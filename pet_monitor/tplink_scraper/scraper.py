from collections import defaultdict
import sqlite3
import os
from pathlib import Path
import urllib.parse
import time
from typing import NamedTuple, Optional


from pet_monitor.constants import DATA_DIR
from pet_monitor.settings import TPLinkSettings, get_settings, RateLimiter
from pet_monitor.tplink_scraper.tplink_interface import TPLinkInterface


SCRIPT_PATH = Path(__file__).parent.resolve()


class ClientInfo(NamedTuple):
    mac: str
    is_reserved: int = 0
    ip: Optional[str] = None
    client_name: Optional[str] = None
    description: Optional[str] = None


SCHEMA_SQL = '''\
CREATE TABLE client_info (
    mac VARCHAR(17) NOT NULL,               -- MAC address (format: XX-XX-XX-XX-XX-XX)
    is_reserved BOOLEAN DEFAULT FALSE,      -- Does device have static IP
    ip VARCHAR(15),                         -- IP address (format: IPv4). NULL if not available.
    client_name VARCHAR(255),               -- Name of the client
    description VARCHAR(255),               -- Additional information about the client
    UNIQUE (mac)                            -- Ensure MAC addresses are unique
);

CREATE TABLE client_traffic (
    client_id INT,                 -- Index of client_info table entry
    is_connected BOOLEAN,          -- Does device have static IP
    rx_bytes INT,                  -- Bytes received since monitor reset
    tx_bytes INT,                  -- Bytes sent since monitor
    timestamp INTEGER DEFAULT (strftime('%s', 'now')), -- Unix time of observation
    FOREIGN KEY(client_id) REFERENCES client_info(rowid)
);
'''


def create_database_from_schema(db_path):
    """Create a new SQLite database from a schema file if it doesn't exist."""
    print(f"Database '{db_path}' does not exist. Creating from schema file...")
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    try:
        cursor.executescript(SCHEMA_SQL)
        conn.commit()
        print(f"Database '{db_path}' created successfully.")
    except sqlite3.Error as e:
        print(f"An error occurred while creating the database: {e}")
    finally:
        conn.close()


class TPLinkScraper():
    def __init__(self, settings: TPLinkSettings) -> None:
        self.settings = settings
        self.rate_limiter = RateLimiter(settings.update_period_sec)
        self.db_path = DATA_DIR / 'tp_clients.sqlite3'

        if not os.path.exists(self.db_path):
            create_database_from_schema(self.db_path)

    def load_ips(self, mac_addresses:list[str]) -> list[tuple[str, str]]:
        with sqlite3.connect(self.db_path) as conn:
            cur = conn.cursor()
            place_holders = ', '.join(['?'] * len(mac_addresses))
            QUERY = f"SELECT mac, ip FROM client_info WHERE mac IN ({place_holders})"
            cur.execute(QUERY, tuple(m for m in mac_addresses))
            return [record for record in cur.fetchall()]

    def update(self) -> bool:
        if not self.rate_limiter.get_ready():
            return True

        try:
            tplink = TPLinkInterface(
                self.settings.router_ip, self.settings.username, self.settings.password)
            clients = tplink.get_dhcp_clients()
            reservations = tplink.get_dhcp_static_reservations()
            traffic = tplink.get_traffic_stats()
        except Exception as e:
            print(e)
            return False

        with sqlite3.connect(self.db_path) as conn:
            devices = defaultdict(dict)
            ip_map = {}
            for entry in reservations:
                mac = entry['mac']
                devices[mac]['description'] = urllib.parse.unquote(
                    entry['note'])
                devices[mac]['ip'] = entry['ip']
                devices[mac]['is_reserved'] = 1
                ip_map[entry['ip']] = mac
            for entry in clients:
                mac = entry['macaddr']
                if entry['name'] != '--':
                    devices[mac]['client_name'] = entry['name']
                devices[mac]['ip'] = entry['ipaddr']
                ip_map[entry['ipaddr']] = mac

            cur = conn.cursor()
            cur.execute("SELECT rowid, * FROM client_info")
            num_updated = 0
            num_added = 0
            num_total = 0
            num_traffic = 0
            num_connected = 0
            for record in cur.fetchall():
                rowid = record[0]
                db_client = ClientInfo(*record[1:])
                if db_client.mac in devices:
                    device = devices.pop(db_client.mac)
                    client = ClientInfo(db_client.mac, **device)
                    if client == db_client:
                        continue
                    else:
                        cur.execute(
                            'UPDATE client_info SET is_reserved=?, ip=?, client_name=?, description=? WHERE rowid=?', client[1:] + (rowid,))
                        num_updated += 1
                elif db_client.ip is not None:
                    cur.execute(
                        'UPDATE client_info SET is_reserved=0, ip=NULL WHERE rowid=?', (rowid,))
                    num_updated += 1

            for mac, device in devices.items():
                client = ClientInfo(mac, **device)
                cur.execute(
                    'INSERT INTO client_info VALUES (?, ?, ?, ?, ?)', client)
                num_added += 1
            conn.commit()

            cur.execute("SELECT rowid, ip FROM client_info")
            for record in cur.fetchall():
                rowid, ip = record
                found = False
                num_total += 1
                if ip is not None:
                    for device in traffic:
                        if device['addr'] == ip:
                            found = True
                            cur.execute('INSERT INTO client_traffic (client_id, is_connected, rx_bytes, tx_bytes) VALUES (?, 1, ?, ?)',
                                        (rowid, device['rx_bytes'], device['tx_bytes']))
                            num_traffic += 1
                            break
                    if not found:
                        cur.execute(
                            'INSERT INTO client_traffic (client_id, is_connected) VALUES (?, 1)', (rowid,))
                    num_connected += 1
                else:
                    cur.execute(
                        'INSERT INTO client_traffic (client_id, is_connected) VALUES (?, 0)', (rowid,))
            conn.commit()
            print(f'num_updated: {num_updated}')
            print(f'num_added: {num_added}')
            print(f'num_traffic: {num_traffic}')
            print(f'num_connected: {num_connected}')
            print(f'num_total: {num_total}')
            return True


def main():
    settings = get_settings().tplink_settings
    if settings is None:
        print("TPLink settings not found.")
        return
    scraper = TPLinkScraper(settings)

    try:
        while True:
            scraper.update()
            time.sleep(1)
    except KeyboardInterrupt:
        pass


if __name__ == '__main__':
    main()
