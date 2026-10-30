import json
import os
from pathlib import Path
import sqlite3

import pytest

from conftest import destination, inventory_item, item, snapshot
from snapshots import current_holdings, decode_item_id, initialize_schema


def containers_by_name(client):
    return {c["name"]: c for c in client.get("/api/holdings").json()["containers"]}


def test_decode_item_id_splits_enhancement_from_high_byte():
    assert decode_item_id(44195) == (44195, 0)
    assert decode_item_id(33566072) == (11640, 2)  # +2 Asula's Crimson Eye Necklace
    assert decode_item_id(336239502) == (695182, 20)  # PEN Tuvala Enlightened Blade


def test_import_storage_and_inventory_with_names(client):
    data = snapshot(
        inventory_items=[
            inventory_item(752021, 13, "0x01", 11, "Enhancement Inventory"),
            inventory_item(336239502, 1, "0x02", 0, "Main Inventory"),
        ],
        currencies=[item(1, 5_000_000, "0x03", container_code=0, container_name="Global Currencies",
                         currency_name="Silver")],
        destinations=[destination(202, "Altinova", [item(33566072, 1, "0x04"), item(44195, 7, "0x05")])],
    )

    response = client.post("/api/snapshots", json=data)

    assert response.status_code == 201
    summary = response.json()
    assert summary["character"] == "Мій персонаж"
    assert (summary["inventory_stacks"], summary["currency_balances"], summary["storage_stacks"]) == (2, 1, 2)
    assert summary["missing_names"] == 0

    containers = containers_by_name(client)
    assert containers["Altinova"]["kind"] == "storage"
    assert containers["Altinova"]["character"] is None
    assert containers["Main Inventory"]["character"] == "Мій персонаж"
    blade = containers["Main Inventory"]["items"][0]
    assert (blade["name"], blade["enhancement"], blade["grade"]) == ("Tuvala Enlightened Blade", 20, 3)
    assert containers["Global Currencies"]["items"][0]["quantity"] == 5_000_000


def test_duplicate_snapshot_is_rejected(client):
    data = snapshot(destinations=[destination(202, "Altinova", [item(44195, 7, "0x05")])])

    assert client.post("/api/snapshots", json=data).status_code == 201
    assert client.post("/api/snapshots", json=data).status_code == 409
    assert len(client.get("/api/snapshots").json()) == 1


def test_unsupported_schema_is_rejected(client):
    response = client.post("/api/snapshots", json={**snapshot(), "schema_version": 4})

    assert response.status_code == 422
    assert client.get("/api/snapshots").json() == []


def test_character_switch_snapshot_keeps_previous_storage(client):
    login = snapshot(destinations=[destination(202, "Altinova", [item(44195, 7, "0x05")])])
    switch = snapshot(inventory_items=[inventory_item(752021, 13, "0x01", 11, "Enhancement Inventory")])

    client.post("/api/snapshots", json=login)
    client.post("/api/snapshots", json=switch)

    containers = containers_by_name(client)
    assert containers["Altinova"]["items"][0]["quantity"] == 7
    assert containers["Enhancement Inventory"]["items"][0]["quantity"] == 13


def test_empty_inventory_hydration_does_not_wipe_inventory(client):
    # Так виглядав знімок, коли Enter натиснули до кінця завантаження.
    filled = snapshot(inventory_items=[inventory_item(752021, 13, "0x01", 11, "Enhancement Inventory")])
    early_enter = snapshot(destinations=[destination(202, "Altinova", [item(44195, 7, "0x05")])])

    client.post("/api/snapshots", json=filled)
    client.post("/api/snapshots", json=early_enter)

    assert containers_by_name(client)["Enhancement Inventory"]["items"][0]["quantity"] == 13


