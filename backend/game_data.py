"""Назви з власного клієнта гри: імпорт виводу bdo-data-extractor (github.com/iDevelopThings/bdo-data-extractor).

Користувач сам запускає extractor на своєму встановленому клієнті (`build` і `loc`), а застосунок лише читає
готові JSON з указаної папки. Таблиці лежать тільки в локальній базі; у репозиторій вони не потрапляють.

Що звідки:
- knowledge.json             → дерево знань (розділи й знання; ключі збігаються з трафіком)
- world.json → nodes         → вузли/міста за ключем (301 = Heidel, як у трафіку робітників)
- items.json                 → назви й грейди предметів (таблиця items, яку також доповнює arsha.io)
- loc: таблиця 18            → квести "група-номер" (key1 = plane<<24 | номер, plane 0 — назва)
- loc: таблиця 6             → персонажі за character key: типи робітників (7572), транспорт (31048), класи
- loc: таблиця навичок робітників визначається автоматично за підтвердженими в грі назвами
loc читається з locs/<таблиця>.json (extractor пише їх поруч) або з loc_<мова>.json.

Картинки (команди extractor `icons` і `knowledge-icons`) не копіюються: бекенд віддає їх прямо з папки імпорту.
Шлях до файлу — з asset_redirects.json, який ці команди пишуть поруч ("urn::item:49706" → "icons/…/00049706.webp",
"urn::knowledge:entry:4150" → "knowledge_icons/…"); тож повторний імпорт після них не потрібен.
"""

import json
import re
import sqlite3
import time
from pathlib import Path

import knowledge_names


SCHEMA = """
    CREATE TABLE IF NOT EXISTS game_names (
        kind TEXT NOT NULL,          -- node, quest, character, worker_skill
        key TEXT NOT NULL,
        name TEXT NOT NULL,
        PRIMARY KEY (kind, key)
    );

    -- Вузли з world.json: територія, головний вузол (для підвузлів), вартість у CP і продукти.
    CREATE TABLE IF NOT EXISTS game_nodes (
        node_id INTEGER PRIMARY KEY,
        name TEXT NOT NULL,
        territory TEXT,
        manager_id INTEGER,
        contribution INTEGER,
        products TEXT NOT NULL,         -- JSON-список item_id
        x REAL,                         -- світові координати (см); висоту не зберігаємо
        z REAL
    );

    -- NPC з npcs.json з першою точкою, де вони стоять у світі.
    CREATE TABLE IF NOT EXISTS game_npcs (
        npc_id INTEGER PRIMARY KEY,
        name TEXT NOT NULL,
        title TEXT,
        region TEXT,
        x REAL NOT NULL,
        z REAL NOT NULL
    );

    -- Знання, яке дає розмова з NPC (знання → персонаж → NPC, що стоїть у світі).
    CREATE TABLE IF NOT EXISTS knowledge_npc (
        knowledge_id INTEGER PRIMARY KEY,
        npc_id INTEGER NOT NULL
    );

    -- Квести з quests.json; умови взяття — сирий DSL клієнта (clearquest(904,1); getLevel()>49; …).
    CREATE TABLE IF NOT EXISTS game_quests (
        quest_key TEXT PRIMARY KEY,     -- «група-номер», як у трафіку
        name TEXT NOT NULL,
        giver TEXT,
        objective TEXT,
        description TEXT,
        accept_dsl TEXT
    );

    -- Журнали пригод з adventure_journals.json: журнал → книги → сторінки-квести з бонусами сім'ї.
    CREATE TABLE IF NOT EXISTS game_journals (
        journal_key INTEGER PRIMARY KEY,
        name TEXT NOT NULL,
        description TEXT,
        position INTEGER NOT NULL
    );

    CREATE TABLE IF NOT EXISTS game_journal_books (
        journal_key INTEGER NOT NULL,
        book_key INTEGER NOT NULL,
        name TEXT NOT NULL,
        requirement TEXT,
        position INTEGER NOT NULL,
        PRIMARY KEY (journal_key, book_key)
    );

    CREATE TABLE IF NOT EXISTS game_journal_pages (
        journal_key INTEGER NOT NULL,
        book_key INTEGER NOT NULL,
        position INTEGER NOT NULL,
        quest_key TEXT NOT NULL,
        quest_name TEXT NOT NULL,
        bonus_type INTEGER,
        bonus_value REAL,
        bonus_unit TEXT,
        PRIMARY KEY (journal_key, book_key, position)
    );

    -- Усі квести, що дають постійні бонуси сім'ї (у журналах і поза ними).
    CREATE TABLE IF NOT EXISTS game_family_bonuses (
        quest_key TEXT NOT NULL,
        reward_slot INTEGER NOT NULL,
        quest_name TEXT NOT NULL,
        giver TEXT,
        bonus_type INTEGER NOT NULL,
        bonus_value REAL NOT NULL,
        bonus_unit TEXT,
        PRIMARY KEY (quest_key, reward_slot)
    );

    CREATE TABLE IF NOT EXISTS game_data_import (
        id INTEGER PRIMARY KEY CHECK (id = 1),
        source TEXT NOT NULL,
        imported_at REAL NOT NULL,
        counts TEXT NOT NULL
    );
"""

