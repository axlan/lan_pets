import requests

import urllib.parse

from Crypto.PublicKey import RSA
from custom_rsa import new


class TPLinkInterface:
    COMMON_HEADERS = {
        "accept": "application/json, text/javascript, */*; q=0.01",
        "content-type": "application/x-www-form-urlencoded; charset=UTF-8",
        "x-requested-with": "XMLHttpRequest",
    }

    def __init__(self, address: str, username: str, password: str) -> None:
        self.address = address
        self.username = username
        self.password = password
        self.session = requests.Session()
        self.stok = None

    def _send_post_request(self, path, data, referer='webpages/index.html') -> requests.Response:
        payload = f'data={urllib.parse.quote(data)}'
        headers = dict(TPLinkInterface.COMMON_HEADERS)
        headers["Referer"] = f"http://{self.address}/{referer}"
        return self.session.post(f'http://{self.address}/{path}', data=payload, headers=headers)

    def _get_auth(self):
        # Get RSA public key for encrypting password to send.
        resp = self._send_post_request(
            'cgi-bin/luci/;stok=/login?form=login', '{"method":"get"}', 'webpages/login.html').json()
        # { "id":1, "result":{ "username":"", "password":[
        # "D1E79FF135D14E342D76185C23024E6DEAD4D6EC2C317A526C811E83538EA4E5ED8E1B0EEE5CE26E3C1B6A5F1FE11FA804F28B7E8821CA90AFA5B2F300DF99FDA27C9D2131E031EA11463C47944C05005EF4C1CE932D7F4A87C7563581D9F27F0C305023FCE94997EC7D790696E784357ED803A610EBB71B12A8BE5936429BFD",
        # "010001" ] }, "error_code":"0" }
        if 'error_code' not in resp or resp['error_code'] != "0":
            raise RuntimeError(
                f'Error getting password encryption parameters: "{resp}"')

        N = int(resp['result']['password'][0], 16)
        E = int(resp['result']['password'][1], 16)

        pubKey = RSA.construct((N, E))
        encryptor = new(pubKey)
        encrypted = encryptor.encrypt(self.password.encode('ascii'))

        # Get the auth token and cookie.
        data = f'{{"method":"login","params":{{"username":"admin","password":"{encrypted.hex()}"}}}}'
        resp = self._send_post_request(
            'cgi-bin/luci/;stok=/login?form=login', data, 'webpages/login.html').json()
        # { "id":1, "result":{ "stok":"09d6caa8c3c71a9171e3f85ff1d0a85e" }, "error_code":"0" }
        # <RequestsCookieJar[<Cookie sysauth=6242d6a547a07bac57adfd7397ff3da2 for 192.168.1.1/cgi-bin/luci>]>
        if 'error_code' not in resp or resp['error_code'] != "0":
            raise RuntimeError(f'Authentication failed: "{resp}"')
        print('Authentication suceeded')
        self.stok = resp['result']['stok']

    def _api_query(self, admin_path, data='{"method":"get","params":{}}'):
        if self.stok is None:
            self._get_auth()
        resp = self._send_post_request(
            f'cgi-bin/luci/;stok={self.stok}/admin/{admin_path}', data).json()
        if 'error_code' not in resp or resp['error_code'] != "0":
            raise RuntimeError(f'Authentication failed: "{resp}"')
        return resp['result']

    def get_dhcp_clients(self):
        return self._api_query('dhcps?form=client')
        # { "id":1, "result":[ { "leasetime":"1:40:9", "name":"A-PC",
        # "macaddr":"F4-6D-04-96-3D-ED", "ipaddr":"192.168.1.138",
        # "interface":"lan" }, ... ], "error_code":"0" }

    def get_dhcp_static_reservations(self):
        return self._api_query('dhcps?form=reservation', '{"method":"get","params":{}}')
        # { "id":1, "others":{ "max_rules":1024 }, "result":[ {
        # "mac":"1C-3B-F3-48-EF-18", "note":"tplink_nursery", "bind":"1",
        # "enable":"on", "ip":"192.168.1.3", "interface":"LAN1" }, ... ],
        # "error_code":"0" }

    def get_cpu_usage(self):
        return self._api_query('sys_status?form=all_usage')
        # { "id":1, "result":{ "cpu_log":{ "core1":[ ... ], "core3":[ ... ],
        # "core2":[ ... ], "core4":[ ... ] }, "mem_usage":{ "mem":29 },
        # "cpu_usage":{ "core1":12, "core3":7, "core2":7, "core4":11 } },
        # "error_code":"0" }

    def get_interface_status(self):
        return self._api_query('interface?form=status2')
        # { "id":1, "result":{ "normal":[ { "t_proto":"static",
        # "ipaddr":"192.168.1.1", "t_type":"physical", "t_linktype":"static",
        # "macaddr":"F0-A7-31-62-D8-D0", "t_label":"LAN", "t_isup":true,
        # "netmask":"255.255.255.0", "t_name":"LAN1" }, { "t_proto":"dhcp",
        # "ipaddr":"125.110.11.241", "dns2":"50.0.2.2", "t_type":"physical",
        # "macaddr":"F0-A7-31-62-D8-D1", "t_linktype":"dhcp", "dns1":"50.0.1.1",
        # "t_label":"WAN", "netmask":"255.255.252.0", "gateway":"135.180.40.1",
        # "t_name":"WAN1", "t_isup":true, "second_conn":false } ], "vpn":{  } },
        # "error_code":"0" }

    def get_traffic_stats(self):
        # { "id":1, "result":{ "status":"on", "mask":"255.255.255.0", "ip":"192.168.1.0" }, "error_code":"0" }
        return self._api_query('ipstats?form=list', '{"method":"get","params":{}}')
        # { "id":1, "result":[ { "rx_bytes":318869, "tx_bytes":146051,
        # "addr":"192.168.1.139", "tx_pps":0, "tx_bps":0, "rx_bps":0,
        # "rx_pkts":878, "tx_pkts":944, "rx_pps":0 }, ...} ],
        # "error_code":"0" }

if __name__ == '__main__':
    import sys
    tplink = TPLinkInterface('192.168.1.1', 'admin', sys.argv[1])
    print(tplink.get_dhcp_clients())
    print(tplink.get_cpu_usage())
    print(tplink.get_interface_status())
    print(tplink.get_dhcp_static_reservations())
    print(tplink.get_traffic_stats())
