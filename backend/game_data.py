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
        products TEXT NOT NULL          -- JSON-список item_id
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
        rows.append((key, names[key], territories.get(_urn_id(node.get("territory"))) or None,
                     _urn_id(node.get("managerNode")), node.get("contribution"), json.dumps(products)))
    return names, rows


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
    if knowledge is None and not loc.available() and not (directory / "world.json").is_file():
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
        connection.executemany("INSERT INTO game_nodes VALUES (?, ?, ?, ?, ?, ?)", world_nodes)
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


def lookup(connection: sqlite3.Connection, kind: str) -> dict[str, str]:
    return dict(connection.execute("SELECT key, name FROM game_names WHERE kind = ?", (kind,)).fetchall())
