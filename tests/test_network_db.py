import json

from pet_monitor.common import (
    DeviceType,
    IdentifierType,
    Mood,
    NetworkInterfaceInfo,
    PetInfo,
    Relationship,
    TrafficStats,
)
from pet_monitor.network_db import DBInterface


def test_db_init():
    conn = DBInterface(":memory:")
    assert conn


def test_db_enter():
    with DBInterface(":memory:") as conn:
        assert conn


TEST_PETS = set(PetInfo(f'pet{i}', IdentifierType.MAC, '', DeviceType.GAMES) for i in range(5))
PET_NAMES = set(p.name for p in TEST_PETS)

def test_add_pet():
    conn = DBInterface(":memory:")

    assert conn.get_specific_pet('pet1') is None

    for pet in TEST_PETS:
        conn.add_pet_info(pet)

    loaded_pets = conn.get_pet_info()

    assert loaded_pets == TEST_PETS
    assert conn.get_specific_pet('pet1') in loaded_pets


def test_add_duplicate_pet():
    conn = DBInterface(":memory:")
    test_pet = PetInfo('pet', IdentifierType.MAC, '', DeviceType.GAMES)
    conn.add_pet_info(test_pet)
    test_pet = PetInfo('pet', IdentifierType.MAC, '', DeviceType.IOT)
    conn.add_pet_info(test_pet)
    loaded_pets = conn.get_pet_info()
    assert loaded_pets == {test_pet}


def test_delete_pet():
    conn = DBInterface(":memory:")
    for pet in TEST_PETS:
        conn.add_pet_info(pet)

    loaded_pets = conn.get_pet_info()
    assert any(p.name == 'pet3' for p in loaded_pets)

    conn.delete_pet_info('pet3')
    loaded_pets = conn.get_pet_info()
    assert not any(p.name == 'pet3' for p in loaded_pets)

    conn.add_pet_info(PetInfo('pet3', IdentifierType.MAC, '', DeviceType.GAMES))
    loaded_pets = conn.get_pet_info()
    assert loaded_pets == TEST_PETS

def test_set_mood():
    NAME = 'pet1'
    conn = DBInterface(":memory:")

    conn.add_pet_info(PetInfo(NAME, IdentifierType.MAC, '', DeviceType.GAMES, mood=Mood.JOLLY))
    assert next(iter(conn.get_pet_info())).mood == Mood.JOLLY
    conn.update_pet_mood(NAME, Mood.SHY)
    assert next(iter(conn.get_pet_info())).mood == Mood.SHY


TEST_INTERFACES = set(NetworkInterfaceInfo(mac=f'mac{i}', ip=f'ip{i}', dns_hostname=f'dns{i}', description_json=json.dumps({'a':str(i)})) for i in range(3))


def test_add_interface():
    conn = DBInterface(":memory:")
    for interface in TEST_INTERFACES:
        conn.add_network_info(interface)

    loaded_interfaces = conn.get_network_info()
    assert loaded_interfaces == TEST_INTERFACES


def test_duplicate_interface():
    conn = DBInterface(":memory:")
    for interface in TEST_INTERFACES:
        conn.add_network_info(interface)

    conn.add_network_info(interface)

    loaded_interfaces = conn.get_network_info()
    assert loaded_interfaces == TEST_INTERFACES


def test_overlapped_interface():
    conn = DBInterface(":memory:")
    for interface in TEST_INTERFACES:
        conn.add_network_info(interface)

    overlapped_interface = NetworkInterfaceInfo(mac='mac0', ip='ip1', dns_hostname='dns2', description_json='{"b": "3"}')

    conn.add_network_info(overlapped_interface)

    loaded_interfaces = conn.get_network_info()

    EXPECTED_INTERFACES = {
        NetworkInterfaceInfo(mac='mac0', ip='ip1', dns_hostname='dns2', description_json='{"a": "2", "b": "3"}'),
        NetworkInterfaceInfo(ip='ip0', dns_hostname='dns0', description_json='{"a": "0"}'),
        NetworkInterfaceInfo(mac='mac1', dns_hostname='dns1', description_json='{"a": "1"}'),
    }

    assert loaded_interfaces == EXPECTED_INTERFACES


def test_delete_overlapped_interface():
    conn = DBInterface(":memory:")
    TEST_INTERFACES2 = {
        NetworkInterfaceInfo(mac='mac0', description_json='{"a": "0"}'),
        NetworkInterfaceInfo(ip='ip1', description_json='{"a": "1"}'),
    }
    for interface in TEST_INTERFACES2:
        conn.add_network_info(interface)

    overlapped_interface = NetworkInterfaceInfo(mac='mac0', ip='ip1', dns_hostname='dns2', description_json='{"b": "3"}')

    conn.add_network_info(overlapped_interface)

    loaded_interfaces = conn.get_network_info()

    EXPECTED_INTERFACES = {
        NetworkInterfaceInfo(mac='mac0', ip='ip1', dns_hostname='dns2', description_json='{"a": "0", "b": "3"}'),
    }

    assert loaded_interfaces == EXPECTED_INTERFACES


