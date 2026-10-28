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
        slot INTEGER,                  -- місце на екрані вибору персонажа, з 0
        level INTEGER,
        xp INTEGER,
        xp_to_next INTEGER,
        last_seen REAL NOT NULL
    );

    -- Слава спільна для сім'ї, хоч і приходить разом із даними персонажа.
    CREATE TABLE IF NOT EXISTS family (
        id INTEGER PRIMARY KEY CHECK (id = 1),
        name TEXT,
        fame_combat INTEGER NOT NULL,
        fame_life INTEGER NOT NULL,
        fame_third INTEGER NOT NULL,
        updated_at REAL NOT NULL
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

    -- Книга знань спільна для сім'ї; рівень 1–5, ймовірно C…SS.
    CREATE TABLE IF NOT EXISTS knowledge (
        knowledge_id INTEGER PRIMARY KEY,
        level INTEGER NOT NULL,
        last_seen REAL NOT NULL
    );

    CREATE TABLE IF NOT EXISTS knowledge_summary (
        id INTEGER PRIMARY KEY CHECK (id = 1),
        ecology_points INTEGER NOT NULL,
        updated_at REAL NOT NULL
    );
"""

# Ймовірна відповідність рівнів буквам у грі; не перевірена на конкретних знаннях.
# Звірено з грою: C=1, B=2, A=3, S=5; букву для 4 ще не підтверджено.
KNOWLEDGE_GRADES = {1: "C", 2: "B", 3: "A", 4: "4", 5: "S"}

# Незнищенні предмети (наприклад, спорядження табору) мають максимальну міцність 32767.
INDESTRUCTIBLE = 32767


def initialize_schema(connection: sqlite3.Connection) -> None:
    connection.executescript(SCHEMA)
    try:
        connection.execute("ALTER TABLE characters ADD COLUMN slot INTEGER")
    except sqlite3.OperationalError:  # колонка вже є
        pass
    # Раніше клас читався як u32 разом зі слотом у старших байтах.
    connection.execute(
        """
        UPDATE characters SET
            class_name = CASE WHEN class_id > 65535 THEN NULL ELSE class_name END,
            slot = class_id >> 16, class_id = class_id & 65535
        WHERE class_id > 65535 OR (slot IS NULL AND class_id IS NOT NULL)
        """
    )
    # Старі бази тримали славу в characters; переносимо найсвіжішу в family.
    try:
        connection.execute(
            """
            INSERT INTO family (id, name, fame_combat, fame_life, fame_third, updated_at)
            SELECT 1, family, fame_combat, fame_life, fame_third, last_seen FROM characters
            WHERE fame_combat IS NOT NULL AND NOT EXISTS (SELECT 1 FROM family)
            ORDER BY last_seen DESC LIMIT 1
            """
        )
    except sqlite3.OperationalError:  # нова база без колонок слави в characters
        pass


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
            INSERT INTO characters (character_id, nick, family, class_id, class_name, slot, last_seen)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT (character_id) DO UPDATE SET
                nick = excluded.nick, family = excluded.family,
                class_id = excluded.class_id, class_name = excluded.class_name,
                slot = excluded.slot, last_seen = excluded.last_seen
            """,
            (r.character_id, r.nick, r.family, r.class_id, r.class_name, r.slot, r.observed_at),
        )
        connection.execute(
            """
            INSERT INTO family (id, name, fame_combat, fame_life, fame_third, updated_at)
            VALUES (1, ?, ?, ?, ?, ?)
            ON CONFLICT (id) DO UPDATE SET
                name = excluded.name, fame_combat = excluded.fame_combat, fame_life = excluded.fame_life,
                fame_third = excluded.fame_third, updated_at = excluded.updated_at
            """,
            (r.family, r.fame_combat, r.fame_life, r.fame_third, r.observed_at),
        )

    def _character_summary(self, connection: sqlite3.Connection, r) -> None:
        # Рівень беремо лише з досвіду: короткий профіль після левел-апу відстає.
        self.current_character_id = r.character_id
        connection.execute(
            """
            INSERT INTO characters (character_id, nick, last_seen) VALUES (?, ?, ?)
            ON CONFLICT (character_id) DO UPDATE SET
                nick = excluded.nick, last_seen = excluded.last_seen
            """,
            (r.character_id, r.nick, r.observed_at),
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


    def _knowledge_batch(self, connection: sqlite3.Connection, r) -> None:
        connection.executemany(
            """
            INSERT INTO knowledge (knowledge_id, level, last_seen) VALUES (?, ?, ?)
            ON CONFLICT (knowledge_id) DO UPDATE SET level = excluded.level, last_seen = excluded.last_seen
            """,
            [(e.knowledge_id, e.level, r.observed_at) for e in r.entries],
        )
        connection.execute(
            """
            INSERT INTO knowledge_summary (id, ecology_points, updated_at) VALUES (1, ?, ?)
            ON CONFLICT (id) DO UPDATE SET
                ecology_points = excluded.ecology_points, updated_at = excluded.updated_at
            """,
            (r.ecology_points, r.observed_at),
        )


def knowledge_summary(connection: sqlite3.Connection, graded_ids: set[int] | None = None) -> dict:
    """`graded_ids` — знання з розділів, що мають рівні (з імпортованих назв); тоді решта
    рахується як «без рівня», а не як найнижчий рівень."""
    summary = connection.execute("SELECT ecology_points, updated_at FROM knowledge_summary WHERE id = 1").fetchone()
    levels = dict(connection.execute("SELECT knowledge_id, level FROM knowledge").fetchall())
    counts: dict[int, int] = {}
    ungraded = 0
    for knowledge_id, level in levels.items():
        if graded_ids is not None and knowledge_id not in graded_ids:
            ungraded += 1
        else:
            counts[level] = counts.get(level, 0) + 1
    return {
        "total": len(levels),
        "ecology_points": None if summary is None else summary["ecology_points"],
        "updated_at": None if summary is None else summary["updated_at"],
        "by_level": [
            {"level": level, "grade": KNOWLEDGE_GRADES.get(level, str(level)), "count": counts.get(level, 0)}
            for level in sorted(set(KNOWLEDGE_GRADES) | set(counts))
        ],
        "ungraded": None if graded_ids is None else ungraded,
    }


def list_characters(connection: sqlite3.Connection) -> list[dict]:
    rows = connection.execute(
        "SELECT * FROM characters ORDER BY slot IS NULL, slot, last_seen DESC"
    ).fetchall()
    return [
        {
            "character_id": str(row["character_id"]),  # u64 не влазить у JS number
            "nick": row["nick"],
            "family": row["family"],
            "class_id": row["class_id"],
            "class_name": row["class_name"],
            "slot": row["slot"],
            "level": row["level"],
            "xp": row["xp"],
            "xp_to_next": row["xp_to_next"],
            "xp_percent": (100 * row["xp"] / row["xp_to_next"]) if row["xp"] is not None and row["xp_to_next"] else None,
            "last_seen": row["last_seen"],
        }
        for row in rows
    ]


def family_summary(connection: sqlite3.Connection) -> dict | None:
    row = connection.execute("SELECT * FROM family WHERE id = 1").fetchone()
    if row is None:
        return None
    return {
        "name": row["name"],
        "fame": {
            "combat": row["fame_combat"], "life": row["fame_life"], "third": row["fame_third"],
            "total": row["fame_combat"] + row["fame_life"] + row["fame_third"],
        },
        "updated_at": row["updated_at"],
    }


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
