"""BDO Companion - Model Context Protocol (MCP) Server.

Надає AI-асистенту прямий доступ до локальної бази даних BDO Assistant (SQLite):
- Збільшення максимальної Енергії (Energy): пошук категорій з мінімальною кількістю відсутніх знань,
  підказки з координатами NPC та локаціями.
- Збільшення та аудит Очок Впливу (CP): статус CP, аудит вкладених вузлів, розрахунок потенціалу
  кулінарії (Witch's Delicacy) з наявних на складах інгредієнтів.
- Пошук предметів та огляд акаунта.
"""

from contextlib import contextmanager
import os
from pathlib import Path
import sqlite3
from typing import Any

from mcp.server.mcpserver import MCPServer

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = Path(os.environ.get("BDO_DB_PATH") or BASE_DIR / "bdo_assistant.db")

mcp = MCPServer(
    name="bdo-companion",
    version="1.0.0",
)


@contextmanager
def get_db():
    """Підключення до SQLite в режимі читання (read-only)."""
    # URI read-only гарантує паралельну роботу з FastAPI/треєм без блокувань
    db_uri = f"{DB_PATH.resolve().as_uri()}?mode=ro"
    connection = sqlite3.connect(db_uri, uri=True)
    connection.row_factory = sqlite3.Row
    try:
        yield connection
    finally:
        connection.close()


@mcp.tool()
def get_characters() -> list[dict[str, Any]]:
    """Отримати список усіх персонажів сім'ї з їхніми класами, рівнями, досвідом та славою сім'ї."""
    with get_db() as db:
        rows = db.execute("""
            SELECT character_id, nick, family, class_name, level, xp, xp_to_next,
                   fame_combat, fame_life, fame_third, slot, last_seen
            FROM characters
            ORDER BY level DESC, xp DESC
        """).fetchall()

        results = []
        for r in rows:
            results.append({
                "name": r["nick"],
                "family": r["family"],
                "class_name": r["class_name"],
                "level": r["level"],
                "experience": r["xp"],
                "experience_to_next": r["xp_to_next"],
                "slot": r["slot"],
                "family_fame": {
                    "combat": r["fame_combat"],
                    "life": r["fame_life"],
                    "special": r["fame_third"],
                },
            })
        return results


@mcp.tool()
def get_account_overview() -> dict[str, Any]:
    """Отримати загальний огляд акаунта: профіль персонажа, AP/DP, срібло, прогрес знань та CP."""
    with get_db() as db:
        profile = db.execute("SELECT * FROM profile WHERE id = 1").fetchone()
        contrib = db.execute("SELECT * FROM contribution WHERE id = 1").fetchone()
        learned_knowledge = db.execute("SELECT COUNT(*) FROM knowledge").fetchone()[0]
        total_names = db.execute("SELECT COUNT(*) FROM knowledge_names").fetchone()[0]
        invested_nodes = db.execute("SELECT COUNT(*) FROM nodes WHERE invested = 1").fetchone()[0]
        containers_count = db.execute("SELECT COUNT(*) FROM containers").fetchone()[0]
        holdings_count = db.execute("SELECT COUNT(*) FROM holdings").fetchone()[0]

        return {
            "profile": {
                "character_name": profile["character_name"] if profile else "Unknown",
                "character_class": profile["character_class"] if profile else "Unknown",
                "ap": profile["ap"] if profile else None,
                "dp": profile["dp"] if profile else None,
                "silver_billions": profile["silver_billions"] if profile else 0.0,
                "goal": profile["goal"] if profile else None,
            },
            "contribution_points": {
                "available": contrib["available"] if contrib else None,
                "total": contrib["total"] if contrib else None,
                "invested_nodes_count": invested_nodes,
            },
            "knowledge_progress": {
                "learned_count": learned_knowledge,
                "catalog_total": total_names,
            },
            "storage": {
                "tracked_containers": containers_count,
                "total_item_stacks": holdings_count,
            },
        }


