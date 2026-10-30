"""Імпорт знімків bdo-toolkit (ItemStateSnapshot.to_dict(), schema_version 5)."""

from dataclasses import dataclass, field
from datetime import datetime, timezone
import hashlib
import json
import sqlite3


SUPPORTED_SCHEMA_VERSIONS = {5}

# Склади спільні для сім'ї, тож у них немає персонажа.
FAMILY = ""

# Інвентарі, теж спільні для всієї сім'ї (код контейнера): Enhancement Inventory.
FAMILY_INVENTORY_CODES = {11}


class SnapshotError(ValueError):
    pass


class DuplicateSnapshotError(SnapshotError):
    pass


@dataclass
class Holding:
    item_id: int
    enhancement: int
    quantity: int
    instance: str


@dataclass
class ParsedContainer:
    kind: str
    game_code: int
    name: str
    holdings: list[Holding] = field(default_factory=list)


@dataclass
class ParsedSnapshot:
    schema_version: int
    taken_at: str
    hydration_detected: bool
    identity_complete: bool
    storage_status: str | None
    containers: list[ParsedContainer]


SCHEMA = """
    CREATE TABLE IF NOT EXISTS items (
        item_id INTEGER PRIMARY KEY,
        name TEXT NOT NULL,
        grade INTEGER NOT NULL DEFAULT 0,
        fetched_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    );

    CREATE TABLE IF NOT EXISTS snapshots (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        taken_at TEXT NOT NULL,
        imported_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        character TEXT NOT NULL,
        schema_version INTEGER NOT NULL,
        hydration_detected INTEGER NOT NULL,
        identity_complete INTEGER NOT NULL,
        storage_status TEXT,
        source_sha256 TEXT NOT NULL UNIQUE
    );

    CREATE TABLE IF NOT EXISTS containers (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        kind TEXT NOT NULL CHECK (kind IN ('inventory', 'currency', 'storage')),
        game_code INTEGER NOT NULL,
        name TEXT NOT NULL,
        character TEXT NOT NULL,
        UNIQUE (kind, game_code, character)
    );

    -- Які контейнери знімок справді бачив, навіть порожніми.
    CREATE TABLE IF NOT EXISTS snapshot_containers (
        snapshot_id INTEGER NOT NULL REFERENCES snapshots (id) ON DELETE CASCADE,
        container_id INTEGER NOT NULL REFERENCES containers (id),
        PRIMARY KEY (snapshot_id, container_id)
    );

    CREATE TABLE IF NOT EXISTS holdings (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        snapshot_id INTEGER NOT NULL REFERENCES snapshots (id) ON DELETE CASCADE,
        container_id INTEGER NOT NULL REFERENCES containers (id),
        item_id INTEGER NOT NULL,
        enhancement INTEGER NOT NULL DEFAULT 0,
        quantity INTEGER NOT NULL,
        instance TEXT NOT NULL
    );

    CREATE INDEX IF NOT EXISTS holdings_snapshot_container
        ON holdings (snapshot_id, container_id);
"""


def initialize_schema(connection: sqlite3.Connection) -> None:
    connection.executescript(SCHEMA)
    _merge_family_inventories(connection)


def _merge_family_inventories(connection: sqlite3.Connection) -> None:
    """Зводить спільні інвентарі, збережені раніше окремо на кожного персонажа, в один сімейний."""
    for code in FAMILY_INVENTORY_CODES:
        rows = connection.execute(
            "SELECT id, name FROM containers WHERE kind = 'inventory' AND game_code = ? AND character != ?",
            (code, FAMILY),
        ).fetchall()
        if not rows:
            continue

        connection.execute(
            """
            INSERT INTO containers (kind, game_code, name, character)
            VALUES ('inventory', ?, ?, ?)
            ON CONFLICT (kind, game_code, character) DO NOTHING
            """,
            (code, rows[0][1], FAMILY),
        )
        family_id = connection.execute(
            "SELECT id FROM containers WHERE kind = 'inventory' AND game_code = ? AND character = ?",
            (code, FAMILY),
        ).fetchone()[0]

        old_ids = [row[0] for row in rows]
        placeholders = ",".join("?" * len(old_ids))
        connection.execute(
            f"UPDATE OR IGNORE snapshot_containers SET container_id = ? WHERE container_id IN ({placeholders})",
            (family_id, *old_ids),
        )
        connection.execute(f"DELETE FROM snapshot_containers WHERE container_id IN ({placeholders})", old_ids)
        connection.execute(
            f"UPDATE holdings SET container_id = ? WHERE container_id IN ({placeholders})",
            (family_id, *old_ids),
        )
        connection.execute(f"DELETE FROM containers WHERE id IN ({placeholders})", old_ids)


