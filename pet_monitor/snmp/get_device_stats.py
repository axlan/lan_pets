# http://www.tcpipguide.com/free/t_SNMPVersion1SNMPv1MessageFormat.htm
# all data fields in an SNMP message must be a valid ASN.1 data type, and encoded according to the BER.
# https://www.ranecommercial.com/legacy/note161.html
# https://www.oss.com/asn1/resources/asn1-made-simple/asn1-quick-reference/octetstring.html

import socket
from typing import Any, Optional

from pyasn1.codec.ber import encoder, decoder
from pysnmp.proto import api


def _send_packet_get_response(host: str, send_data: bytes) -> Optional[bytes]:
    # Create a UDP socket
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

    # Bind the socket to the client address
    sock.bind(("0.0.0.0", 1161))

    try:
        # Send the message
        sock.sendto(send_data, (host, 161))

        # Wait for a response (with a timeout)
        sock.settimeout(1)  # Set a 1-second timeout
        data, addr = sock.recvfrom(1024)
        return data

    except socket.timeout:
        print("No response received")

    finally:
        # Close the socket
        sock.close()

    return None


def send_requests(host: str, community: str, oids: list[str], use_get_next = False) -> dict[str, Any]:
    results = {} if use_get_next else {oid: None for oid in oids}

    # Protocol version to use
    pMod = api.PROTOCOL_MODULES[api.SNMP_VERSION_1]
    # pMod = api.protoModules[api.protoVersion2c]

    # Build PDU
    reqPDU = pMod.GetNextRequestPDU() if use_get_next else pMod.GetRequestPDU()
    pMod.apiPDU.set_defaults(reqPDU)
    pMod.apiPDU.set_varbinds(
        reqPDU, tuple((oid, pMod.Null('')) for oid in oids)
    )

    # Build message
    reqMsg = pMod.Message()
    pMod.apiMessage.set_defaults(reqMsg)
    pMod.apiMessage.set_community(reqMsg, community)
    pMod.apiMessage.set_pdu(reqMsg, reqPDU)

    resp_data = _send_packet_get_response(host, encoder.encode(reqMsg))

    if resp_data is not None:    
        rspMsg, wholeMsg = decoder.decode(resp_data, asn1Spec=pMod.Message())
        rspPDU = pMod.apiMessage.get_pdu(rspMsg)
        # print(rspMsg)

        # Check for SNMP errors reported
        errorStatus = pMod.apiPDU.get_error_status(rspPDU)
        if errorStatus:
            print(errorStatus.prettyPrint())
        else:
            for oid, val in pMod.apiPDU.get_varbinds(rspPDU):
                # print('%s = %s' % (oid.prettyPrint(), val.prettyPrint()))
                results[str(oid)] = val

    return results


def walk_tree(host: str, community: str, root_oid: str) -> dict[str, Any]:
    last_oid = root_oid
    results = {}
    done = False
    while not done:
        result = send_requests(host, community, [last_oid], use_get_next=True)
        if len(result) == 0:
            break

        for oid, val in result.items():
            if not oid.startswith(root_oid):
                done = True
            else:
                results[oid] = val
                last_oid = oid
            break

    return results


def get_load_averages(host: str, community: str) -> tuple[float, float, float]:
    indexes = range(1, 4)
    # The 1,5 and 15 minute load averages DisplayString (one per row).
    base_oid = '1.3.6.1.4.1.2021.10.1.3.'

    response = send_requests(sys.argv[1], sys.argv[2], [base_oid + str(i) for i in indexes])
    # print(response)
    results: list[float] = []
    for i in indexes:
        oid = base_oid + str(i)
        value = response.get(oid)
        if value is None:
            results.append(float('NaN'))
        else:
            results.append(float(value))
    return tuple(results) # type: ignore


def get_attached_ips(host: str, community: str) -> list[tuple[str, str]]:
    # # RFC1213-MIB Network Management
    # base_oid = '1.3.6.1.2.1.4'

    # RFC1213-MIB::ipNetToMediaPhysAddress
    base_oid = '1.3.6.1.2.1.4.22.1.2'

    results = walk_tree(host, community, base_oid)
    return [
        (
            '.'.join(oid.split('.')[11:]),
            '-'.join([f'{x:02X}' for x in bytes(mac_data)])
         ) for  oid, mac_data in results.items()
    ]


def get_cpu_idle_percent(host: str, community: str) -> int:
    # UCD-SNMP-MIB::ssCpuIdle
    base_oid = '1.3.6.1.4.1.2021.11.11.0'
    response = send_requests(sys.argv[1], sys.argv[2], [base_oid])
    # print(response)
    value = response.get(base_oid)
    if value is None:
        return -1
    else:
        return int(value)


if __name__ == '__main__':
    import sys

    print(get_cpu_idle_percent(sys.argv[1], sys.argv[2]))

    print(get_attached_ips(sys.argv[1], sys.argv[2]))

    # import time
    # while True:
    #     one_min_load, five_min_load, fifteen_min_load = get_load_averages(sys.argv[1], sys.argv[2])
    #     print(f' 1: {one_min_load}')
    #     print(f' 5: {five_min_load}')
    #     print(f'15: {fifteen_min_load}\n')
    #     time.sleep(10)
