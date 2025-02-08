import json

from pet_monitor.network_db import (
    delete_pet_info,
    get_db_connection,
    PetInfo,
    IdentifierType,
    DeviceType,
    add_pet_info,
    get_pet_info,
    get_network_info,
    add_network_info,
    NetworkInterfaceInfo,
    add_traffic_for_pet,
    _load_traffic_df,
    load_bps,
    get_mean_traffic,
    TrafficStats,
    add_pet_availability,
    load_availability,
    load_availability_mean,
    load_current_availability,
    load_last_seen,
    get_history_len,
    update_pet_mood,
    Mood,
    get_relationship_map,
    get_all_relationships,
    add_relationship,
    remove_relationship,
    Relationship,
    )


def test_db_init():
    conn = get_db_connection(":memory:")
    assert conn


TEST_PETS = set(PetInfo(f'pet{i}', IdentifierType.MAC, '', DeviceType.GAMES) for i in range(5))
PET_NAMES = set(p.name for p in TEST_PETS)

def test_add_pet():
    conn = get_db_connection(":memory:")
    for pet in TEST_PETS:
        add_pet_info(conn, pet)

    loaded_pets = get_pet_info(conn)

    assert loaded_pets == TEST_PETS


def test_add_duplicate_pet():
    conn = get_db_connection(":memory:")
    test_pet = PetInfo('pet', IdentifierType.MAC, '', DeviceType.GAMES)
    add_pet_info(conn, test_pet)
    test_pet = PetInfo('pet', IdentifierType.MAC, '', DeviceType.IOT)
    add_pet_info(conn, test_pet)
    loaded_pets = get_pet_info(conn)
    assert loaded_pets == {test_pet}


def test_delete_pet():
    conn = get_db_connection(":memory:")
    for pet in TEST_PETS:
        add_pet_info(conn, pet)

    loaded_pets = get_pet_info(conn)
    assert any(p.name == 'pet3' for p in loaded_pets)

    delete_pet_info(conn, 'pet3')
    loaded_pets = get_pet_info(conn)
    assert not any(p.name == 'pet3' for p in loaded_pets)

    add_pet_info(conn, PetInfo('pet3', IdentifierType.MAC, '', DeviceType.GAMES))
    loaded_pets = get_pet_info(conn)
    assert loaded_pets == TEST_PETS

def test_set_mood():
    NAME = 'pet1'
    conn = get_db_connection(":memory:")

    add_pet_info(conn, PetInfo(NAME, IdentifierType.MAC, '', DeviceType.GAMES, mood=Mood.JOLLY))
    assert next(iter(get_pet_info(conn))).mood == Mood.JOLLY
    update_pet_mood(conn, NAME, Mood.SHY)
    assert next(iter(get_pet_info(conn))).mood == Mood.SHY


TEST_INTERFACES = set(NetworkInterfaceInfo(mac=f'mac{i}', ip=f'ip{i}', dns_hostname=f'dns{i}', description_json=json.dumps({'a':str(i)})) for i in range(3))


def test_add_interface():
    conn = get_db_connection(":memory:")
    for interface in TEST_INTERFACES:
        add_network_info(conn, interface)

    loaded_interfaces = get_network_info(conn)
    assert loaded_interfaces == TEST_INTERFACES


def test_duplicate_interface():
    conn = get_db_connection(":memory:")
    for interface in TEST_INTERFACES:
        add_network_info(conn, interface)

    add_network_info(conn, interface)

    loaded_interfaces = get_network_info(conn)
    assert loaded_interfaces == TEST_INTERFACES


def test_overlapped_interface():
    conn = get_db_connection(":memory:")
    for interface in TEST_INTERFACES:
        add_network_info(conn, interface)

    overlapped_interface = NetworkInterfaceInfo(mac='mac0', ip='ip1', dns_hostname='dns2', description_json='{"b": "3"}')

    add_network_info(conn, overlapped_interface)

    loaded_interfaces = get_network_info(conn)

    EXPECTED_INTERFACES = {
        NetworkInterfaceInfo(mac='mac0', ip='ip1', dns_hostname='dns2', description_json='{"a": "2", "b": "3"}'),
        NetworkInterfaceInfo(ip='ip0', dns_hostname='dns0', description_json='{"a": "0"}'),
        NetworkInterfaceInfo(mac='mac1', dns_hostname='dns1', description_json='{"a": "1"}'),
    }

    assert loaded_interfaces == EXPECTED_INTERFACES


def test_delete_overlapped_interface():
    conn = get_db_connection(":memory:")
    TEST_INTERFACES2 = {
        NetworkInterfaceInfo(mac='mac0', description_json='{"a": "0"}'),
        NetworkInterfaceInfo(ip='ip1', description_json='{"a": "1"}'),
    }
    for interface in TEST_INTERFACES2:
        add_network_info(conn, interface)

    overlapped_interface = NetworkInterfaceInfo(mac='mac0', ip='ip1', dns_hostname='dns2', description_json='{"b": "3"}')

    add_network_info(conn, overlapped_interface)

    loaded_interfaces = get_network_info(conn)

    EXPECTED_INTERFACES = {
        NetworkInterfaceInfo(mac='mac0', ip='ip1', dns_hostname='dns2', description_json='{"a": "0", "b": "3"}'),
    }

    assert loaded_interfaces == EXPECTED_INTERFACES


