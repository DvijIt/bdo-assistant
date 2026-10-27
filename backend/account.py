"""Персонажі, робітники й транспорт з записів bdo_toolkit.account.

Модуль не імпортує bdo_toolkit: записи розпізнаються за `record_type`, тож дашборд
працює й там, де агента немає.
"""

import sqlite3


SCHEMA = """
    -- Свої персонажі; кожен з'являється після входу ним у світ.
    CREATE TABLE IF NOT EXISTS characters (
        character_id INTEGER PRIMARY KEY,
        nick TEXT NOT NULL,
        family TEXT,
        class_id INTEGER,
        class_name TEXT,
        level INTEGER,
        xp INTEGER,
        xp_to_next INTEGER,
        fame_combat INTEGER,
        fame_life INTEGER,
        fame_third INTEGER,
        last_seen REAL NOT NULL
    );

    CREATE TABLE IF NOT EXISTS workers (
        worker_id INTEGER PRIMARY KEY,
        type_id INTEGER NOT NULL,
        type_name TEXT NOT NULL,
        level INTEGER NOT NULL,
        stamina INTEGER NOT NULL,
        town_id INTEGER NOT NULL,
        town_name TEXT NOT NULL,
        last_seen REAL NOT NULL
    );

    CREATE TABLE IF NOT EXISTS worker_skills (
        worker_id INTEGER NOT NULL REFERENCES workers (worker_id) ON DELETE CASCADE,
        position INTEGER NOT NULL,
        skill_id INTEGER NOT NULL,
        skill_name TEXT NOT NULL,
        PRIMARY KEY (worker_id, position)
    );

    -- Коні, кораблі й табори сім'ї; ім'я в межах типу унікальне.
    CREATE TABLE IF NOT EXISTS servants (
        kind_id INTEGER NOT NULL,
        name TEXT NOT NULL,
        category TEXT NOT NULL,
        level_guess INTEGER,
        last_seen REAL NOT NULL,
        PRIMARY KEY (kind_id, name)
    );

    CREATE TABLE IF NOT EXISTS servant_gear (
        kind_id INTEGER NOT NULL,
        name TEXT NOT NULL,
        slot INTEGER NOT NULL,
        item_id INTEGER NOT NULL,
        count INTEGER NOT NULL,
        durability INTEGER NOT NULL,
        max_durability INTEGER NOT NULL,
        PRIMARY KEY (kind_id, name, slot),
        FOREIGN KEY (kind_id, name) REFERENCES servants (kind_id, name) ON DELETE CASCADE
    );
"""

# Незнищенні предмети (наприклад, спорядження табору) мають максимальну міцність 32767.
INDESTRUCTIBLE = 32767


def initialize_schema(connection: sqlite3.Connection) -> None:
    connection.executescript(SCHEMA)


