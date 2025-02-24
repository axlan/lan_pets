# http://www.tcpipguide.com/free/t_SNMPVersion1SNMPv1MessageFormat.htm
# all data fields in an SNMP message must be a valid ASN.1 data type, and encoded according to the BER.
# https://www.ranecommercial.com/legacy/note161.html
# https://www.oss.com/asn1/resources/asn1-made-simple/asn1-quick-reference/octetstring.html

import socket
from typing import Any, Optional

from pyasn1.codec.ber import decoder, encoder
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
    except (socket.timeout, socket.gaierror):
        pass

    finally:
        # Close the socket
        sock.close()

    return None


def send_requests(host: str, community: str, oids: list[str], use_get_next=False) -> dict[str, Any]:
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
            # print(errorStatus.prettyPrint())
            pass
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
    return tuple(results)  # type: ignore


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
        ) for oid, mac_data in results.items()
    ]


def get_cpu_idle_percent(host: str, community: str) -> Optional[int]:
    # UCD-SNMP-MIB::ssCpuIdle
    base_oid = '1.3.6.1.4.1.2021.11.11.0'
    response = send_requests(host, community, [base_oid])
    # print(response)
    value = response.get(base_oid)
    if value is None:
        return None
    else:
        return int(value)


def get_per_cpu_usage(host: str, community: str) -> list[int]:
    # HOST-RESOURCES-MIB::hrStorageTable
    BASE_OID = '1.3.6.1.2.1.25.3.3.1.2'
    results = walk_tree(host, community, BASE_OID)
    return [int(d) for d in results.values()]


def get_total_cpu_usage(host: str, community: str) -> Optional[float]:
    cpu_loads = get_per_cpu_usage(host, community)
    if len(cpu_loads) > 0:
        return float(sum(cpu_loads)) / float(len(cpu_loads))
    else:
        return None


def get_ram_info(host: str, community: str) -> Optional[tuple[int, int]]:
    # HOST-RESOURCES-MIB::hrStorageTable
    BASE_OID = '1.3.6.1.2.1.25.2.3.1'
    RESOURCE_TYPE_OID = BASE_OID + '.2'
    results = walk_tree(host, community, RESOURCE_TYPE_OID)
    for oid, data in results.items():
        type_oid = str(data)
        # https://mibs.observium.org/mib/HOST-RESOURCES-TYPES/
        RAM_RESOURCE_TYPE = '1.3.6.1.2.1.25.2.1.2'
        if type_oid == RAM_RESOURCE_TYPE:
            idx = int(oid.split('.')[-1])
            ALLOCATION_UNITS_OID = BASE_OID + f'.4.{idx}'
            STORAGE_SIZE_OID = BASE_OID + f'.5.{idx}'
            STORAGE_USED_OID = BASE_OID + f'.6.{idx}'

            response = send_requests(host, community, [ALLOCATION_UNITS_OID, STORAGE_SIZE_OID, STORAGE_USED_OID])
            unit_size = int(response[ALLOCATION_UNITS_OID])
            total = int(response[STORAGE_SIZE_OID]) * unit_size
            used = int(response[STORAGE_USED_OID]) * unit_size
            return (used, total)

    return None


def get_ram_used_percent(host: str, community: str) -> Optional[float]:
    # HOST-RESOURCES-MIB::hrStorageTable
    ram_info = get_ram_info(host, community)
    if ram_info is None:
        return None
    else:
        return float(ram_info[0]) / float(ram_info[1]) * 100.0


def get_max_if_in_out_bytes(host: str, community: str) -> Optional[tuple[int, int]]:
    # IF-MIB MIB .1.3.6.1.2.1.2.

    # RFC1213-MIB::ifTable
    BASE_OID = '1.3.6.1.2.1.2.2.1'
    IN_OCTETS_OID = BASE_OID + '.10'
    OUT_OCTETS_OID = BASE_OID + '.16'
    in_results = walk_tree(host, community, IN_OCTETS_OID)
    if len(in_results) == 0:
        return None
    out_results = walk_tree(host, community, OUT_OCTETS_OID)
    if len(in_results) == 0:
        return None

    def _get_max(vals) -> int:
        return max(int(m) for m in vals)

    return (_get_max(in_results.values()), _get_max(out_results.values()))


if __name__ == '__main__':
    import sys

    print(get_attached_ips(sys.argv[1], sys.argv[2]))

    print(get_cpu_idle_percent(sys.argv[1], sys.argv[2]))

    print(get_load_averages(sys.argv[1], sys.argv[2]))

    print(get_per_cpu_usage(sys.argv[1], sys.argv[2]))

    print(get_ram_info(sys.argv[1], sys.argv[2]))

    print(get_total_cpu_usage(sys.argv[1], sys.argv[2]))

    print(get_ram_used_percent(sys.argv[1], sys.argv[2]))

    print(get_max_if_in_out_bytes(sys.argv[1], sys.argv[2]))

    # import time
    # while True:
    #     one_min_load, five_min_load, fifteen_min_load = get_load_averages(sys.argv[1], sys.argv[2])
    #     print(f' 1: {one_min_load}')
    #     print(f' 5: {five_min_load}')
    #     print(f'15: {fifteen_min_load}\n')
    #     time.sleep(10)