QUEST_TABLE = 18
ENTITY_TABLE = 6
# Назви вузлів і міст за waypoint id (301 → Heidel); є й тоді, коли build не записав world.json.
NODE_TABLE = 29
FIELD_NAME = 0
# Назви навичок робітників, звірені в грі; за ними шукаємо таблицю навичок у loc.
WORKER_SKILL_ANCHORS = {
    1002: "Mass Production Knowledge", 1004: "Tool Knowledge", 1010: "Mount Knowledge", 1201: "Thrifty A",
    1403: "Work Supervisor C", 1501: "Lucky Guy A", 1503: "Lucky Guy C", 1603: "Wings C", 1902: "Craftsmanship",
    1909: "Ore Packing",
}
MIN_ANCHOR_MATCHES = 3
# Розмітка Pearl Abyss у рядках loc (<PAColor0xff…>…<PAOldColor>).
PA_MARKUP = re.compile(r"<PA[^>]*>")


class GameDataError(ValueError):
    pass


def initialize_schema(connection: sqlite3.Connection) -> None:
    connection.executescript(SCHEMA)
    columns = {row[1] for row in connection.execute("PRAGMA table_info(game_nodes)")}
    for column in ("x", "z"):
        if column not in columns:
            connection.execute(f"ALTER TABLE game_nodes ADD COLUMN {column} REAL")


def _clean(text: str) -> str:
    return PA_MARKUP.sub("", text).strip()


def _read_json(path: Path):
    with path.open(encoding="utf-8") as file:
        return json.load(file)


def _urn_id(value) -> int | None:
    """Ключ із посилання extractor: "urn::knowledge:theme:10001" → 10001."""
    if isinstance(value, dict):
        value = value.get("urn")
    if not isinstance(value, str):
        return None
    tail = value.rsplit(":", 1)[-1]
    return int(tail) if tail.isdigit() else None


class _Loc:
    """Таблиці loc: {таблиця: {id: {key1: текст}}}; читаються ліниво з locs/ або з loc_<мова>.json."""

    def __init__(self, directory: Path) -> None:
        self._dir = directory / "locs"
        dumps = sorted(directory.glob("loc_*.json"))
        self._dump_path = dumps[0] if dumps else None
        self._dump: dict | None = None

    def available(self) -> bool:
        return self._dir.is_dir() or self._dump_path is not None

    def table_ids(self) -> list[int]:
        if self._dir.is_dir():
            return sorted(int(p.stem) for p in self._dir.glob("*.json") if p.stem.isdigit())
        return sorted(int(k) for k in self._load_dump())

    def table(self, table_id: int) -> dict:
        path = self._dir / f"{table_id}.json"
        if path.is_file():
            return _read_json(path)
        if self._dump_path is not None:
            return self._load_dump().get(str(table_id), {})
        return {}

    def _load_dump(self) -> dict:
        if self._dump is None:
            self._dump = _read_json(self._dump_path) if self._dump_path else {}
        return self._dump


def _names(table: dict) -> dict[int, str]:
    """id → назва (поле 0) з таблиці loc."""
    out = {}
    for id_text, fields in table.items():
        name = fields.get(str(FIELD_NAME)) if isinstance(fields, dict) else None
        if name and id_text.isdigit():
            cleaned = _clean(name)
            if cleaned and cleaned != "<null>":
                out[int(id_text)] = cleaned
    return out


