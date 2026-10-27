import time

import pytest

account_models = pytest.importorskip("bdo_toolkit.account")
from bdo_toolkit.account import (CharacterInfo, CharacterSummary, Experience, GearItem,  # noqa: E402
                                 KnowledgeBatch, KnowledgeEntry, Servant, Worker)

import agent as agent_module  # noqa: E402
import arsha  # noqa: E402
import main  # noqa: E402


CHARACTER_ID = 0x0000000000A11CE1

RECORDS = [
    CharacterInfo(100.0, CHARACTER_ID, "Sefir", "Testfam", 34, 2136, 1669, 901),
    Experience(101.0, 61, 125_316_039, 234_278_708),
    Worker(102.0, 11, 7562, level=27, stamina=10, town_id=602, skills=(1909, 1501)),
    Worker(102.0, 12, 7552, level=1, stamina=8, town_id=9999),
    Servant(103.0, 31048, "Seabird", 1, 1, (GearItem(3, 49706, 1, 100, 100, 7),)),
    Servant(103.0, 9999, "Campsite", 3, 1, (GearItem(6, 18881, 1, 32767, 32767, 8),)),
]


def save(records):
    writer = main.account.AccountWriter()
    with main.get_connection() as connection:
        return writer.save(connection, records)


def test_characters_get_level_and_xp_from_experience(client):
    assert save(RECORDS[:2]) == 2

    (character,) = client.get("/api/characters").json()

    assert character["character_id"] == str(CHARACTER_ID)
    assert (character["nick"], character["family"], character["class_name"]) == ("Sefir", "Testfam", "Dosa")
    assert (character["level"], character["xp"], character["xp_to_next"]) == (61, 125_316_039, 234_278_708)
    assert round(character["xp_percent"], 3) == 53.490
    assert "fame" not in character


def test_characters_are_ordered_by_slot(client):
    save([CharacterInfo(300.0, 7, "Mirel", "Testfam", 35, 1, 1, 1, slot=1), RECORDS[0]])

    characters = client.get("/api/characters").json()

    assert [(c["nick"], c["slot"], c["class_name"]) for c in characters] == [
        ("Sefir", 0, "Dosa"), ("Mirel", 1, "Deadeye")]


def test_old_class_ids_with_the_slot_are_split(client):
    with main.get_connection() as connection:
        connection.executemany("INSERT INTO characters (character_id, nick, class_id, class_name, last_seen)"
                               " VALUES (?, ?, ?, ?, 1.0)",
                               [(7, "Mirel", 65571, "class#65571"), (8, "Sefir", 34, "Dosa")])
        main.account.initialize_schema(connection)

    characters = client.get("/api/characters").json()

    assert [(c["nick"], c["class_id"], c["slot"], c["class_name"]) for c in characters] == [
        ("Sefir", 34, 0, "Dosa"), ("Mirel", 35, 1, None)]


def test_fame_belongs_to_the_family(client):
    assert client.get("/api/family").json() is None
    save([RECORDS[0], CharacterInfo(200.0, 7, "Mobix", "Testfam", 6, 2141, 1669, 903)])

    family = client.get("/api/family").json()

    assert family["name"] == "Testfam"
    assert family["fame"] == {"combat": 2141, "life": 1669, "third": 903, "total": 4713}
    assert family["updated_at"] == 200.0


def test_summary_after_experience_keeps_the_level(client):
    # При вході короткий профіль приходить після досвіду.
    save([RECORDS[0], Experience(101.0, 62, 96_763_069, 7_262_639_948),
          CharacterSummary(102.0, CHARACTER_ID, "Sefir")])

    (character,) = client.get("/api/characters").json()

    assert (character["level"], character["xp"]) == (62, 96_763_069)


def test_experience_before_any_character_is_ignored(client):
    save([RECORDS[1]])
    assert client.get("/api/characters").json() == []


def test_workers_with_named_skills_and_unknown_town(client):
    save(RECORDS[2:4])

    workers = {w["worker_id"]: w for w in client.get("/api/workers").json()}

    assert workers["11"]["type_name"] == "Professional Goblin Worker"
    assert workers["11"]["town_name"] == "Keplan"
    assert workers["11"]["skills"] == [{"id": 1909, "name": "Ore Packing"}, {"id": 1501, "name": "Lucky Guy A"}]
    assert (workers["12"]["town_name"], workers["12"]["skills"]) == ("town#9999", [])


