import json

import pytest

pytest.importorskip("bdo_toolkit.account")
from bdo_toolkit.account import (CharacterInfo, Contribution, GearItem, KnowledgeBatch, KnowledgeEntry,  # noqa: E402
                                 NodeBatch, NodeState, Servant, SkillPoints, Worker)

import main  # noqa: E402


def write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


@pytest.fixture
def extractor_output(tmp_path):
    """Вигаданий вивід bdo-data-extractor у тій самій структурі файлів."""
    out = tmp_path / "data"
    write(out / "knowledge.json", {
        "themes": [
            {"key": 10001, "name": "Ecology"},
            {"key": 10002, "name": "Beasts (Testland)", "parent": "urn::knowledge:theme:10001"},
        ],
        "entries": [
            {"key": 4150, "theme": "urn::knowledge:theme:10002", "name": "Baby Boar"},
            {"key": 4006, "theme": "urn::knowledge:theme:10002", "name": "Boar"},
        ],
    })
    write(out / "world.json", {"territories": [{"index": 1, "name": "Testland"}], "regions": [], "nodes": [
        {"key": 301, "name": "Testheim", "enabled": True, "territory": "urn::world:territory:1"},
        {"key": 135, "name": "Test Farming", "enabled": True, "territory": "urn::world:territory:1",
         "managerNode": "urn::world:node:301", "contribution": 1, "products": {"urns": ["urn::item:49706"]}},
        {"key": 9, "name": "Unused", "enabled": False},
    ]})
    write(out / "items.json", [{"id": 49706, "name": "Test Prow", "grade": 3},
                               {"id": 1, "name": "Ghost", "ghost": True, "grade": 0}])
    write(out / "locs" / "18.json", {"40022": {"14": "<PAColor0xffd0ee68>Test Chapter 11<PAOldColor>",
                                               str(1 << 24 | 14): "description"}})
    write(out / "locs" / "6.json", {"7572": {"0": "Test Goblin Worker"}, "31048": {"0": "Test Caravel"},
                                    "13": {"0": "Corsair"}})
    write(out / "locs" / "250.json", {"1501": {"0": "Lucky Guy A"}, "1503": {"0": "Lucky Guy C"},
                                      "1909": {"0": "Ore Packing"}, "1401": {"0": "Test Skill"}})
    write(out / "locs" / "251.json", {"1501": {"0": "Not a skill"}})
    return out


def save(records):
    writer = main.account.AccountWriter()
    with main.get_connection() as connection:
        writer.save(connection, records)


def test_import_extractor_output_names_everything(client, extractor_output):
    counts = client.post("/api/game-data/import", json={"path": str(extractor_output)}).json()

    assert counts == {"categories": 2, "knowledge": 2, "nodes": 2, "items": 1, "quests": 1, "characters": 3,
                      "worker_skills": 4}
    assert client.get("/api/game-data").json()["counts"] == counts

    beasts = client.get("/api/knowledge/categories?parent=10002").json()
    assert [e["name"] for e in beasts["entries"]] == ["Baby Boar", "Boar"]
    with main.get_connection() as connection:
        assert main.game_data.lookup(connection, "quest") == {"40022-14": "Test Chapter 11"}


def test_imported_names_replace_placeholders(client, extractor_output):
    save([
        CharacterInfo(1.0, 7, "Mobix", "Testfam", 13, 1, 1, 1, slot=2),
        Worker(1.0, 11, 7572, level=30, stamina=5, town_id=301, skills=(1501, 1401)),
        Servant(1.0, 31048, "Seabird", 1, 1, (GearItem(3, 49706, 1, 100, 100, 5),)),
        KnowledgeBatch(1.0, 10, (KnowledgeEntry(4150, 2),)),
    ])
    client.post("/api/game-data/import", json={"path": str(extractor_output)})

    (worker,) = client.get("/api/workers").json()
    assert (worker["type_name"], worker["town_name"]) == ("Test Goblin Worker", "Testheim")
    assert [s["name"] for s in worker["skills"]] == ["Lucky Guy A", "Test Skill"]

    (servant,) = client.get("/api/servants").json()["servants"]
    assert servant["kind_name"] == "Test Caravel"
    assert servant["gear"][0]["name"] == "Test Prow"  # з items.json, без arsha.io

    (character,) = client.get("/api/characters").json()
    assert character["class_name"] == "Corsair"


def test_single_loc_dump_is_read_when_locs_folder_is_missing(client, tmp_path):
    write(tmp_path / "loc_en.json", {"18": {"122": {"1": "Traces"}}, "6": {"2": {"0": "Ranger"}}})

    counts = client.post("/api/game-data/import", json={"path": str(tmp_path)}).json()

    assert (counts["quests"], counts["characters"], counts["worker_skills"]) == (1, 1, 0)