@mcp.tool()
def get_energy_quick_wins(max_missing: int = 3, category_search: str = "") -> list[dict[str, Any]]:
    """Знайти категорії знань (Knowledge Categories), де до повного закриття групи бракує найменше знань.

    Закриття групи знань у BDO дає збільшення максимальної Енергії (Energy).
    Цей інструмент знаходить «low-hanging fruit» — категорії, де бракує від 1 до max_missing знань.

    Args:
        max_missing: Максимальна кількість пропущених знань у категорії (за замовчуванням 3).
        category_search: Необов'язковий фільтр за назвою категорії (наприклад, 'Serendia', 'Calpheon', 'Duvencrune').
    """
    with get_db() as db:
        query = """
            SELECT 
                c.category_id,
                c.name AS category_name,
                c.parent_id,
                COUNT(n.knowledge_id) AS total_count,
                COUNT(k.knowledge_id) AS learned_count,
                (COUNT(n.knowledge_id) - COUNT(k.knowledge_id)) AS missing_count
            FROM knowledge_categories c
            JOIN knowledge_names n ON c.category_id = n.category_id
            LEFT JOIN knowledge k ON n.knowledge_id = k.knowledge_id
            WHERE (:search = '' OR c.name LIKE '%' || :search || '%')
            GROUP BY c.category_id, c.name, c.parent_id
            HAVING missing_count > 0 AND missing_count <= :max_missing AND learned_count > 0
            ORDER BY missing_count ASC, learned_count DESC
            LIMIT 25
        """
        rows = db.execute(query, {"search": category_search.strip(), "max_missing": max_missing}).fetchall()

        parent_ids = {r["parent_id"] for r in rows if r["parent_id"] != 0}
        parent_names = {}
        if parent_ids:
            placeholders = ",".join("?" for _ in parent_ids)
            p_rows = db.execute(
                f"SELECT category_id, name FROM knowledge_categories WHERE category_id IN ({placeholders})",
                list(parent_ids),
            ).fetchall()
            parent_names = {pr["category_id"]: pr["name"] for pr in p_rows}

        results = []
        for r in rows:
            results.append({
                "category_id": r["category_id"],
                "category_name": r["category_name"],
                "parent_category": parent_names.get(r["parent_id"]),
                "learned_count": r["learned_count"],
                "total_count": r["total_count"],
                "missing_count": r["missing_count"],
                "completion_percent": round((r["learned_count"] / r["total_count"]) * 100, 1),
            })
        return results


@mcp.tool()
def get_missing_knowledge_details(category_id: int) -> dict[str, Any]:
    """Отримати детальний список пропущених знань для конкретної категорії з координатами та NPC.

    Args:
        category_id: ID категорії (можна отримати з get_energy_quick_wins).
    """
    with get_db() as db:
        cat = db.execute("SELECT category_id, name FROM knowledge_categories WHERE category_id = ?", (category_id,)).fetchone()
        if not cat:
            return {"error": f"Категорія з ID {category_id} не знайдена"}

        query = """
            SELECT 
                n.knowledge_id,
                n.name AS knowledge_name,
                n.acquisition,
                npc.npc_id,
                npc.name AS npc_name,
                npc.title AS npc_title,
                npc.region,
                npc.x, npc.z
            FROM knowledge_names n
            LEFT JOIN knowledge k ON n.knowledge_id = k.knowledge_id
            LEFT JOIN knowledge_npc kn ON n.knowledge_id = kn.knowledge_id
            LEFT JOIN game_npcs npc ON kn.npc_id = npc.npc_id
            WHERE n.category_id = ? AND k.knowledge_id IS NULL
            ORDER BY n.position ASC
        """
        rows = db.execute(query, (category_id,)).fetchall()

        missing = []
        for r in rows:
            loc = None
            if r["x"] is not None and r["z"] is not None:
                loc = {"x": round(r["x"], 1), "z": round(r["z"], 1), "region": r["region"]}

            missing.append({
                "knowledge_id": r["knowledge_id"],
                "name": r["knowledge_name"],
                "hint": r["acquisition"] or "Поговоріть з NPC або виконайте дію",
                "npc": {
                    "id": r["npc_id"],
                    "name": r["npc_name"],
                    "title": r["npc_title"],
                    "location": loc,
                } if r["npc_name"] else None,
            })

        return {
            "category_id": cat["category_id"],
            "category_name": cat["name"],
            "missing_total": len(missing),
            "missing_entries": missing,
        }


@mcp.tool()
def search_knowledge(query: str) -> list[dict[str, Any]]:
    """Пошук знання за назвою: перевірка чи воно вивчене, грейд (C/B/A/S), категорія та джерело.

    Args:
        query: Текст для пошуку (назва знання, монстра або NPC).
    """
    with get_db() as db:
        sql = """
            SELECT 
                n.knowledge_id,
                n.name AS knowledge_name,
                c.name AS category_name,
                k.level,
                n.acquisition,
                npc.name AS npc_name,
                npc.region
            FROM knowledge_names n
            JOIN knowledge_categories c ON n.category_id = c.category_id
            LEFT JOIN knowledge k ON n.knowledge_id = k.knowledge_id
            LEFT JOIN knowledge_npc kn ON n.knowledge_id = kn.knowledge_id
            LEFT JOIN game_npcs npc ON kn.npc_id = npc.npc_id
            WHERE n.name LIKE '%' || ? || '%'
            LIMIT 20
        """
        rows = db.execute(sql, (query.strip(),)).fetchall()
        grades = {1: "C", 2: "B", 3: "A", 4: "A+", 5: "S"}

        results = []
        for r in rows:
            results.append({
                "knowledge_id": r["knowledge_id"],
                "name": r["knowledge_name"],
                "category": r["category_name"],
                "is_learned": r["level"] is not None,
                "grade": grades.get(r["level"], str(r["level"])) if r["level"] is not None else None,
                "hint": r["acquisition"],
                "npc": f"{r['npc_name']} ({r['region']})" if r["npc_name"] else None,
            })
        return results


