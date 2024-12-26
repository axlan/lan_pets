from collections import defaultdict
import io
import sqlite3
import os
from pathlib import Path
import time
import urllib.parse
from typing import NamedTuple, Optional

import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from pet_monitor.tplink_scraper.scraper import ClientInfo, TrafficStats
from pet_monitor.settings import TPLinkSettings, RateLimiter


class TPLinkScraper():

    _INFO = [
        ClientInfo(
            mac='44-AF-28-12-11-E6',
            is_reserved=False,
            ip='192.168.1.88',
            client_name='Zephurus'
        ),
        ClientInfo(
            mac='1A-F3-51-12-36-EB',
            is_reserved=False,
            ip='192.168.1.86',
            client_name='Pixel 8'
        ),
        
    ]
    _INFO_MAP = {i.mac: i for i in _INFO}

    def __init__(self, settings: TPLinkSettings) -> None:
        self.settings = settings
        self.rate_limiter = RateLimiter(settings.update_period_sec)

    def load_ips(self, mac_addresses: list[str]) -> list[tuple[str, str]]:
        return [(i.mac, i.ip) for i in self._INFO if i.mac in mac_addresses and i.ip is not None]

    def load_info(self, mac_addresses: Optional[list[str]] = None) -> dict[str, ClientInfo]:
        if mac_addresses is None:
            return self._INFO_MAP
        else:
            return {i.mac: i for i in self._INFO if i.mac in mac_addresses}
    
    def generate_traffic_plot(self, mac_address: str, since_timestamp: Optional[float] = None, sample_rate='1h') -> bytes:
        x = np.arange(30)
        y1 = np.full((1,30), 1)
        y2 = np.full((1,30), 2)

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
        return {m:TrafficStats(0,0,0,0,0) for m in mac_addresses}

    def update(self):
        self.rate_limiter.get_ready()
