from collections import defaultdict
import io
import time
import urllib.parse
from typing import NamedTuple, Optional

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from pet_monitor.common import DATA_DIR, get_db_connection
from pet_monitor.settings import TPLinkSettings, get_settings, RateLimiter
from pet_monitor.tplink_scraper.tplink_interface import TPLinkInterface


class ClientInfo(NamedTuple):
    mac: str
    is_reserved: int = 0
    ip: Optional[str] = None
    client_name: Optional[str] = None
    description: Optional[str] = None


class TrafficStats(NamedTuple):
    rx_bytes: float
    tx_bytes: float
    timestamp: int
    rx_bytes_bps: float
    tx_bytes_bps: float


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


class TPLinkScraper():
    def __init__(self, settings: TPLinkSettings) -> None:
        self.settings = settings
        self.rate_limiter = RateLimiter(settings.update_period_sec)
        self.conn = get_db_connection(DATA_DIR / 'tp_clients.sqlite3', SCHEMA_SQL)

    def load_ips(self, mac_addresses: list[str]) -> list[tuple[str, str]]:
        cur = self.conn.cursor()
        place_holders = ', '.join(['?'] * len(mac_addresses))
        QUERY = f"SELECT mac, ip FROM client_info WHERE mac IN ({
            place_holders})"
        cur.execute(QUERY, tuple(m for m in mac_addresses))
        return [record for record in cur.fetchall()]

    def load_info(self, mac_addresses: Optional[list[str]] = None) -> dict[str, ClientInfo]:
        info = {}
        cur = self.conn.cursor()
        QUERY = "SELECT * FROM client_info"
        if mac_addresses is not None:
            place_holders = ', '.join(['?'] * len(mac_addresses))
            QUERY += f" WHERE mac IN ({place_holders});"
            cur.execute(QUERY, tuple(m for m in mac_addresses))
        else:
            cur.execute(QUERY+';')
        for record in cur.fetchall():
            client = ClientInfo(*record)
            info[client.mac] = client
        return info

    def _load_bps_df(self, mac_addresses: list[str], since_timestamp: Optional[float] = None) -> pd.DataFrame:
        MAC_STRS = ','.join([f'"{m}"' for m in mac_addresses])
        QUERY = f"""
        SELECT i.mac, t.rx_bytes, t.tx_bytes, t.timestamp
        FROM client_traffic t
        JOIN client_info i
        ON t.client_id = i.rowid
        WHERE i.mac in ({MAC_STRS}) AND t.is_connected = 1"""

        if since_timestamp is not None:
            QUERY += f' AND t.timestamp >= {since_timestamp}'

        QUERY += ';'

        df = pd.read_sql(QUERY, self.conn)
        df.dropna(inplace=True)
        return df

    def load_bps(self, mac_addresses: list[str], since_timestamp: Optional[float] = None) -> dict[str, pd.DataFrame]:
        results = {}
        df = self._load_bps_df(mac_addresses, since_timestamp)
        for mac in mac_addresses:
            mac_df = df[df['mac'] == mac].dropna().copy()
            mac_df.drop(columns=['mac'], inplace=True)
            durations = mac_df['timestamp'].diff()
            for col in ['rx_bytes', 'tx_bytes']:
                bps_col = f'{col}_bps'
                mac_df.loc[:, bps_col] = mac_df[col].diff()
                mac_df.loc[:, bps_col] /= durations
                mac_df.loc[mac_df.index[0], bps_col] = 0
                mac_df.loc[mac_df[bps_col] < 0, bps_col] = 0
            results[mac] = mac_df
        return results
    
    def generate_traffic_plot(self, mac_address: str, since_timestamp: Optional[float] = None, sample_rate='1h', time_zone='America/Los_Angeles') -> bytes:
        df = self.load_bps([mac_address], since_timestamp=since_timestamp)[mac_address]
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='s', utc=True).dt.tz_convert(time_zone)
        df.set_index('timestamp', inplace=True)
        df = df.resample(sample_rate).mean()
        x = df.index.values
        y1 = df['rx_bytes_bps']
        y2 = df['tx_bytes_bps']

        # Create figure with secondary y-axis
        fig = make_subplots(specs=[[{"secondary_y": True}]])

        # Add traces
        fig.add_trace(go.Scatter(x=x, y=y1, name="Recieved",  mode='markers'), secondary_y=False)
        fig.add_trace(go.Scatter(x=x, y=y2, name="Transmitted",  mode='markers'), secondary_y=True)

        # Set y-axes titles
        fig.update_yaxes(title_text="<b>Recieved Bytes/Second</b>", type="log", secondary_y=False)
        fig.update_yaxes(title_text="<b>Transmitted Bytes/Second</b>", type="log", secondary_y=True)

        fd = io.BytesIO()
        fig.write_image(fd, format='webp')
        fd.seek(0)
        return fd.read()


    def load_mean_bps(self, mac_addresses: list[str], since_timestamp: Optional[float] = None) -> dict[str, TrafficStats]:
        results = {}
        df = self._load_bps_df(mac_addresses, since_timestamp)
        for mac in mac_addresses:
            mac_df = df[df['mac'] == mac].dropna()
            metrics = {}
            metrics['timestamp'] = mac_df['timestamp'].iloc[-1]
            durations = mac_df['timestamp'].diff()
            # For metric calculation, remove periods where collection wasn't running, or device was disconnected.
            # type: ignore
            no_gaps = durations[durations < self.settings.update_period_sec * 2].index # type: ignore
            durations = durations[no_gaps]
            for col in ['rx_bytes', 'tx_bytes']:
                bps_col = f'{col}_bps'
                diffs = mac_df[col].diff()[no_gaps]
                diffs = diffs[diffs >= 0]
                metrics[bps_col] = (diffs / durations).mean()
                metrics[col] = diffs.sum()
            results[mac] = TrafficStats(**metrics)
        return results

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

        cur = self.conn.cursor()
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
        self.conn.commit()

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
        self.conn.commit()
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

    # try:
    #     while True:
    #         scraper.update()
    #         time.sleep(1)
    # except KeyboardInterrupt:
    #     pass

    print(scraper.load_mean_bps(['E2-2D-4F-4F-4F-0B', '10-E8-A7-CA-84-BB']))

    # df = scraper.load_bps(['E2-2D-4F-4F-4F-0B'])['E2-2D-4F-4F-4F-0B']
    # from plotly import express as px
    # fig = px.line(df, x='timestamp', y=['rx_bytes_bps', 'tx_bytes_bps'])
    # fig.write_image("/tmp/traffic.png")




if __name__ == '__main__':
    main()
