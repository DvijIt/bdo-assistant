import json

import pytest

pytest.importorskip("bdo_toolkit.account")
from bdo_toolkit.account import CharacterInfo, GearItem, KnowledgeBatch, KnowledgeEntry, Servant, Worker  # noqa: E402

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
    write(out / "world.json", {"territories": [], "regions": [], "nodes": [
        {"key": 301, "name": "Testheim", "enabled": True},
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

    assert counts == {"categories": 2, "knowledge": 2, "nodes": 1, "items": 1, "quests": 1, "characters": 3,
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


def test_folder_without_extractor_output_is_rejected(client, tmp_path):
    response = client.post("/api/game-data/import", json={"path": str(tmp_path)})

    assert response.status_code == 422
    assert "bdo-data-extractor" in response.json()["detail"]