@mcp.tool()
def get_cp_status() -> dict[str, Any]:
    """Отримати детальний статус Contribution Points (Очок Впливу): скільки є, скільки вільно, витрати на вузли."""
    with get_db() as db:
        contrib = db.execute("SELECT * FROM contribution WHERE id = 1").fetchone()
        if not contrib:
            return {"error": "Дані про Contribution Points ще не завантажені (увійдіть у гру з активним агентом)"}

        node_stats = db.execute("""
            SELECT 
                COUNT(*) AS total_invested_nodes,
                COALESCE(SUM(gn.contribution), 0) AS total_cp_in_nodes
            FROM nodes n
            LEFT JOIN game_nodes gn ON n.node_id = gn.node_id
            WHERE n.invested = 1
        """).fetchone()

        return {
            "total_cp": contrib["total"],
            "available_cp": contrib["available"],
            "used_cp": contrib["total"] - contrib["available"],
            "invested_nodes_count": node_stats["total_invested_nodes"],
            "cp_spent_on_nodes": node_stats["total_cp_in_nodes"],
            "current_experience": contrib["experience"],
        }


@mcp.tool()
def list_invested_nodes(territory: str = "") -> list[dict[str, Any]]:
    """Список усіх активних вузлів, куди зараз вкладено очки CP.

    Дозволяє провести аудит і знайти вузли, які більше не використовуються, щоб повернути CP.

    Args:
        territory: Необов'язковий фільтр за територією (наприклад, 'Balenos', 'Serendia', 'Calpheon', 'Mediah', 'Valencia', 'Kamasylvia', 'Drieghan').
    """
    with get_db() as db:
        sql = """
            SELECT 
                n.node_id,
                COALESCE(gn.name, 'Вузол #' || n.node_id) AS node_name,
                gn.territory,
                gn.contribution AS cp_cost,
                gn.products,
                gn.x, gn.z
            FROM nodes n
            LEFT JOIN game_nodes gn ON n.node_id = gn.node_id
            WHERE n.invested = 1
              AND (:territory = '' OR gn.territory LIKE '%' || :territory || '%')
            ORDER BY gn.territory ASC, cp_cost DESC
        """
        rows = db.execute(sql, {"territory": territory.strip()}).fetchall()
        results = []
        for r in rows:
            results.append({
                "node_id": r["node_id"],
                "name": r["node_name"],
                "territory": r["territory"] or "Unknown",
                "cp_cost": r["cp_cost"] if r["cp_cost"] is not None else "Місто/Базовий (0 CP)",
                "location": {"x": round(r["x"], 1), "z": round(r["z"], 1)} if r["x"] is not None else None,
            })
        return results