def test_worker_seen_again_replaces_its_skills(client):
    save([RECORDS[2]])
    save([Worker(200.0, 11, 7562, level=28, stamina=9, town_id=602, skills=(1002,))])

    (worker,) = client.get("/api/workers").json()

    assert (worker["level"], worker["stamina"]) == (28, 9)
    assert [s["id"] for s in worker["skills"]] == [1002]


def test_servants_gear_gets_item_names_on_refresh(client, monkeypatch):
    monkeypatch.setattr(arsha, "fetch_items", lambda ids, lang="en": [
        {"id": 49706, "name": "Ship Prow", "grade": 3}])
    save(RECORDS[4:6])

    before = client.get("/api/servants").json()
    assert before["missing_names"] == 2
    assert client.post("/api/items/refresh").json() == {"missing_names": 1}

    servants = {s["name"]: s for s in client.get("/api/servants").json()["servants"]}
    (prow,) = servants["Seabird"]["gear"]
    assert servants["Seabird"]["category"] == "ship"
    assert (prow["name"], prow["durability"], prow["max_durability"]) == ("Ship Prow", 100, 100)
    (camp_item,) = servants["Campsite"]["gear"]
    assert servants["Campsite"]["category"] == "camp"
    assert (camp_item["name"], camp_item["durability"]) == (None, None)  # незнищенне


def test_knowledge_from_several_batches(client):
    assert client.get("/api/knowledge").json()["total"] == 0

    save([
        KnowledgeBatch(300.0, 2591, (KnowledgeEntry(1, 1), KnowledgeEntry(2, 5))),
        KnowledgeBatch(300.0, 2591, (KnowledgeEntry(3, 2),)),
    ])
    # Наступний вхід: знання 3 підвищило рівень, з'явилось нове.
    save([KnowledgeBatch(400.0, 2596, (KnowledgeEntry(3, 3), KnowledgeEntry(4, 1)))])

    knowledge = client.get("/api/knowledge").json()

    assert (knowledge["total"], knowledge["ecology_points"], knowledge["updated_at"]) == (4, 2596, 400.0)
    assert {row["grade"]: row["count"] for row in knowledge["by_level"]} == {"C": 2, "B": 0, "A": 1, "S": 0, "SS": 1}


class FakeSession:
    def __init__(self, messages):
        self.messages = list(messages)
        self.stopped = False
        self.started = False

    def start(self):
        self.started = True

    def poll(self, timeout=None):
        if self.messages:
            return self.messages.pop(0)
        self.stopped = True
        return None

    def stop(self):
        self.stopped = True


class FakeDecoder:
    def feed(self, message):
        return [message]


def wait_until_stopped(agent, timeout=5.0):
    deadline = time.monotonic() + timeout
    while agent.status()["state"] in ("starting", "running") and time.monotonic() < deadline:
        time.sleep(0.02)
    return agent.status()


def test_agent_writes_decoded_records_until_the_session_ends(client, monkeypatch):
    agent = agent_module.Agent(main.get_connection, lambda: FakeSession(RECORDS), FakeDecoder)
    monkeypatch.setattr(main, "agent", agent)

    assert client.post("/api/agent/start").json()["state"] in ("starting", "running", "stopped")
    status = wait_until_stopped(agent)

    assert (status["state"], status["error"], status["messages"], status["records"]) == ("stopped", None, 6, 6)
    assert [c["nick"] for c in client.get("/api/characters").json()] == ["Sefir"]
    assert len(client.get("/api/workers").json()) == 2
    assert client.get("/api/agent").json()["state"] == "stopped"


def test_agent_reports_why_capture_could_not_start(client):
    def broken():
        raise PermissionError("Npcap access denied")

    agent = agent_module.Agent(main.get_connection, broken, FakeDecoder)
    agent.start()
    status = wait_until_stopped(agent)

    assert status["state"] == "error"
    assert "Npcap access denied" in status["error"]