def decode_item_id(raw_item_id: int) -> tuple[int, int]:
    """Старший байт item_id у bdo-toolkit — рівень заточки, молодші 24 біти — ID предмета."""
    return raw_item_id & 0xFFFFFF, raw_item_id >> 24


def _holding(record: dict) -> Holding:
    item_id, enhancement = decode_item_id(int(record["item_id"]))
    return Holding(
        item_id=item_id,
        enhancement=enhancement,
        quantity=int(record["quantity"]),
        instance=str(record["instance"]),
    )


def _inventory_containers(records: list[dict], kind: str) -> list[ParsedContainer]:
    # Порожні обгортки інвентаря не мають коду контейнера, тож контейнер
    # вважаємо побаченим лише тоді, коли в ньому є хоч один запис.
    containers: dict[int, ParsedContainer] = {}
    for record in records:
        code = int(record["container_code"])
        container = containers.setdefault(
            code,
            ParsedContainer(kind, code, record.get("container_name") or f"Container {code}"),
        )
        container.holdings.append(_holding(record))
    return list(containers.values())


def parse_snapshot(data: dict) -> ParsedSnapshot:
    if not isinstance(data, dict):
        raise SnapshotError("Знімок має бути JSON-об'єктом")

    schema_version = data.get("schema_version")
    if schema_version not in SUPPORTED_SCHEMA_VERSIONS:
        raise SnapshotError(
            f"Непідтримувана schema_version: {schema_version!r}; "
            f"очікується {sorted(SUPPORTED_SCHEMA_VERSIONS)}"
        )

    try:
        inventory = data["inventory"]
        storages = data["storages"]
        containers = _inventory_containers(inventory["items"], "inventory")
        containers += _inventory_containers(inventory["currency_balances"], "currency")

        for destination in storages["destinations"]:
            if not destination["current_state_observed"]:
                continue
            containers.append(
                ParsedContainer(
                    "storage",
                    int(destination["storage_id"]),
                    destination["name"],
                    [_holding(record) for record in destination["items"]],
                )
            )
    except (KeyError, TypeError, ValueError) as error:
        raise SnapshotError(f"Знімок має неочікувану структуру: {error!r}") from error

    observed = [
        holding_record["observed_at"]
        for holding_record in [
            *inventory["items"],
            *inventory["currency_balances"],
            *(record for d in storages["destinations"] for record in d["items"]),
        ]
        if isinstance(holding_record.get("observed_at"), (int, float))
    ]
    taken_at = (
        datetime.fromtimestamp(max(observed), timezone.utc)
        if observed
        else datetime.now(timezone.utc)
    )

    return ParsedSnapshot(
        schema_version=schema_version,
        taken_at=taken_at.isoformat(timespec="seconds"),
        hydration_detected=bool(data.get("hydration_detected")),
        identity_complete=bool(data.get("identity_complete")),
        storage_status=data.get("decoder_health", {}).get("storage_status"),
        containers=containers,
    )