def test_node_names_fall_back_to_loc_when_world_json_is_missing(client, tmp_path):
    write(tmp_path / "locs" / "29.json", {"301": {"0": "Test Town", "16777216": "This is a city."}})

    counts = client.post("/api/game-data/import", json={"path": str(tmp_path)}).json()

    assert counts["nodes"] == 1


def test_folder_without_extractor_output_is_rejected(client, tmp_path):
    response = client.post("/api/game-data/import", json={"path": str(tmp_path)})

    assert response.status_code == 422
    assert "bdo-data-extractor" in response.json()["detail"]


def test_images_are_served_from_the_import_folder(client, extractor_output, tmp_path):
    client.post("/api/game-data/import", json={"path": str(extractor_output)})
    assert client.get("/api/game-data").json()["images"] == {"items": False, "knowledge": False}

    # Як після `icons` / `knowledge-icons`: файли й asset_redirects.json, без повторного імпорту.
    icon = extractor_output / "icons" / "new_icon" / "00049706.webp"
    icon.parent.mkdir(parents=True)
    icon.write_bytes(b"RIFF-item")
    card = extractor_output / "knowledge_icons" / "ui_artwork" / "ic_04150.webp"
    card.parent.mkdir(parents=True)
    card.write_bytes(b"RIFF-card")
    (tmp_path / "secret.webp").write_bytes(b"outside")
    write(extractor_output / "asset_redirects.json", {
        "urn::item:49706": "icons/new_icon/00049706.webp",
        "urn::knowledge:entry:4150": "knowledge_icons/ui_artwork/ic_04150.webp",
        "urn::knowledge:entry:4006": "../secret.webp",
    })

    assert client.get("/api/game-data").json()["images"] == {"items": True, "knowledge": True}
    item = client.get("/api/game-data/icons/item/49706")
    assert (item.status_code, item.content, item.headers["content-type"]) == (200, b"RIFF-item", "image/webp")
    assert client.get("/api/game-data/icons/knowledge/4150").content == b"RIFF-card"
    assert client.get("/api/game-data/icons/item/1").status_code == 404
    # Шлях з asset_redirects.json не виходить за межі папки імпорту.
    assert client.get("/api/game-data/icons/knowledge/4006").status_code == 404


def test_knowledge_tree_follows_the_game_book(client, tmp_path):
    write(tmp_path / "knowledge.json", {
        "themes": [
            {"key": 10020, "name": "Serendia", "parent": "urn::knowledge:theme:10001"},
            {"key": 10001, "name": "Ecology"},
            {"key": 10010, "name": "Balenos", "parent": "urn::knowledge:theme:10001"},
            {"key": 10320, "name": "Empty Bosses"},
            {"key": 10399, "name": "None"},
        ],
        "entries": [
            {"key": 2, "theme": "urn::knowledge:theme:10010", "name": "Wolf",
             "acquisition": "<PAColor0xfff3d900>Can be obtained through [Exploration]<PAOldColor>\nBalenos Forest"},
            # Старші біти — прапорці: 1 — звичайне знання, 0x100 — у книзі гри його немає.
            {"key": 1, "theme": f"urn::knowledge:theme:{1 << 16 | 10010}", "name": "Boar"},
            {"key": 3, "theme": f"urn::knowledge:theme:{0x100 << 16 | 10020}", "name": "Hidden"},
            {"key": 4, "theme": "urn::knowledge:theme:10020", "name": "Fox"},
            {"key": 5, "theme": f"urn::knowledge:theme:{0x100 << 16 | 10399}", "name": "Test A"},
            {"key": 6, "theme": f"urn::knowledge:theme:{0x100 << 16 | 10399}", "name": "Test B"},
            {"key": 7, "theme": "urn::knowledge:theme:10399", "name": "Leftover"},
        ],
    })
    counts = client.post("/api/game-data/import", json={"path": str(tmp_path)}).json()

    assert (counts["categories"], counts["knowledge"]) == (3, 3)
    roots = client.get("/api/knowledge/categories").json()["categories"]
    assert [r["name"] for r in roots] == ["Ecology"]  # порожні й службові розділи сховано
    ecology = client.get("/api/knowledge/categories?parent=10001").json()["categories"]
    assert [r["name"] for r in ecology] == ["Balenos", "Serendia"]  # за номером, не за порядком у файлі
    balenos = client.get("/api/knowledge/categories?parent=10010").json()["entries"]
    assert [e["name"] for e in balenos] == ["Wolf", "Boar"]  # порядок знань — як у файлі
    assert balenos[0]["acquisition"] == "Can be obtained through [Exploration]\nBalenos Forest"
    assert balenos[1]["acquisition"] is None