# Посилання знання на розділ: молодші 16 біт — номер розділу, старші — прапорці. Знань із прапорцем
# 0x100 у книзі знань гри немає (звірено з bdocodex: 373 таких, жодне не показується); прапорець 1 — звичайні.
# Розділ, де прихованих знань більше, ніж видимих, — службовий («None», «People of the Black Desert»): у грі
# його немає, як і кількох видимих знань у ньому.
THEME_MASK = 0xFFFF
HIDDEN_ENTRY_FLAG = 0x100


def _knowledge(directory: Path) -> tuple[list[tuple], list[tuple]] | None:
    path = directory / "knowledge.json"
    if not path.is_file():
        return None
    data = _read_json(path)

    visible: list[tuple[int, int, str, str | None]] = []
    hidden: dict[int, int] = {}
    for entry in data.get("entries") or []:
        reference = _urn_id(entry.get("theme"))
        name = _clean(entry.get("name") or "")
        if reference is None or not name:
            continue
        theme = reference & THEME_MASK
        if (reference >> 16) & HIDDEN_ENTRY_FLAG:
            hidden[theme] = hidden.get(theme, 0) + 1
        else:
            visible.append((int(entry["key"]), theme, name, _acquisition(entry.get("acquisition"))))
    shown = {theme: 0 for _, theme, _, _ in visible}
    for _, theme, _, _ in visible:
        shown[theme] += 1

    positions: dict[int, int] = {}
    entries = []
    # Порядок знань у розділі — як у файлі: так їх показує гра.
    for key, theme, name, acquisition in visible:
        if hidden.get(theme, 0) > shown[theme]:
            continue
        position = positions.get(theme, 0)
        positions[theme] = position + 1
        entries.append((key, theme, name, position, acquisition))

    themes = {int(t["key"]): t for t in data.get("themes") or []}
    parents = {key: _urn_id(theme.get("parent")) or 0 for key, theme in themes.items()}
    # Розділ лишаємо, лише якщо в ньому чи в підрозділах є знання: порожні (≈100) у грі не показуються.
    filled: set[int] = set()
    for theme in positions:
        while theme and theme not in filled and theme in themes:
            filled.add(theme)
            theme = parents[theme]

    # Розділи одного рівня гра впорядковує за номером (Ecology: Eastern Balenos 10010, Serendia 10020, …).
    siblings: dict[int, int] = {}
    categories = []
    for key in sorted(filled):
        parent = parents[key]
        position = siblings.get(parent, 0)
        siblings[parent] = position + 1
        categories.append((key, _clean(themes[key].get("name") or str(key)), parent, position))
    return categories, entries


def _acquisition(text) -> str | None:
    """«Де взяти» з вікна знань гри; «????» гра показує, поки знання приховане, — це не підказка."""
    if not isinstance(text, str):
        return None
    cleaned = "\n".join(line.strip() for line in _clean(text).splitlines() if line.strip())
    return cleaned if cleaned and set(cleaned) != {"?"} else None


def _world(directory: Path) -> tuple[dict[int, str], list[tuple]]:
    """Назви ввімкнених вузлів і рядки game_nodes з world.json."""
    path = directory / "world.json"
    if not path.is_file():
        return {}, []
    world = _read_json(path)
    territories = {t.get("index"): _clean(t.get("name") or "") for t in world.get("territories") or []}
    names: dict[int, str] = {}
    rows = []
    for node in world.get("nodes") or []:
        if not node.get("name") or not node.get("enabled", True):
            continue
        key = int(node["key"])
        names[key] = _clean(node["name"])
        products = [i for i in (_urn_id(u) for u in (node.get("products") or {}).get("urns") or []) if i]
        x, z = _ground(node.get("position"))
        rows.append((key, names[key], territories.get(_urn_id(node.get("territory"))) or None,
                     _urn_id(node.get("managerNode")), node.get("contribution"), json.dumps(products), x, z))
    return names, rows


def _ground(position) -> tuple[float | None, float | None]:
    """(x, z) зі світової точки extractor [x, висота, z]."""
    if isinstance(position, list) and len(position) == 3:
        return float(position[0]), float(position[2])
    return None, None


