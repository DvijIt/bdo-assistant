from pathlib import Path
import sys

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import arsha  # noqa: E402
import main  # noqa: E402


KNOWN_ITEMS = {
    1: ("Silver", 0),
    6: ("Pearl", 0),
    44195: ("Memory Fragment", 0),
    752021: ("Flawless Magical Black Stone", 4),
    11640: ("Asula's Crimson Eye Necklace", 2),
    695182: ("Tuvala Enlightened Blade", 3),
}


def fake_fetch_items(item_ids, lang="en"):
    return [
        {"id": item_id, "name": KNOWN_ITEMS[item_id][0], "grade": KNOWN_ITEMS[item_id][1]}
        for item_id in item_ids
        if item_id in KNOWN_ITEMS
    ]


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(main, "DB_PATH", tmp_path / "test.db")
    monkeypatch.setattr(arsha, "fetch_items", fake_fetch_items)
    with TestClient(main.app) as test_client:
        yield test_client


def item(raw_item_id, quantity, instance, observed_at=1793037771.0, **extra):
    return {
        "item_id": raw_item_id,
        "quantity": quantity,
        "instance": instance,
        "observed_at": observed_at,
        **extra,
    }


def inventory_item(raw_item_id, quantity, instance, code, name):
    return item(
        raw_item_id,
        quantity,
        instance,
        inventory_slot=1,
        container_code=code,
        container_code_hex=f"0x{code:02X}",
        container_name=name,
        container_confidence="provisional",
    )


def destination(storage_id, name, items, observed=True):
    return {
        "storage_id": storage_id,
        "name": name,
        "name_confidence": "observed",
        "occupied_stacks": len(items),
        "current_state_observed": observed,
        "current_empty": observed and not items,
        "current_identity_complete": True,
        "items": items,
    }


def snapshot(inventory_items=(), currencies=(), destinations=()):
    """Знеособлений знімок у форматі bdo-toolkit 1.0.15 (schema_version 5)."""
    return {
        "schema_version": 5,
        "hydration_detected": True,
        "identity_complete": True,
        "provenance": {"capture_mode": "live_capture"},
        "coverage": {},
        "decoder_health": {"storage_status": "compatible" if destinations else "not_observed"},
        "inventory": {
            "hydration_observed": True,
            "occupied_stacks": len(inventory_items),
            "items": list(inventory_items),
            "currency_balances": list(currencies),
        },
        "storages": {"destinations": list(destinations)},
        "warnings": [],
    }
