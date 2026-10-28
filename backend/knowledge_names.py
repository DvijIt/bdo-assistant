"""Назви й розділи знань з файлу, який користувач сам зберіг зі сторінки bdocodex.com/us/knowledge/.

Сторінка вбудовує JSON `{"categories": …, "category_tree": …, "entries": …, "entry_tree": …}`;
id знань у ньому збігаються з id з трафіку гри. Мережею модуль нічого не завантажує.
"""

import html
import json
import sqlite3


SCHEMA = """
    CREATE TABLE IF NOT EXISTS knowledge_categories (
        category_id INTEGER PRIMARY KEY,
        name TEXT NOT NULL,
        parent_id INTEGER NOT NULL,        -- 0 для кореневих розділів
        position INTEGER NOT NULL
    );

    CREATE TABLE IF NOT EXISTS knowledge_names (
        knowledge_id INTEGER PRIMARY KEY,
        category_id INTEGER NOT NULL,
        name TEXT NOT NULL,
        position INTEGER NOT NULL
    );
"""

# Рівні знань у трафіку; звірено з грою: C=1, B=2, A=3, S=5. Букву для 4 ще не підтверджено.
GRADES = {1: "C", 2: "B", 3: "A", 5: "S"}
# Лише в цих кореневих розділах знання мають рівень; в інших 1 означає «без рівня».
GRADED_ROOTS = {"Ecology", "Trade"}
HIDDEN_CATEGORY = "None"


class KnowledgeImportError(ValueError):
    pass


def initialize_schema(connection: sqlite3.Connection) -> None:
    connection.executescript(SCHEMA)


def parse_page(text: str) -> tuple[list[tuple], list[tuple]]:
    """(розділи, знання) зі збереженої сторінки bdocodex."""
    start = text.find('{"categories":')
    if start < 0:
        raise KnowledgeImportError("У файлі немає даних знань: збережи сторінку bdocodex.com/us/knowledge/ повністю")
    try:
        data, _ = json.JSONDecoder().raw_decode(text, start)
        names = {int(k): html.unescape(v[0]) for k, v in data["categories"].items()}
        categories = [
            (child, names[child], int(parent), position)
            for parent, children in data["category_tree"].items()
            for position, child in enumerate(children)
            if child in names
        ]
        entries = []
        seen: set[int] = set()
        for category, ids in data["entry_tree"].items():
            for position, knowledge_id in enumerate(ids):
                entry = data["entries"].get(str(knowledge_id))
                # Кілька знань у дереві повторюються в тому самому розділі; лишаємо перше.
                if entry is not None and knowledge_id not in seen:
                    seen.add(knowledge_id)
                    entries.append((knowledge_id, int(category), html.unescape(entry[2]), position))
    except (KeyError, TypeError, ValueError, IndexError) as error:
        raise KnowledgeImportError(f"Неочікувана структура даних знань: {error!r}") from error
    if not entries:
        raise KnowledgeImportError("У файлі не знайдено жодного знання")
    return categories, entries


def import_page(connection: sqlite3.Connection, text: str) -> dict:
    return replace(connection, *parse_page(text))


def replace(connection: sqlite3.Connection, categories: list[tuple], entries: list[tuple]) -> dict:
    """Замінює дерево знань: розділи (id, назва, батько, позиція) і знання (id, розділ, назва, позиція)."""
    connection.execute("DELETE FROM knowledge_categories")
    connection.execute("DELETE FROM knowledge_names")
    connection.executemany("INSERT INTO knowledge_categories VALUES (?, ?, ?, ?)", categories)
    connection.executemany("INSERT INTO knowledge_names VALUES (?, ?, ?, ?)", entries)
    return {"categories": len(categories), "knowledge": len(entries)}


def _tree(connection: sqlite3.Connection):
    categories = {
        row["category_id"]: dict(row)
        for row in connection.execute("SELECT * FROM knowledge_categories ORDER BY parent_id, position")
    }
    children: dict[int, list[int]] = {}
    for category in categories.values():
        children.setdefault(category["parent_id"], []).append(category["category_id"])
    return categories, children


def _root_name(categories: dict, category_id: int) -> str | None:
    while category_id in categories and categories[category_id]["parent_id"] != 0:
        category_id = categories[category_id]["parent_id"]
    return categories.get(category_id, {}).get("name")


def grade(level: int | None, graded: bool) -> str | None:
    if level is None:
        return None
    if not graded:
        return "—"
    return GRADES.get(level, str(level))


def category_view(connection: sqlite3.Connection, parent_id: int) -> dict:
    """Підрозділи `parent_id` з прогресом (зібрано/усього) і знання самого розділу."""
    categories, children = _tree(connection)
    if parent_id and parent_id not in categories:
        return {"categories": [], "entries": []}
    names = list(connection.execute("SELECT knowledge_id, category_id, name, position FROM knowledge_names"))
    by_category: dict[int, list] = {}
    for row in names:
        by_category.setdefault(row["category_id"], []).append(row)
    levels = dict(connection.execute("SELECT knowledge_id, level FROM knowledge").fetchall())

    def count(category_id: int) -> tuple[int, int]:
        total = gained = 0
        for row in by_category.get(category_id, []):
            total += 1
            gained += row["knowledge_id"] in levels
        for child in children.get(category_id, []):
            child_total, child_gained = count(child)
            total += child_total
            gained += child_gained
        return total, gained

    rows = []
    for category_id in children.get(parent_id, []):
        # У клієнті є службовий розділ «None» з кількома незавершеними знаннями — у грі його не видно.
        if categories[category_id]["name"] == HIDDEN_CATEGORY:
            continue
        total, gained = count(category_id)
        rows.append({
            "category_id": category_id,
            "name": categories[category_id]["name"],
            "total": total,
            "gained": gained,
            "has_children": bool(children.get(category_id)),
        })
    graded = parent_id != 0 and _root_name(categories, parent_id) in GRADED_ROOTS
    entries = [
        {
            "knowledge_id": row["knowledge_id"],
            "name": row["name"],
            "gained": row["knowledge_id"] in levels,
            "level": levels.get(row["knowledge_id"]),
            "grade": grade(levels.get(row["knowledge_id"]), graded),
        }
        for row in sorted(by_category.get(parent_id, []), key=lambda r: r["position"])
    ]
    return {"categories": rows, "entries": entries}


def names_loaded(connection: sqlite3.Connection) -> int:
    return connection.execute("SELECT COUNT(*) FROM knowledge_names").fetchone()[0]


def graded_ids(connection: sqlite3.Connection) -> set[int] | None:
    """id знань з розділів, де є рівні; None, доки назви не імпортовано."""
    if not names_loaded(connection):
        return None
    categories, _ = _tree(connection)
    graded = {c for c in categories if _root_name(categories, c) in GRADED_ROOTS}
    return {row[0] for row in connection.execute("SELECT knowledge_id, category_id FROM knowledge_names")
            if row[1] in graded}