def _quest_rows(directory: Path) -> list[tuple]:
    path = directory / "quests.json"
    if not path.is_file():
        return []
    rows = []
    for quest in _read_json(path):
        if not quest.get("id") or not quest.get("name"):
            continue
        rows.append((quest["id"], _clean(quest["name"]), _clean(quest.get("giver") or "") or None,
                     _clean(quest.get("objective") or "").strip(";") or None,
                     _clean(quest.get("desc") or "") or None,
                     (quest.get("conditions") or {}).get("acceptDsl")))
    return rows


def _journal_rows(directory: Path) -> tuple[list, list, list, list] | None:
    path = directory / "adventure_journals.json"
    if not path.is_file():
        return None
    data = _read_json(path)
    bonuses = []
    for reward in data.get("bonuses") or []:
        quest, bonus = reward.get("quest") or {}, reward.get("bonus") or {}
        if quest.get("id") and bonus.get("type") is not None:
            bonuses.append((quest["id"], reward.get("rewardSlot") or 0, _clean(quest.get("name") or quest["id"]),
                            _clean(quest.get("giver") or "") or None, bonus["type"], bonus.get("value") or 0,
                            bonus.get("unit")))
    journals, books, pages = [], [], []
    for j_pos, journal in enumerate(data.get("journals") or []):
        jk = int(journal["key"])
        journals.append((jk, _clean(journal.get("name") or str(jk)), _clean(journal.get("description") or "") or None,
                         j_pos))
        for b_pos, book in enumerate(journal.get("books") or []):
            bk = int(book["key"])
            books.append((jk, bk, _clean(book.get("name") or str(bk)), _clean(book.get("requirement") or "") or None,
                          b_pos))
            for p_pos, page in enumerate(book.get("pages") or []):
                quest = page.get("quest") or {}
                bonus = page.get("bonus") or {}
                pages.append((jk, bk, p_pos, quest.get("id"), _clean(quest.get("name") or quest.get("id") or ""),
                              bonus.get("type"), bonus.get("value"), bonus.get("unit")))
    return journals, books, pages, bonuses


def _npcs(directory: Path) -> list[tuple]:
    """NPC, що стоять у світі: (id, ім'я, титул, район, x, z) — за першою точкою з npcs.json."""
    path = directory / "npcs.json"
    if not path.is_file():
        return []
    rows = []
    for npc in _read_json(path):
        spawn = next((s for s in npc.get("spawns") or [] if _ground(s.get("pos"))[0] is not None), None)
        if spawn is None or not npc.get("name"):
            continue
        x, z = _ground(spawn["pos"])
        title = _clean(npc.get("title") or "").strip("<>") or None
        rows.append((int(npc["id"]), _clean(npc["name"]), title, spawn.get("regionName"), x, z))
    return rows


def _knowledge_npcs(directory: Path, placed: set[int]) -> list[tuple[int, int]]:
    """(знання, NPC): знання посилається на персонажа, а той — на NPC, які стоять у світі."""
    knowledge, characters = directory / "knowledge.json", directory / "characters.json"
    if not knowledge.is_file() or not characters.is_file():
        return []
    entities = {
        c["urn"]: [e["id"] for e in c.get("entities") or [] if e.get("id") in placed]
        for c in _read_json(characters) if c.get("urn")
    }
    links = []
    for entry in _read_json(knowledge).get("entries") or []:
        npcs = entities.get(entry.get("character")) or []
        if npcs:
            links.append((int(entry["key"]), npcs[0]))
    return links


def _items(directory: Path) -> list[tuple]:
    path = directory / "items.json"
    if not path.is_file():
        return []
    data = _read_json(path)
    items = data.values() if isinstance(data, dict) else data
    out = []
    for item in items:
        if not isinstance(item, dict) or item.get("ghost") or not item.get("name"):
            continue
        grade = item.get("grade")
        out.append((int(item["id"]), _clean(item["name"]), grade if isinstance(grade, int) else 0))
    return out


def _quests(loc: _Loc) -> dict[str, str]:
    out = {}
    for group, fields in loc.table(QUEST_TABLE).items():
        if not group.isdigit() or not isinstance(fields, dict):
            continue
        for key1, text in fields.items():
            key = int(key1)
            if key >> 24 == FIELD_NAME and text and text != "<null>":
                out[f"{group}-{key & 0xFFFFFF}"] = _clean(text)
    return out