def snapshot_sha256(data: dict) -> str:
    canonical = json.dumps(data, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _container_id(
    connection: sqlite3.Connection, container: ParsedContainer, character: str
) -> int:
    shared = container.kind == "storage" or (
        container.kind == "inventory" and container.game_code in FAMILY_INVENTORY_CODES
    )
    owner = FAMILY if shared else character
    connection.execute(
        """
        INSERT INTO containers (kind, game_code, name, character)
        VALUES (?, ?, ?, ?)
        ON CONFLICT (kind, game_code, character) DO UPDATE SET name = excluded.name
        """,
        (container.kind, container.game_code, container.name, owner),
    )
    return connection.execute(
        "SELECT id FROM containers WHERE kind = ? AND game_code = ? AND character = ?",
        (container.kind, container.game_code, owner),
    ).fetchone()[0]


def import_snapshot(connection: sqlite3.Connection, data: dict, character: str) -> dict:
    parsed = parse_snapshot(data)
    sha256 = snapshot_sha256(data)

    if connection.execute(
        "SELECT 1 FROM snapshots WHERE source_sha256 = ?", (sha256,)
    ).fetchone():
        raise DuplicateSnapshotError("Цей знімок уже імпортовано")

    snapshot_id = connection.execute(
        """
        INSERT INTO snapshots (
            taken_at, character, schema_version, hydration_detected,
            identity_complete, storage_status, source_sha256
        )
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            parsed.taken_at,
            character,
            parsed.schema_version,
            parsed.hydration_detected,
            parsed.identity_complete,
            parsed.storage_status,
            sha256,
        ),
    ).lastrowid

    counts = {"inventory": 0, "currency": 0, "storage": 0}
    for container in parsed.containers:
        container_id = _container_id(connection, container, character)
        connection.execute(
            "INSERT INTO snapshot_containers (snapshot_id, container_id) VALUES (?, ?)",
            (snapshot_id, container_id),
        )
        connection.executemany(
            """
            INSERT INTO holdings (
                snapshot_id, container_id, item_id, enhancement, quantity, instance
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            [
                (snapshot_id, container_id, h.item_id, h.enhancement, h.quantity, h.instance)
                for h in container.holdings
            ],
        )
        counts[container.kind] += len(container.holdings)

    return {
        "snapshot_id": snapshot_id,
        "taken_at": parsed.taken_at,
        "character": character,
        "containers": len(parsed.containers),
        "inventory_stacks": counts["inventory"],
        "currency_balances": counts["currency"],
        "storage_stacks": counts["storage"],
    }


# Поточний стан контейнера — його вміст в останньому знімку, який цей контейнер бачив.
LATEST_OBSERVATIONS = """
    SELECT container_id, MAX(snapshot_id) AS snapshot_id
    FROM snapshot_containers
    GROUP BY container_id
"""


def current_holdings(connection: sqlite3.Connection) -> list[dict]:
    rows = connection.execute(
        f"""
        SELECT c.id AS container_id, c.kind, c.game_code, c.name AS container_name,
               c.character, s.taken_at,
               h.item_id, h.enhancement, h.quantity,
               i.name AS item_name, i.grade
        FROM ({LATEST_OBSERVATIONS}) latest
        JOIN containers c ON c.id = latest.container_id
        JOIN snapshots s ON s.id = latest.snapshot_id
        LEFT JOIN holdings h
            ON h.snapshot_id = latest.snapshot_id AND h.container_id = c.id
        LEFT JOIN items i ON i.item_id = h.item_id
        ORDER BY c.kind, c.name, i.name, h.item_id, h.enhancement DESC
        """
    ).fetchall()

    containers: dict[int, dict] = {}
    for row in rows:
        container = containers.setdefault(
            row["container_id"],
            {
                "id": row["container_id"],
                "kind": row["kind"],
                "game_code": row["game_code"],
                "name": row["container_name"],
                "character": row["character"] or None,
                "observed_at": row["taken_at"],
                "items": [],
            },
        )
        if row["item_id"] is not None:
            container["items"].append(
                {
                    "item_id": row["item_id"],
                    "name": row["item_name"],
                    "grade": row["grade"],
                    "enhancement": row["enhancement"],
                    "quantity": row["quantity"],
                }
            )
    return list(containers.values())


def list_snapshots(connection: sqlite3.Connection) -> list[dict]:
    rows = connection.execute(
        """
        SELECT s.id, s.taken_at, s.imported_at, s.character, s.storage_status,
               s.hydration_detected, s.identity_complete,
               COUNT(h.id) AS stacks
        FROM snapshots s
        LEFT JOIN holdings h ON h.snapshot_id = s.id
        GROUP BY s.id
        ORDER BY s.id DESC
        """
    ).fetchall()
    return [
        {
            "id": row["id"],
            "taken_at": row["taken_at"],
            "imported_at": row["imported_at"],
            "character": row["character"],
            "storage_status": row["storage_status"],
            "hydration_detected": bool(row["hydration_detected"]),
            "identity_complete": bool(row["identity_complete"]),
            "stacks": row["stacks"],
        }
        for row in rows
    ]


def missing_item_ids(connection: sqlite3.Connection) -> list[int]:
    rows = connection.execute(
        """
        SELECT DISTINCT h.item_id
        FROM holdings h
        LEFT JOIN items i ON i.item_id = h.item_id
        WHERE i.item_id IS NULL
        ORDER BY h.item_id
        """
    ).fetchall()
    return [row[0] for row in rows]


def save_items(connection: sqlite3.Connection, items: list[dict]) -> None:
    connection.executemany(
        """
        INSERT INTO items (item_id, name, grade)
        VALUES (:id, :name, :grade)
        ON CONFLICT (item_id) DO UPDATE SET
            name = excluded.name,
            grade = excluded.grade,
            fetched_at = CURRENT_TIMESTAMP
        """,
        [
            {"id": int(item["id"]), "name": item["name"], "grade": int(item.get("grade") or 0)}
            for item in items
            if item and item.get("name")
        ],
    )