def test_enhancement_inventory_is_shared_by_family(client):
    first = snapshot(inventory_items=[
        inventory_item(752021, 13, "0x01", 11, "Enhancement Inventory"),
        inventory_item(44195, 3, "0x02", 0, "Main Inventory"),
    ])
    second = snapshot(inventory_items=[
        inventory_item(752021, 15, "0x01", 11, "Enhancement Inventory"),
        inventory_item(44195, 4, "0x02", 0, "Main Inventory"),
    ])

    client.post("/api/snapshots?character=Mirel", json=first)
    client.post("/api/snapshots?character=Sefir", json=second)

    containers = client.get("/api/holdings").json()["containers"]
    enhancement = [c for c in containers if c["name"] == "Enhancement Inventory"]
    assert len(enhancement) == 1
    assert enhancement[0]["character"] is None
    assert enhancement[0]["items"][0]["quantity"] == 15  # найсвіжіший знімок
    main_inventories = sorted(c["character"] for c in containers if c["name"] == "Main Inventory")
    assert main_inventories == ["Mirel", "Sefir"]


def test_per_character_enhancement_inventories_are_merged():
    # Так зберігали Enhancement Inventory до того, як він став сімейним.
    connection = sqlite3.connect(":memory:")
    initialize_schema(connection)
    for snapshot_id, character, quantity in [(1, "Mirel", 13), (2, "Sefir", 15)]:
        connection.execute(
            "INSERT INTO snapshots (id, taken_at, character, schema_version, hydration_detected,"
            " identity_complete, source_sha256) VALUES (?, '2026-10-28', ?, 5, 1, 1, ?)",
            (snapshot_id, character, f"sha{snapshot_id}"),
        )
        container_id = connection.execute(
            "INSERT INTO containers (kind, game_code, name, character)"
            " VALUES ('inventory', 11, 'Enhancement Inventory', ?)",
            (character,),
        ).lastrowid
        connection.execute("INSERT INTO snapshot_containers VALUES (?, ?)", (snapshot_id, container_id))
        connection.execute(
            "INSERT INTO holdings (snapshot_id, container_id, item_id, quantity, instance)"
            " VALUES (?, ?, 752021, ?, '0x01')",
            (snapshot_id, container_id, quantity),
        )

    initialize_schema(connection)

    assert connection.execute("SELECT character FROM containers").fetchall() == [("",)]
    connection.row_factory = sqlite3.Row
    enhancement = current_holdings(connection)
    assert len(enhancement) == 1
    assert enhancement[0]["character"] is None
    assert enhancement[0]["items"][0]["quantity"] == 15


def test_newer_storage_snapshot_replaces_town_contents(client):
    older = snapshot(destinations=[
        destination(202, "Altinova", [item(44195, 7, "0x05")]),
        destination(1, "Velia", [item(44195, 2, "0x06")]),
    ])
    newer = snapshot(destinations=[
        destination(202, "Altinova", []),
        destination(1, "Velia", [], observed=False),
    ])

    client.post("/api/snapshots", json=older)
    client.post("/api/snapshots", json=newer)

    containers = containers_by_name(client)
    assert containers["Altinova"]["items"] == []  # побачений порожнім
    assert containers["Velia"]["items"][0]["quantity"] == 2  # не побачений — лишається попередній стан


def test_import_survives_arsha_outage(client, monkeypatch):
    import arsha

    def offline(item_ids, lang="en"):
        raise OSError("arsha.io недоступний")

    monkeypatch.setattr(arsha, "fetch_items", offline)
    data = snapshot(destinations=[destination(202, "Altinova", [item(44195, 7, "0x05")])])

    response = client.post("/api/snapshots", json=data)

    assert response.status_code == 201
    assert response.json()["missing_names"] == 1
    assert containers_by_name(client)["Altinova"]["items"][0]["name"] is None


REAL_SNAPSHOTS = os.environ.get("BDO_SNAPSHOTS_DIR")


@pytest.mark.skipif(not REAL_SNAPSHOTS, reason="BDO_SNAPSHOTS_DIR не задано")
def test_real_snapshots_import(client):
    # Справжні знімки акаунта лежать поза репозиторієм; тест лише перевіряє,
    # що реальний вивід bdo-toolkit імпортується без помилок.
    paths = sorted(Path(REAL_SNAPSHOTS).glob("*.json"))
    assert paths

    for path in paths:
        data = json.loads(path.read_text(encoding="utf-8"))
        assert client.post("/api/snapshots", json=data).status_code == 201

    containers = client.get("/api/holdings").json()["containers"]
    assert any(c["kind"] == "storage" and c["items"] for c in containers)
    assert any(c["kind"] == "inventory" and c["items"] for c in containers)