def _worker_skill_table(loc: _Loc) -> dict[int, str]:
    best: tuple[int, dict[int, str]] = (0, {})
    for table_id in loc.table_ids():
        names = _names(loc.table(table_id))
        matches = sum(1 for k, v in WORKER_SKILL_ANCHORS.items() if names.get(k) == v)
        if matches > best[0]:
            best = (matches, names)
    return best[1] if best[0] >= MIN_ANCHOR_MATCHES else {}


def import_directory(connection: sqlite3.Connection, directory: str | Path) -> dict:
    directory = Path(directory).expanduser()
    if not directory.is_dir():
        raise GameDataError(f"Папки не знайдено: {directory}")
    loc = _Loc(directory)
    knowledge = _knowledge(directory)
    outputs = ("world.json", "quests.json", "adventure_journals.json")
    if knowledge is None and not loc.available() and not any((directory / name).is_file() for name in outputs):
        raise GameDataError(
            "У папці немає виводу bdo-data-extractor (knowledge.json, world.json, locs/ або loc_<мова>.json)")

    counts: dict[str, int] = {}
    names: list[tuple[str, str, str]] = []
    if knowledge is not None:
        counts.update(knowledge_names.replace(connection, *knowledge))
    # world.json знає лише ввімкнені вузли; решту назв доповнює таблиця loc.
    world_names, world_nodes = _world(directory)
    nodes = {**_names(loc.table(NODE_TABLE)), **world_names}
    if world_nodes:
        connection.execute("DELETE FROM game_nodes")
        connection.executemany(
            "INSERT INTO game_nodes (node_id, name, territory, manager_id, contribution, products, x, z)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            world_nodes,
        )
    quests = _quest_rows(directory)
    if quests:
        connection.execute("DELETE FROM game_quests")
        connection.executemany("INSERT OR REPLACE INTO game_quests VALUES (?, ?, ?, ?, ?, ?)", quests)
        counts["quest_details"] = len(quests)
    journals = _journal_rows(directory)
    if journals:
        for table in ("game_journals", "game_journal_books", "game_journal_pages", "game_family_bonuses"):
            connection.execute(f"DELETE FROM {table}")
        connection.executemany("INSERT OR REPLACE INTO game_family_bonuses VALUES (?, ?, ?, ?, ?, ?, ?)", journals[3])
        connection.executemany("INSERT INTO game_journals VALUES (?, ?, ?, ?)", journals[0])
        connection.executemany("INSERT INTO game_journal_books VALUES (?, ?, ?, ?, ?)", journals[1])
        connection.executemany("INSERT INTO game_journal_pages VALUES (?, ?, ?, ?, ?, ?, ?, ?)", journals[2])
        counts["journals"] = len(journals[0])
    npcs = _npcs(directory)
    if npcs:
        connection.execute("DELETE FROM game_npcs")
        connection.executemany("INSERT INTO game_npcs VALUES (?, ?, ?, ?, ?, ?)", npcs)
        links = _knowledge_npcs(directory, {row[0] for row in npcs})
        connection.execute("DELETE FROM knowledge_npc")
        connection.executemany("INSERT OR IGNORE INTO knowledge_npc VALUES (?, ?)", links)
        counts.update(npcs=len(npcs), knowledge_npcs=len(links))
    names +=[("node", str(k), v) for k, v in nodes.items()]
    counts["nodes"] = len(nodes)
    items = _items(directory)
    if items:
        connection.executemany(
            """
            INSERT INTO items (item_id, name, grade) VALUES (?, ?, ?)
            ON CONFLICT (item_id) DO UPDATE SET name = excluded.name, grade = excluded.grade,
                fetched_at = CURRENT_TIMESTAMP
            """,
            items,
        )
    counts["items"] = len(items)
    if loc.available():
        quests = _quests(loc)
        characters = _names(loc.table(ENTITY_TABLE))
        skills = _worker_skill_table(loc)
        names += [("quest", k, v) for k, v in quests.items()]
        names += [("character", str(k), v) for k, v in characters.items()]
        names += [("worker_skill", str(k), v) for k, v in skills.items()]
        counts.update(quests=len(quests), characters=len(characters), worker_skills=len(skills))

    kinds = {kind for kind, _, _ in names}
    for kind in kinds:
        connection.execute("DELETE FROM game_names WHERE kind = ?", (kind,))
    connection.executemany("INSERT OR REPLACE INTO game_names (kind, key, name) VALUES (?, ?, ?)", names)
    connection.execute(
        """
        INSERT INTO game_data_import (id, source, imported_at, counts) VALUES (1, ?, ?, ?)
        ON CONFLICT (id) DO UPDATE SET source = excluded.source, imported_at = excluded.imported_at,
            counts = excluded.counts
        """,
        (str(directory), time.time(), json.dumps(counts)),
    )
    return counts


