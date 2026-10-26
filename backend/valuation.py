"""Ринкові ціни arsha.io і вартість акаунта за поточними знімками."""

from collections import defaultdict
import sqlite3

import snapshots


SILVER_ITEM_ID = 1
TOP_ITEMS = 10

SCHEMA = """
    -- Одна ринкова позиція на діапазон заточки. base_price 0 означає,
    -- що предмет поза ринком; такі ID не перепитуємо при звичайному оновленні.
    CREATE TABLE IF NOT EXISTS prices (
        item_id INTEGER NOT NULL,
        min_enhancement INTEGER NOT NULL,
        max_enhancement INTEGER NOT NULL,
        base_price INTEGER NOT NULL,
        last_sold_price INTEGER NOT NULL DEFAULT 0,
        current_stock INTEGER NOT NULL DEFAULT 0,
        fetched_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY (item_id, min_enhancement)
    );
"""


def initialize_schema(connection: sqlite3.Connection) -> None:
    connection.executescript(SCHEMA)


def item_ids_to_price(connection: sqlite3.Connection, include_off_market: bool = False) -> list[int]:
    """ID предметів у поточному стані, ціни яких варто оновити.

    Валюти (срібло, перли) ринкових цін не мають і пропускаються.
    """
    rows = connection.execute(
        f"""
        SELECT DISTINCT h.item_id
        FROM ({snapshots.LATEST_OBSERVATIONS}) latest
        JOIN containers c ON c.id = latest.container_id AND c.kind != 'currency'
        JOIN holdings h
            ON h.snapshot_id = latest.snapshot_id AND h.container_id = c.id
        WHERE ? OR NOT EXISTS (
            SELECT 1 FROM prices p WHERE p.item_id = h.item_id
        ) OR EXISTS (
            SELECT 1 FROM prices p WHERE p.item_id = h.item_id AND p.base_price > 0
        )
        ORDER BY h.item_id
        """,
        (include_off_market,),
    ).fetchall()
    return [row[0] for row in rows]


def save_prices(connection: sqlite3.Connection, item_ids: list[int], entries: list[dict]) -> None:
    connection.executemany(
        "DELETE FROM prices WHERE item_id = ?", [(item_id,) for item_id in item_ids]
    )
    by_item: dict[int, list[dict]] = defaultdict(list)
    for entry in entries:
        by_item[int(entry["id"])].append(entry)

    rows = []
    for item_id in item_ids:
        # Предмет, якого ринок не повернув, записуємо як «поза ринком».
        for entry in by_item.get(item_id) or [{"minEnhance": 0, "maxEnhance": 20, "basePrice": 0}]:
            rows.append(
                (
                    item_id,
                    int(entry.get("minEnhance") or 0),
                    int(entry.get("maxEnhance") or 0),
                    int(entry.get("basePrice") or 0),
                    int(entry.get("lastSoldPrice") or 0),
                    int(entry.get("currentStock") or 0),
                )
            )
    connection.executemany(
        """
        INSERT OR REPLACE INTO prices (
            item_id, min_enhancement, max_enhancement,
            base_price, last_sold_price, current_stock
        )
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        rows,
    )


def unit_prices(connection: sqlite3.Connection) -> dict[tuple[int, int], int]:
    """{(item_id, enhancement): ціна} для кожної заточки з ринковою ціною."""
    prices: dict[tuple[int, int], int] = {}
    for row in connection.execute(
        "SELECT item_id, min_enhancement, max_enhancement, base_price FROM prices WHERE base_price > 0"
    ):
        for enhancement in range(row[1], row[2] + 1):
            prices[(row[0], enhancement)] = row[3]
    return prices


def prices_fetched_at(connection: sqlite3.Connection) -> str | None:
    # CURRENT_TIMESTAMP у SQLite — UTC без поясу; віддаємо ISO 8601 для браузера.
    fetched_at = connection.execute("SELECT MAX(fetched_at) FROM prices").fetchone()[0]
    return None if fetched_at is None else fetched_at.replace(" ", "T") + "Z"


def account_value(connection: sqlite3.Connection) -> dict:
    containers = snapshots.current_holdings(connection)
    prices = unit_prices(connection)

    silver = 0
    items_value = 0
    priced_stacks = 0
    unpriced_stacks = 0
    by_container = []
    valued_items = []
    # Незкладувані предмети лежать окремими стеками навіть в одному місті,
    # тож кількість сумуємо по місту.
    storage_places: dict[tuple[int, int], dict[str, int]] = defaultdict(lambda: defaultdict(int))
    storage_names: dict[tuple[int, int], str | None] = {}

    for container in containers:
        container_value = 0
        for holding in container["items"]:
            if container["kind"] == "currency":
                if holding["item_id"] == SILVER_ITEM_ID:
                    silver += holding["quantity"]
                continue

            key = (holding["item_id"], holding["enhancement"])
            if container["kind"] == "storage":
                storage_places[key][container["name"]] += holding["quantity"]
                storage_names[key] = holding["name"]

            price = prices.get(key)
            if price is None:
                unpriced_stacks += 1
                continue

            value = price * holding["quantity"]
            priced_stacks += 1
            container_value += value
            valued_items.append({**holding, "container": container["name"], "unit_price": price, "value": value})

        items_value += container_value
        if container["kind"] != "currency":
            by_container.append(
                {"id": container["id"], "kind": container["kind"], "name": container["name"], "value": container_value}
            )

    # Дублікати — і з ціною, і без: прив'язані предмети теж варто звезти в одне місто.
    duplicates = []
    for (item_id, enhancement), places in storage_places.items():
        if len(places) < 2:
            continue
        quantity = sum(places.values())
        price = prices.get((item_id, enhancement))
        duplicates.append(
            {
                "item_id": item_id,
                "name": storage_names[(item_id, enhancement)],
                "enhancement": enhancement,
                "quantity": quantity,
                "value": None if price is None else price * quantity,
                "places": [
                    {"container": name, "quantity": place_quantity}
                    for name, place_quantity in sorted(places.items())
                ],
            }
        )

    return {
        "total_value": items_value + silver,
        "items_value": items_value,
        "silver": silver,
        "priced_stacks": priced_stacks,
        "unpriced_stacks": unpriced_stacks,
        "prices_fetched_at": prices_fetched_at(connection),
        "by_container": sorted(by_container, key=lambda c: c["value"], reverse=True),
        "top_items": sorted(valued_items, key=lambda i: i["value"], reverse=True)[:TOP_ITEMS],
        "duplicates": sorted(
            duplicates, key=lambda d: (d["value"] or 0, d["name"] or ""), reverse=True
        ),
    }
