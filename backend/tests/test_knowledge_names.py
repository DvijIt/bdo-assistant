import json

import pytest

pytest.importorskip("bdo_toolkit.account")
from bdo_toolkit.account import KnowledgeBatch, KnowledgeEntry  # noqa: E402

import main  # noqa: E402

# Вигадані дані у форматі, який bdocodex вбудовує в сторінку знань.
DATA = {
    "categories": {
        "1": ["Characters", 0, 0, 192, 0, 0, 31, 0],
        "10": ["People of Testvale", 1, 0, 10, 0, 0, 5, 0],
        "10001": ["Ecology", 0, 0, 163, 0, 0, 0, 0],
        "10002": ["Beasts", 1, 0, 2, 0, 0, 0, 0],
    },
    "category_tree": {"0": [1, 10001], "1": [10], "10001": [10002]},
    "entries": {
        "1": [10, 0, "Test Merchant", 0],
        "2": [10, 1, "Test Guard&#39;s Wife", 1],
        "4150": [10002, 0, "Baby Boar", 2],
        "4006": [10002, 1, "Boar", 3],
        "4005": [10002, 2, "Wolf", 4],
    },
    "entry_tree": {"10": [1, 2], "10002": [4150, 4006, 4005, 4006]},  # повтор, як у справжніх даних
    "icons": [],
    "hints": [],
}
PAGE = "<html><script>var x = 1;</script><script>" + json.dumps(DATA) + "</script></html>"


def gain(levels):
    writer = main.account.AccountWriter()
    with main.get_connection() as connection:
        writer.save(connection, [KnowledgeBatch(1.0, 2596, tuple(KnowledgeEntry(k, v) for k, v in levels.items()))])


def test_import_page_and_browse_categories_with_progress(client):
    assert client.post("/api/knowledge/import", content=PAGE.encode()).json() == {"categories": 4, "knowledge": 5}
    gain({1: 1, 4150: 2, 4006: 5})

    roots = client.get("/api/knowledge/categories").json()
    assert [(c["name"], c["gained"], c["total"]) for c in roots["categories"]] == [
        ("Characters", 1, 2), ("Ecology", 2, 3)]

    people = client.get("/api/knowledge/categories?parent=10").json()
    assert [(e["name"], e["gained"], e["grade"]) for e in people["entries"]] == [
        ("Test Merchant", True, "—"), ("Test Guard's Wife", False, None)]

    beasts = client.get("/api/knowledge/categories?parent=10002").json()
    assert [(e["name"], e["grade"]) for e in beasts["entries"]] == [("Baby Boar", "B"), ("Boar", "S"), ("Wolf", None)]


def test_summary_separates_ungraded_knowledge_once_names_are_known(client):
    client.post("/api/knowledge/import", content=PAGE.encode())
    gain({1: 1, 2: 1, 4150: 2, 4006: 5})

    knowledge = client.get("/api/knowledge").json()

    assert (knowledge["names_loaded"], knowledge["total"], knowledge["ungraded"]) == (5, 4, 2)
    assert {row["grade"]: row["count"] for row in knowledge["by_level"]} == {"C": 0, "B": 1, "A": 0, "4": 0, "S": 1}


def test_a_page_without_knowledge_data_is_rejected(client):
    response = client.post("/api/knowledge/import", content=b"<html>login page</html>")

    assert response.status_code == 422
    assert "bdocodex" in response.json()["detail"]