def test_insert_invalid_pet_stats():
    conn = DBInterface(":memory:")
    NAME = 'pet1'
    
    conn.add_traffic_for_pet(NAME, 0, 0, 0)

    traffic_df = conn._load_traffic_df(PET_NAMES, 0)

    assert len(traffic_df) == 0


def test_insert_stats():
    conn = DBInterface(":memory:")
    NAME = 'pet1'

    bps_df = conn.load_bps(PET_NAMES, 0)
    assert len(bps_df) == len(PET_NAMES)
    assert len(bps_df[NAME]) == 0
    mean_stats = conn.get_mean_traffic(bps_df)
    assert len(mean_stats) == len(PET_NAMES)
    assert mean_stats[NAME] == TrafficStats() 

    for pet in TEST_PETS:
        conn.add_pet_info(pet)

    conn.add_traffic_for_pet(NAME, 0, 0, 0)
    bps_df = conn.load_bps(PET_NAMES, 0)
    assert len(bps_df) == len(PET_NAMES)
    assert len(bps_df[NAME]) == 1
    mean_stats = conn.get_mean_traffic(bps_df)
    assert len(mean_stats) == len(PET_NAMES)
    assert mean_stats[NAME] == TrafficStats()

    conn.add_traffic_for_pet(NAME, 100, 200, 1)
    traffic_df = conn._load_traffic_df(PET_NAMES, 0)
    assert len(traffic_df) == 2
    assert len(traffic_df[traffic_df['name'] == NAME]) == 2
    assert traffic_df.iloc[1].tx_bytes == 200

    bps_df = conn.load_bps(PET_NAMES, 0)
    assert len(bps_df) == len(PET_NAMES)
    assert len(bps_df[NAME]) == 2
    assert bps_df[NAME].iloc[1].rx_bytes_bps == 100.0
    mean_stats = conn.get_mean_traffic(bps_df)
    assert len(mean_stats) == len(PET_NAMES)
    assert mean_stats[NAME] == TrafficStats(100, 200, 1, 100, 200)


def test_insert_invalid_availability():
    conn = DBInterface(":memory:")

    availability = conn.load_availability(PET_NAMES)
    assert len(availability) == 0

    availability_mean = conn.load_availability_mean(PET_NAMES)
    assert availability_mean == {n: 0.0 for n in PET_NAMES}

    current_availability = conn.load_current_availability(PET_NAMES)
    assert current_availability == {n: False for n in PET_NAMES}

    last_seen = conn.load_last_seen(PET_NAMES)
    assert last_seen == {n: 0 for n in PET_NAMES}

    history_lens = conn.get_history_len(PET_NAMES)
    assert history_lens == {n: 0 for n in PET_NAMES}


def test_availability():
    conn = DBInterface(":memory:")
    NAME = 'pet1'

    for pet in TEST_PETS:
        conn.add_pet_info(pet)

    conn.add_pet_availability(NAME, False, 1)
    conn.add_pet_availability(NAME, True, 2)

    availability = conn.load_availability(PET_NAMES)
    assert len(availability) == 2

    availability_mean = conn.load_availability_mean(PET_NAMES)
    EXPECTED = {n: 0.0 for n in PET_NAMES}
    EXPECTED[NAME] = 50.
    assert availability_mean == EXPECTED

    current_availability = conn.load_current_availability(PET_NAMES)
    EXPECTED = {n: False for n in PET_NAMES}
    EXPECTED[NAME] = True
    assert current_availability == EXPECTED

    last_seen = conn.load_last_seen(PET_NAMES)
    EXPECTED = {n: 0 for n in PET_NAMES}
    EXPECTED[NAME] = 2
    assert last_seen == EXPECTED

    history_lens = conn.get_history_len(PET_NAMES)
    EXPECTED = {n: 0 for n in PET_NAMES}
    EXPECTED[NAME] = 1
    assert history_lens == EXPECTED


def test_relationships():
    conn = DBInterface(":memory:")
    NAMES = ('pet1', 'pet2', 'pet3', 'pet4')

    for pet in TEST_PETS:
        conn.add_pet_info(pet)

    conn.add_relationship(NAMES[0], NAMES[1], Relationship.FRIENDS)
    conn.add_relationship(NAMES[0], NAMES[2], Relationship.FRIENDS)

    relationships = conn.get_all_relationships()
    assert relationships == {
        (NAMES[0], NAMES[1], Relationship.FRIENDS),
        (NAMES[0], NAMES[2], Relationship.FRIENDS),
    }

    relationship_map = conn.get_relationship_map(PET_NAMES)

    assert relationship_map.get_relationship(NAMES[2], NAMES[0]) == Relationship.FRIENDS
    assert relationship_map.get_relationship(NAMES[0], NAMES[3]) is None
    assert relationship_map.get_relationships(NAMES[0]) == {
        NAMES[1]: Relationship.FRIENDS,
        NAMES[2]: Relationship.FRIENDS,
    }
    assert relationship_map.get_relationships(NAMES[1]) == {
        NAMES[0]: Relationship.FRIENDS,
    }

    conn.remove_relationship(NAMES[1], NAMES[0])
    relationship_map.remove(NAMES[1], NAMES[0])

    relationships = conn.get_all_relationships()
    assert relationships == {
        (NAMES[0], NAMES[2], Relationship.FRIENDS),
    }
    assert relationships == relationship_map.relationships
