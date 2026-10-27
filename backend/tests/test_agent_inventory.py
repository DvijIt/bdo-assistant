import time

import pytest

pytest.importorskip("bdo_toolkit.account")
from bdo_toolkit.account import CharacterInfo  # noqa: E402

import agent as agent_module  # noqa: E402
import main  # noqa: E402
from conftest import destination, inventory_item, item, snapshot  # noqa: E402


def login(nick, at):
    return CharacterInfo(at, hash(nick) & 0xFFFF, nick, "Testfam", 34, 1, 1, 1)


class FakeRawSession:
    def __init__(self, records, delay=0.0):
        self.records = list(records)
        self.delay = delay
        self.stopped = False

    def start(self):
        pass

    def poll(self, timeout=None):
        if self.records:
            time.sleep(self.delay)
            return self.records.pop(0)
        self.stopped = True
        return None

    def stop(self):
        self.stopped = True


class FakeDecoder:
    def feed(self, message):
        return [message]


class FakeSnapshot:
    def __init__(self, data):
        self.data = data

    def to_dict(self):
        return self.data


class FakeInventorySessions:
    """Видає по одному знімку на кожну сесію, як бібліотека на кожен вхід."""

    def __init__(self, *snapshots):
        self.snapshots = list(snapshots)
        self.started = 0

    def __call__(self, profile):
        factory = self

        class Session:
            def start(self):
                factory.started += 1

            def stop(self):
                return FakeSnapshot(factory.snapshots.pop(0))

        return Session()


def run_agent(records, inventory_sessions, profile="opcodes.local", delay=0.0):
    agent = agent_module.Agent(
        main.get_connection, lambda: FakeRawSession(records, delay), FakeDecoder,
        inventory_profile=lambda: profile, import_snapshot=main.import_agent_snapshot,
        inventory_session_factory=inventory_sessions, inventory_settle_seconds=0.05,
    )
    agent.start()
    deadline = time.monotonic() + 5
    while agent.status()["state"] in ("starting", "running") and time.monotonic() < deadline:
        time.sleep(0.02)
    return agent.status()


def sorentik_snapshot(silver):
    return snapshot(
        inventory_items=[inventory_item(752021, 13, "0x01", 11, "Enhancement Inventory")],
        currencies=[item(1, silver, "0x03", container_code=0, container_name="Global Currencies")],
        destinations=[destination(202, "Altinova", [item(44195, 7, "0x05")])],
    )


def test_each_login_imports_its_own_snapshot(client):
    sessions = FakeInventorySessions(sorentik_snapshot(5_000_000),
                                     snapshot(inventory_items=[inventory_item(44195, 2, "0x09", 0, "Main Inventory")]))

    status = run_agent([login("Sefir", 1.0), login("Mirel", 2.0)], sessions, delay=0.1)

    assert status["state"] == "stopped"
    assert (status["inventory"]["enabled"], status["inventory"]["snapshots"]) == (True, 2)
    assert status["inventory"]["last"]["character"] == "Mirel"
    assert sessions.started == 2  # свіжа сесія для другого входу; після зупинки агента — жодної
    imported = client.get("/api/snapshots").json()
    assert sorted(s["character"] for s in imported) == ["Mirel", "Sefir"]
    names = {c["name"]: c for c in client.get("/api/holdings").json()["containers"]}
    assert "Altinova" in names


def test_without_a_profile_the_agent_explains_and_skips_inventory(client):
    status = run_agent([login("Sefir", 1.0)], FakeInventorySessions(), profile=None)

    assert status["state"] == "stopped"
    assert status["inventory"]["enabled"] is False
    assert "opcodes.local" in status["inventory"]["note"]
    assert client.get("/api/snapshots").json() == []


def test_login_without_inventory_traffic_is_reported_not_imported(client):
    empty = snapshot()
    empty["hydration_detected"] = False

    status = run_agent([login("Sefir", 1.0)], FakeInventorySessions(empty))

    assert status["inventory"]["snapshots"] == 0
    assert "Sefir" in status["inventory"]["note"]
    assert client.get("/api/snapshots").json() == []