def status(connection: sqlite3.Connection) -> dict | None:
    row = connection.execute("SELECT source, imported_at, counts FROM game_data_import WHERE id = 1").fetchone()
    if row is None:
        return None
    return {"source": row["source"], "imported_at": row["imported_at"], "counts": json.loads(row["counts"])}


REDIRECTS_FILE = "asset_redirects.json"
# asset_redirects.json має ~85 тис. записів; читаємо раз і перечитуємо, лише коли файл змінився.
_redirects_cache: dict[Path, tuple[float, dict[str, str]]] = {}


def images(connection: sqlite3.Connection) -> dict[str, bool]:
    """Які картинки є в папці імпорту (extractor `icons` / `knowledge-icons`)."""
    redirects = _redirects(_source(connection))
    values = redirects.values()
    return {
        "items": any(v.startswith("icons/") for v in values),
        "knowledge": any(v.startswith("knowledge_icons/") for v in values),
    }


def item_icon(connection: sqlite3.Connection, item_id: int) -> Path | None:
    return _image(connection, f"urn::item:{item_id}")


def knowledge_image(connection: sqlite3.Connection, knowledge_id: int) -> Path | None:
    return _image(connection, f"urn::knowledge:entry:{knowledge_id}")


def _source(connection: sqlite3.Connection) -> Path | None:
    row = connection.execute("SELECT source FROM game_data_import WHERE id = 1").fetchone()
    return Path(row[0]) if row else None


def _redirects(source: Path | None) -> dict[str, str]:
    if source is None:
        return {}
    path = source / REDIRECTS_FILE
    try:
        mtime = path.stat().st_mtime
    except OSError:
        return {}
    cached = _redirects_cache.get(path)
    if cached is None or cached[0] != mtime:
        data = _read_json(path)
        cached = (mtime, data if isinstance(data, dict) else {})
        _redirects_cache[path] = cached
    return cached[1]


def _image(connection: sqlite3.Connection, urn: str) -> Path | None:
    source = _source(connection)
    relative = _redirects(source).get(urn)
    if source is None or not isinstance(relative, str):
        return None
    base = source.resolve()
    path = (base / relative).resolve()
    # Шлях з asset_redirects.json не повинен вивести за межі папки імпорту.
    if not path.is_relative_to(base) or not path.is_file():
        return None
    return path


def node_details(connection: sqlite3.Connection, node_ids: list[int]) -> dict[int, dict]:
    """Подробиці вузлів з world.json (порожньо, доки його не імпортовано)."""
    rows = {row["node_id"]: row for row in connection.execute("SELECT * FROM game_nodes")}
    items = dict(connection.execute("SELECT item_id, name FROM items WHERE name IS NOT NULL").fetchall())
    out = {}
    for node_id in node_ids:
        row = rows.get(node_id)
        if row is None:
            continue
        out[node_id] = {
            "territory": row["territory"],
            "manager_id": row["manager_id"],
            "contribution": row["contribution"],
            "products": [items.get(i, f"#{i}") for i in json.loads(row["products"])],
        }
    return out


# Бонуси сім'ї за сторінки журналів (тип з extractor, src/model/enums/family_stat_types.yml).
FAMILY_STATS = {
    0: "Усі AP", 1: "Усі DP", 2: "Макс. HP", 3: "Макс. MP", 4: "Макс. витривалість", 5: "Вантажопідйомність",
    6: "Слоти інвентаря", 7: "Влучність", 8: "Ухилення", 9: "Шанс заточування",
    10: "Додатковий ліміт шансу заточування", 11: "Ліміт стаку шансу заточування",
}
QUEST_REQUIRED = re.compile(r"(?<![!\w])clearquest\((\d+),\s*(\d+)\)", re.IGNORECASE)
DISABLED_LEVEL = 100
QUEST_LEVEL = re.compile(r"getLevel\(\)\s*(>=|>)\s*(\d+)", re.IGNORECASE)