def test_insert_invalid_pet_stats():
    conn = get_db_connection(":memory:")
    NAME = 'pet1'
    
    add_traffic_for_pet(conn, NAME, 0, 0, 0)

    traffic_df = _load_traffic_df(conn, PET_NAMES, 0)

    assert len(traffic_df) == 0


def test_insert_stats():
    conn = get_db_connection(":memory:")
    NAME = 'pet1'

    bps_df = load_bps(conn, PET_NAMES, 0)
    assert len(bps_df) == len(PET_NAMES)
    assert len(bps_df[NAME]) == 0
    mean_stats = get_mean_traffic(bps_df)
    assert len(mean_stats) == len(PET_NAMES)
    assert mean_stats[NAME] == TrafficStats() 

    for pet in TEST_PETS:
        add_pet_info(conn, pet)

    add_traffic_for_pet(conn, NAME, 0, 0, 0)
    bps_df = load_bps(conn, PET_NAMES, 0)
    assert len(bps_df) == len(PET_NAMES)
    assert len(bps_df[NAME]) == 1
    mean_stats = get_mean_traffic(bps_df)
    assert len(mean_stats) == len(PET_NAMES)
    assert mean_stats[NAME] == TrafficStats()

    add_traffic_for_pet(conn, NAME, 100, 200, 1)
    traffic_df = _load_traffic_df(conn, PET_NAMES, 0)
    assert len(traffic_df) == 2
    assert len(traffic_df[traffic_df['name'] == NAME]) == 2
    assert traffic_df.iloc[1].tx_bytes == 200

    bps_df = load_bps(conn, PET_NAMES, 0)
    assert len(bps_df) == len(PET_NAMES)
    assert len(bps_df[NAME]) == 2
    assert bps_df[NAME].iloc[1].rx_bytes_bps == 100.0
    mean_stats = get_mean_traffic(bps_df)
    assert len(mean_stats) == len(PET_NAMES)
    assert mean_stats[NAME] == TrafficStats(100, 200, 1, 100, 200)


def test_insert_invalid_availability():
    conn = get_db_connection(":memory:")

    availability = load_availability(conn, PET_NAMES)
    assert len(availability) == 0

    availability_mean = load_availability_mean(conn, PET_NAMES)
    assert availability_mean == {n: 0.0 for n in PET_NAMES}

    current_availability = load_current_availability(conn, PET_NAMES)
    assert current_availability == {n: False for n in PET_NAMES}

    last_seen = load_last_seen(conn, PET_NAMES)
    assert last_seen == {n: 0 for n in PET_NAMES}

    history_lens = get_history_len(conn, PET_NAMES)
    assert history_lens == {n: 0 for n in PET_NAMES}


def test_availability():
    conn = get_db_connection(":memory:")
    NAME = 'pet1'

    for pet in TEST_PETS:
        add_pet_info(conn, pet)

    add_pet_availability(conn, NAME, False, 1)
    add_pet_availability(conn, NAME, True, 2)

    availability = load_availability(conn, PET_NAMES)
    assert len(availability) == 2

    availability_mean = load_availability_mean(conn, PET_NAMES)
    EXPECTED = {n: 0.0 for n in PET_NAMES}
    EXPECTED[NAME] = 50.
    assert availability_mean == EXPECTED

    current_availability = load_current_availability(conn, PET_NAMES)
    EXPECTED = {n: False for n in PET_NAMES}
    EXPECTED[NAME] = True
    assert current_availability == EXPECTED

    last_seen = load_last_seen(conn, PET_NAMES)
    EXPECTED = {n: 0 for n in PET_NAMES}
    EXPECTED[NAME] = 2
    assert last_seen == EXPECTED

    history_lens = get_history_len(conn, PET_NAMES)
    EXPECTED = {n: 0 for n in PET_NAMES}
    EXPECTED[NAME] = 1
    assert history_lens == EXPECTED


def test_relationships():
    conn = get_db_connection(":memory:")
    NAMES = ('pet1', 'pet2', 'pet3', 'pet4')

    for pet in TEST_PETS:
        add_pet_info(conn, pet)

    add_relationship(conn, NAMES[0], NAMES[1], Relationship.FRIENDS)
    add_relationship(conn, NAMES[0], NAMES[2], Relationship.FRIENDS)

    relationships = get_all_relationships(conn)
    assert relationships == {
        (NAMES[0], NAMES[1], Relationship.FRIENDS),
        (NAMES[0], NAMES[2], Relationship.FRIENDS),
    }

    relationship_map = get_relationship_map(conn, PET_NAMES)

    assert relationship_map.get_relationship(NAMES[2], NAMES[0]) == Relationship.FRIENDS
    assert relationship_map.get_relationship(NAMES[0], NAMES[3]) is None
    assert relationship_map.get_relationships(NAMES[0]) == {
        NAMES[1]: Relationship.FRIENDS,
        NAMES[2]: Relationship.FRIENDS,
    }
    assert relationship_map.get_relationships(NAMES[1]) == {
        NAMES[0]: Relationship.FRIENDS,
    }

    remove_relationship(conn, NAMES[1], NAMES[0])
    relationship_map.remove(NAMES[1], NAMES[0])

    relationships = get_all_relationships(conn)
    assert relationships == {
        (NAMES[0], NAMES[2], Relationship.FRIENDS),
    }
    assert relationships == relationship_map.relationships