@mcp.tool()
def get_cooking_cp_potential() -> dict[str, Any]:
    """Аналіз складів на інгредієнти для кулінарії під прокачування CP (через Witch's Delicacy / Делікатес відьми).

    Перевіряє наявність зернових культур, овочів, оцту та готових Witch's Delicacy,
    а також розраховує, скільки крафтів оцту або маринованих овочів можна виконати.
    """
    with get_db() as db:
        # 1. Поточні запаси Witch's Delicacy
        delicacy = db.execute("""
            SELECT c.name AS container, SUM(h.quantity) AS qty
            FROM holdings h
            JOIN items i ON h.item_id = i.item_id
            JOIN containers c ON h.container_id = c.id
            WHERE i.name LIKE "%Witch's Delicacy%"
            GROUP BY c.name
        """).fetchall()
        total_delicacies = sum(d["qty"] for d in delicacy)

        # 2. Зернові культури (Wheat, Barley, Potato, Corn, Sweet Potato)
        grains = db.execute("""
            SELECT i.name, c.name AS container, SUM(h.quantity) AS qty
            FROM holdings h
            JOIN items i ON h.item_id = i.item_id
            JOIN containers c ON h.container_id = c.id
            WHERE i.name IN ('Wheat', 'Barley', 'Potato', 'Corn', 'Sweet Potato')
               OR i.name LIKE '%Wheat%' OR i.name LIKE '%Potato%'
            GROUP BY i.name, c.name
            ORDER BY qty DESC
        """).fetchall()
        total_grain = sum(g["qty"] for g in grains)

        # 3. Овочі / фрукти (Paprika, Tomato, Cabbage, Apple, Grape, Strawberry)
        produce = db.execute("""
            SELECT i.name, c.name AS container, SUM(h.quantity) AS qty
            FROM holdings h
            JOIN items i ON h.item_id = i.item_id
            JOIN containers c ON h.container_id = c.id
            WHERE i.name IN ('Paprika', 'Tomato', 'Cabbage', 'Pumpkin', 'Olive', 'Apple', 'Grape', 'Strawberry')
            GROUP BY i.name, c.name
            ORDER BY qty DESC
        """).fetchall()
        total_produce = sum(p["qty"] for p in produce)

        # 4. Вже готовий оцет (Vinegar)
        vinegar = db.execute("""
            SELECT c.name AS container, SUM(h.quantity) AS qty
            FROM holdings h
            JOIN items i ON h.item_id = i.item_id
            JOIN containers c ON h.container_id = c.id
            WHERE i.name = 'Vinegar'
            GROUP BY c.name
        """).fetchall()
        total_vinegar = sum(v["qty"] for v in vinegar)

        # Розрахунок потенціалу:
        # Рецепт Vinegar (Оцет): 1 Зерно + 1 Фрукт + 1 Дріжджі (Leavening Agent) + 1 Цукор (Sugar).
        # Дріжджі та цукор купуються у кухаря NPC за срібло в необмеженій кількості.
        vinegar_crafts_possible = min(total_grain, total_produce) if total_produce > 0 else total_grain

        # Орієнтовний шанс дропу Witch's Delicacy ~ 2.5% на крафт (близько 25 штук на 1000 крафтів)
        estimated_delicacies = int(vinegar_crafts_possible * 0.025)
        # 10 Witch's Delicacy = 900 Contribution EXP
        estimated_cp_exp = (estimated_delicacies // 10) * 900

        return {
            "current_delicacies": {
                "total": total_delicacies,
                "breakdown": [{"storage": d["container"], "quantity": d["qty"]} for d in delicacy],
                "ready_turn_ins_batches_of_10": total_delicacies // 10,
                "ready_cp_exp_gain": (total_delicacies // 10) * 900,
            },
            "inventory_resources": {
                "total_grain_count": total_grain,
                "grain_details": [{"item": g["name"], "storage": g["container"], "quantity": g["qty"]} for g in grains[:10]],
                "total_produce_fruits_vegetables": total_produce,
                "produce_details": [{"item": p["name"], "storage": p["container"], "quantity": p["qty"]} for p in produce[:10]],
                "existing_vinegar_count": total_vinegar,
            },
            "crafting_estimate": {
                "vinegar_crafts_possible": vinegar_crafts_possible,
                "estimated_delicacy_drops": estimated_delicacies,
                "estimated_cp_exp": estimated_cp_exp,
                "recipe_note": "Для оцту (Vinegar): 1 зерно + 1 фрукт/овоч + 1 дріжджі (NPC) + 1 цукор (NPC).",
            },
        }


@mcp.tool()
def search_inventory(item_name: str) -> list[dict[str, Any]]:
    """Знайти предмет на складах міст або в інвентарях персонажів.

    Args:
        item_name: Назва або частина назви предмета (наприклад, 'Caphras', 'Black Stone', 'Memory Fragment').
    """
    with get_db() as db:
        sql = """
            SELECT 
                i.item_id,
                i.name AS item_name,
                i.grade,
                h.enhancement,
                h.quantity,
                c.name AS container_name,
                c.kind AS container_kind,
                c.character
            FROM holdings h
            JOIN items i ON h.item_id = i.item_id
            JOIN containers c ON h.container_id = c.id
            WHERE i.name LIKE '%' || ? || '%'
            ORDER BY h.quantity DESC
            LIMIT 30
        """
        rows = db.execute(sql, (item_name.strip(),)).fetchall()
        results = []
        for r in rows:
            location = r["container_name"]
            if r["character"]:
                location = f"{r['container_name']} ({r['character']})"

            results.append({
                "item_id": r["item_id"],
                "name": r["item_name"],
                "enhancement": r["enhancement"] if r["enhancement"] > 0 else None,
                "quantity": r["quantity"],
                "location": location,
                "type": r["container_kind"],
            })
        return results


if __name__ == "__main__":
    mcp.run()