def _bonus(type_: int | None, value: float | None, unit: str | None) -> dict | None:
    if type_ is None or value is None:
        return None
    return {"type": type_, "label": FAMILY_STATS.get(type_, f"Бонус #{type_}"), "value": value, "unit": unit}


def journals(connection: sqlite3.Connection, status: dict[str, str]) -> list[dict]:
    """Журнали пригод з прогресом: сторінка виконана, відкрита або ще недоступна."""
    books: dict[int, list] = {}
    for book in connection.execute("SELECT * FROM game_journal_books ORDER BY journal_key, position"):
        books.setdefault(book["journal_key"], []).append({
            "book_key": book["book_key"], "name": book["name"], "requirement": book["requirement"], "pages": [],
        })
    index = {(j, b["book_key"]): b for j, items in books.items() for b in items}
    for page in connection.execute("SELECT * FROM game_journal_pages ORDER BY journal_key, book_key, position"):
        book = index.get((page["journal_key"], page["book_key"]))
        if book is not None:
            book["pages"].append({
                "quest_key": page["quest_key"], "name": page["quest_name"],
                "status": status.get(page["quest_key"], "locked"),
                "bonus": _bonus(page["bonus_type"], page["bonus_value"], page["bonus_unit"]),
            })
    out = []
    for journal in connection.execute("SELECT * FROM game_journals ORDER BY position"):
        items = books.get(journal["journal_key"], [])
        pages = [p for b in items for p in b["pages"]]
        for book in items:
            book["done"] = sum(p["status"] == "done" for p in book["pages"])
        out.append({
            "journal_key": journal["journal_key"], "name": journal["name"], "description": journal["description"],
            "done": sum(p["status"] == "done" for p in pages), "total": len(pages), "books": items,
        })
    return out


def family_bonuses(connection: sqlite3.Connection, status: dict[str, str]) -> list[dict]:
    """Постійні бонуси сім'ї за квести: усього, отримано (квест виконано) і що ще лишилось узяти."""
    # Квест бонусу може бути сторінкою журналу — тоді сторінка посилається на нього.
    pages = {row[0]: (row[1], row[2]) for row in connection.execute(
        "SELECT quest_key, journal_key, book_key FROM game_journal_pages")}
    totals: dict[int, dict] = {}
    for row in connection.execute("SELECT * FROM game_family_bonuses ORDER BY bonus_type, quest_name"):
        bonus = _bonus(row["bonus_type"], row["bonus_value"], row["bonus_unit"])
        total = totals.setdefault(row["bonus_type"], {**bonus, "value": 0, "gained": 0, "missing": []})
        total["value"] += row["bonus_value"]
        if status.get(row["quest_key"]) == "done":
            total["gained"] += row["bonus_value"]
        else:
            journal, book = pages.get(row["quest_key"], (None, None))
            total["missing"].append({"quest_key": row["quest_key"], "name": row["quest_name"], "giver": row["giver"],
                                     "value": row["bonus_value"], "status": status.get(row["quest_key"], "locked"),
                                     "journal_key": journal, "book_key": book})
    return list(totals.values())


def search_quests(connection: sqlite3.Connection, status: dict[str, str], text: str, limit: int = 60) -> list[dict]:
    """Квести за назвою, NPC чи ключем, з вимогами: попередні квести й рівень з умов взяття."""
    pattern = f"%{text.strip()}%"
    rows = connection.execute(
        "SELECT * FROM game_quests WHERE name LIKE ? OR giver LIKE ? OR quest_key = ? ORDER BY name LIMIT ?",
        (pattern, pattern, text.strip(), limit),
    ).fetchall()
    names = dict(connection.execute("SELECT quest_key, name FROM game_quests").fetchall()) if rows else {}
    out = []
    for row in rows:
        dsl = row["accept_dsl"] or ""
        required = [k for k in dict.fromkeys(f"{g}-{i}" for g, i in QUEST_REQUIRED.findall(dsl))
                    if k != row["quest_key"]]
        levels = [int(n) + (1 if op == ">" else 0) for op, n in QUEST_LEVEL.findall(dsl)]
        out.append({
            "quest_key": row["quest_key"], "name": row["name"], "giver": row["giver"],
            "objective": row["objective"], "description": row["description"],
            "status": status.get(row["quest_key"], "unknown"),
            "min_level": min(levels) if levels else None,
            # Умова «рівень понад 99» недосяжна: так клієнт вимикає старі й подієві квести.
            "disabled": bool(levels) and min(levels) >= DISABLED_LEVEL,
            # «<or>» у DSL розділяє варіанти, тож попередні квести — це можливі, а не всі обов'язкові.
            "alternatives": "<or>" in dsl,
            "requires": [{"quest_key": k, "name": names.get(k, k), "status": status.get(k, "unknown")}
                         for k in required[:12]],
        })
    return out