class AccountWriter:
    """Пише записи в базу. Досвід не містить ID персонажа, тож прив'язується
    до останнього персонажа, яким зайшли у світ."""

    def __init__(self) -> None:
        self.current_character_id: int | None = None

    def save(self, connection: sqlite3.Connection, records: list) -> int:
        saved = 0
        for record in records:
            handler = getattr(self, f"_{record.record_type}", None)
            if handler is not None:
                handler(connection, record)
                saved += 1
        return saved

    def _character_info(self, connection: sqlite3.Connection, r) -> None:
        self.current_character_id = r.character_id
        connection.execute(
            """
            INSERT INTO characters (character_id, nick, family, class_id, class_name,
                                    fame_combat, fame_life, fame_third, last_seen)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT (character_id) DO UPDATE SET
                nick = excluded.nick, family = excluded.family,
                class_id = excluded.class_id, class_name = excluded.class_name,
                fame_combat = excluded.fame_combat, fame_life = excluded.fame_life,
                fame_third = excluded.fame_third, last_seen = excluded.last_seen
            """,
            (r.character_id, r.nick, r.family, r.class_id, r.class_name,
             r.fame_combat, r.fame_life, r.fame_third, r.observed_at),
        )

    def _character_summary(self, connection: sqlite3.Connection, r) -> None:
        self.current_character_id = r.character_id
        connection.execute(
            """
            INSERT INTO characters (character_id, nick, level, last_seen) VALUES (?, ?, ?, ?)
            ON CONFLICT (character_id) DO UPDATE SET
                nick = excluded.nick, level = excluded.level, last_seen = excluded.last_seen
            """,
            (r.character_id, r.nick, r.level, r.observed_at),
        )

    def _experience(self, connection: sqlite3.Connection, r) -> None:
        if self.current_character_id is None:
            return
        connection.execute(
            "UPDATE characters SET level = ?, xp = ?, xp_to_next = ?, last_seen = ? WHERE character_id = ?",
            (r.level, r.xp, r.xp_to_next, r.observed_at, self.current_character_id),
        )

    def _worker(self, connection: sqlite3.Connection, r) -> None:
        connection.execute(
            """
            INSERT INTO workers (worker_id, type_id, type_name, level, stamina, town_id, town_name, last_seen)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT (worker_id) DO UPDATE SET
                type_id = excluded.type_id, type_name = excluded.type_name, level = excluded.level,
                stamina = excluded.stamina, town_id = excluded.town_id, town_name = excluded.town_name,
                last_seen = excluded.last_seen
            """,
            (r.worker_id, r.type_id, r.type_name, r.level, r.stamina, r.town_id, r.town_name, r.observed_at),
        )
        connection.execute("DELETE FROM worker_skills WHERE worker_id = ?", (r.worker_id,))
        connection.executemany(
            "INSERT INTO worker_skills (worker_id, position, skill_id, skill_name) VALUES (?, ?, ?, ?)",
            [(r.worker_id, i, skill, name) for i, (skill, name) in enumerate(zip(r.skills, r.skill_names))],
        )

    def _servant(self, connection: sqlite3.Connection, r) -> None:
        connection.execute(
            """
            INSERT INTO servants (kind_id, name, category, level_guess, last_seen) VALUES (?, ?, ?, ?, ?)
            ON CONFLICT (kind_id, name) DO UPDATE SET
                category = excluded.category, level_guess = excluded.level_guess, last_seen = excluded.last_seen
            """,
            (r.kind_id, r.name, r.category_name, r.level_guess, r.observed_at),
        )
        connection.execute("DELETE FROM servant_gear WHERE kind_id = ? AND name = ?", (r.kind_id, r.name))
        connection.executemany(
            """
            INSERT INTO servant_gear (kind_id, name, slot, item_id, count, durability, max_durability)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            [(r.kind_id, r.name, g.slot, g.item_id, g.count, g.durability, g.max_durability) for g in r.gear],
        )


def list_characters(connection: sqlite3.Connection) -> list[dict]:
    rows = connection.execute("SELECT * FROM characters ORDER BY last_seen DESC").fetchall()
    return [
        {
            "character_id": str(row["character_id"]),  # u64 не влазить у JS number
            "nick": row["nick"],
            "family": row["family"],
            "class_id": row["class_id"],
            "class_name": row["class_name"],
            "level": row["level"],
            "xp": row["xp"],
            "xp_to_next": row["xp_to_next"],
            "xp_percent": (100 * row["xp"] / row["xp_to_next"]) if row["xp"] is not None and row["xp_to_next"] else None,
            "fame": None if row["fame_combat"] is None else {
                "combat": row["fame_combat"], "life": row["fame_life"], "third": row["fame_third"],
                "total": row["fame_combat"] + row["fame_life"] + row["fame_third"],
            },
            "last_seen": row["last_seen"],
        }
        for row in rows
    ]


def list_workers(connection: sqlite3.Connection) -> list[dict]:
    skills: dict[int, list[dict]] = {}
    for row in connection.execute("SELECT * FROM worker_skills ORDER BY worker_id, position"):
        skills.setdefault(row["worker_id"], []).append({"id": row["skill_id"], "name": row["skill_name"]})
    rows = connection.execute("SELECT * FROM workers ORDER BY town_name, level DESC, type_name").fetchall()
    return [
        {
            "worker_id": str(row["worker_id"]),
            "type_id": row["type_id"],
            "type_name": row["type_name"],
            "level": row["level"],
            "stamina": row["stamina"],
            "town_id": row["town_id"],
            "town_name": row["town_name"],
            "skills": skills.get(row["worker_id"], []),
            "last_seen": row["last_seen"],
        }
        for row in rows
    ]


def list_servants(connection: sqlite3.Connection, prices: dict[tuple[int, int], int]) -> list[dict]:
    gear: dict[tuple[int, str], list[dict]] = {}
    for row in connection.execute(
        """
        SELECT g.*, i.name AS item_name, i.grade
        FROM servant_gear g LEFT JOIN items i ON i.item_id = g.item_id
        ORDER BY g.kind_id, g.name, g.slot
        """
    ):
        gear.setdefault((row["kind_id"], row["name"]), []).append(
            {
                "slot": row["slot"],
                "item_id": row["item_id"],
                "name": row["item_name"],
                "grade": row["grade"],
                "count": row["count"],
                "durability": None if row["max_durability"] == INDESTRUCTIBLE else row["durability"],
                "max_durability": None if row["max_durability"] == INDESTRUCTIBLE else row["max_durability"],
                "unit_price": prices.get((row["item_id"], 0)),
            }
        )
    rows = connection.execute("SELECT * FROM servants ORDER BY category, name").fetchall()
    return [
        {
            "kind_id": row["kind_id"],
            "name": row["name"],
            "category": row["category"],
            "level_guess": row["level_guess"],
            "gear": gear.get((row["kind_id"], row["name"]), []),
            "last_seen": row["last_seen"],
        }
        for row in rows
    ]


def missing_gear_item_ids(connection: sqlite3.Connection) -> list[int]:
    rows = connection.execute(
        """
        SELECT DISTINCT g.item_id FROM servant_gear g
        LEFT JOIN items i ON i.item_id = g.item_id
        WHERE i.item_id IS NULL ORDER BY g.item_id
        """
    ).fetchall()
    return [row[0] for row in rows]