def test_contribution_skill_points_and_invested_nodes(client, extractor_output):
    save([
        Contribution(1.0, available=195, total=411, experience=3699),
        CharacterInfo(2.0, 7, "Mobix", "Testfam", 13, 1, 1, 1, slot=0),
        SkillPoints(3.0, available=183, total=1892),
        NodeBatch(1.0, (NodeState(301, True), NodeState(135, True), NodeState(9, False))),
    ])
    client.post("/api/game-data/import", json={"path": str(extractor_output)})

    assert client.get("/api/family").json()["contribution"] == {"available": 195, "total": 411, "updated_at": 1.0}
    (character,) = client.get("/api/characters").json()
    assert (character["skill_points"], character["skill_points_total"]) == (183, 1892)

    data = client.get("/api/nodes").json()
    assert data["contribution"]["available"] == 195
    farming = next(n for n in data["nodes"] if n["node_id"] == 135)
    assert farming == {"node_id": 135, "name": "Test Farming", "territory": "Testland", "manager_id": 301,
                       "manager_name": "Testheim", "contribution": 1, "products": ["Test Prow"]}
    assert [n["node_id"] for n in data["nodes"]] == [135, 301]


def test_map_places_nodes_and_npcs_for_unlearned_knowledge(client, tmp_path):
    write(tmp_path / "knowledge.json", {
        "themes": [{"key": 1, "name": "Characters"}],
        "entries": [
            {"key": 10, "theme": "urn::knowledge:theme:1", "name": "Mira", "character": "urn::character:mira",
             "acquisition": "Can be obtained through [Dialogue]\nMira"},
            {"key": 11, "theme": "urn::knowledge:theme:1", "name": "Known", "character": "urn::character:mira"},
        ],
    })
    write(tmp_path / "characters.json", [{"urn": "urn::character:mira", "entities": [{"id": 500}, {"id": 501}]}])
    write(tmp_path / "npcs.json", [
        {"id": 501, "name": "Mira", "title": "<Test Merchant>",
         "spawns": [{"regionName": "Testheim", "pos": [1000.0, 50.0, 2000.0]}]},
        {"id": 600, "name": "Nobody", "spawns": []},
    ])
    write(tmp_path / "world.json", {"territories": [], "nodes": [
        {"key": 301, "name": "Testheim", "enabled": True, "position": [3000.0, 0.0, 4000.0]},
        {"key": 302, "name": "Far Away", "enabled": True, "position": [9_000_000.0, 0.0, 0.0]},
    ]})
    meta = {"tilePx": 128, "unitsPerPixel": 100, "unitsPerTile": 12800, "minZoom": 0, "maxZoom": 1,
            "tileWorldSizeZ0": 25600, "grid": {"xmin": -1, "xmax": 0, "ymin": -1, "ymax": 0}}
    write(tmp_path / "worldmap-files" / "world" / "meta.json", meta)
    tile = tmp_path / "worldmap-files" / "world" / "1" / "-1" / "0.webp"
    tile.parent.mkdir(parents=True)
    tile.write_bytes(b"RIFF-tile")
    save([KnowledgeBatch(1.0, 0, (KnowledgeEntry(11, 1),)), NodeBatch(1.0, (NodeState(301, True),))])
    counts = client.post("/api/game-data/import", json={"path": str(tmp_path)}).json()
    assert (counts["npcs"], counts["knowledge_npcs"]) == (1, 2)

    data = client.get("/api/map").json()
    assert [layer["name"] for layer in data["layers"]] == ["world"]
    # «Far Away» поза сіткою плиток — на карту не потрапляє.
    assert data["nodes"] == [{"node_id": 301, "name": "Testheim", "territory": None, "sub": False,
                              "invested": True, "layer": "world", "x": 3000.0, "z": 4000.0}]
    (npc,) = data["npcs"]
    assert (npc["name"], npc["title"], npc["region"], npc["layer"]) == ("Mira", "Test Merchant", "Testheim", "world")
    assert [k["name"] for k in npc["knowledge"]] == ["Mira"]  # «Known» уже зібрано
    assert client.get("/api/game-data/map-tiles/world/1/-1/0").content == b"RIFF-tile"
    assert client.get("/api/game-data/map-tiles/world/1/5/5").status_code == 404
    assert client.get("/api/game-data/map-tiles/secret/1/-1/0").status_code == 404


def test_map_is_null_until_the_tiles_are_generated(client, extractor_output):
    client.post("/api/game-data/import", json={"path": str(extractor_output)})
    assert client.get("/api/map").json() is None