# Плитки карти, як у грі: extractor `worldmap-files` пише <шар>/<z>/<x>/<y>.webp і meta.json на шар.
TILES_DIR = "worldmap-files"
MAP_LAYERS = ("world", "morningland")


def map_layers(connection: sqlite3.Connection) -> list[dict]:
    """meta.json кожного шару карти, що є в папці імпорту (порожньо, доки плиток немає)."""
    source = _source(connection)
    layers = []
    for name in MAP_LAYERS:
        meta = source / TILES_DIR / name / "meta.json" if source else None
        if meta and meta.is_file():
            layers.append({"name": name, **_read_json(meta)})
    return layers


def _layer_of(layers: list[dict], x: float, z: float) -> str | None:
    """Шар, сітка плиток якого містить точку; Ранкова Країна — окремий шар зі своєю сіткою."""
    for layer in layers:
        size = layer["unitsPerTile"]
        grid = layer["grid"]
        if grid["xmin"] <= x // size <= grid["xmax"] and grid["ymin"] <= z // size <= grid["ymax"]:
            return layer["name"]
    return None


def map_data(connection: sqlite3.Connection, invested: set[int], gained: set[int]) -> dict | None:
    """Карта: усі вузли (вкладені позначено) і NPC, у яких можна взяти ще не зібрані знання.
    Координати світові (x, z у см гри); None, доки плиток карти немає."""
    layers = map_layers(connection)
    if not layers:
        return None

    nodes = []
    for node in connection.execute("SELECT node_id, name, territory, manager_id, x, z FROM game_nodes "
                                   "WHERE x IS NOT NULL"):
        layer = _layer_of(layers, node["x"], node["z"])
        if layer:
            nodes.append({"node_id": node["node_id"], "name": node["name"], "territory": node["territory"],
                          "sub": node["manager_id"] is not None, "invested": node["node_id"] in invested,
                          "layer": layer, "x": node["x"], "z": node["z"]})

    npcs: dict[int, dict] = {}
    for link in connection.execute(
        """
        SELECT k.knowledge_id, n.name AS knowledge, n.acquisition, c.name AS category,
               p.npc_id, p.name, p.title, p.region, p.x, p.z
        FROM knowledge_npc k
        JOIN knowledge_names n USING (knowledge_id)
        JOIN knowledge_categories c USING (category_id)
        JOIN game_npcs p USING (npc_id)
        """
    ):
        if link["knowledge_id"] in gained:
            continue
        layer = _layer_of(layers, link["x"], link["z"])
        if not layer:
            continue
        npc = npcs.setdefault(link["npc_id"], {
            "npc_id": link["npc_id"], "name": link["name"], "title": link["title"], "region": link["region"],
            "layer": layer, "x": link["x"], "z": link["z"], "knowledge": [],
        })
        npc["knowledge"].append({"knowledge_id": link["knowledge_id"], "name": link["knowledge"],
                                 "category": link["category"], "acquisition": link["acquisition"]})
    return {
        "layers": layers,
        "nodes": nodes,
        "npcs": sorted(npcs.values(), key=lambda n: (-len(n["knowledge"]), n["name"])),
    }


def map_tile(connection: sqlite3.Connection, layer: str, z: int, x: int, y: int) -> Path | None:
    source = _source(connection)
    if source is None or layer not in MAP_LAYERS:
        return None
    path = source / TILES_DIR / layer / str(z) / str(x) / f"{y}.webp"
    return path if path.is_file() else None


def lookup(connection: sqlite3.Connection, kind: str) -> dict[str, str]:
    return dict(connection.execute("SELECT key, name FROM game_names WHERE kind = ?", (kind,)).fetchall())
