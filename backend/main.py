
from contextlib import asynccontextmanager, contextmanager
import json
import os
from pathlib import Path
import sqlite3

from fastapi import Body, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from starlette.exceptions import HTTPException as StarletteHTTPException

import account
import agent as agent_module
import arsha
import snapshots
import game_data
import knowledge_names
import valuation


BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "bdo_assistant.db"
# Зібраний фронт (`npm run build` → out/); FastAPI роздає його сам, Node для запуску не потрібен.
FRONTEND_DIR = Path(os.environ.get("BDO_FRONTEND_DIR") or BASE_DIR.parent / "out")


@contextmanager
def get_connection():
    # `with sqlite3.connect()` лише комітить або відкочує транзакцію,
    # тому з'єднання закриваємо явно.
    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row
    try:
        with connection:
            yield connection
    finally:
        connection.close()


def initialize_database():
    with get_connection() as connection:
        connection.execute("""
            CREATE TABLE IF NOT EXISTS profile (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                character_name TEXT NOT NULL DEFAULT 'Мій персонаж',
                character_class TEXT NOT NULL DEFAULT 'Woosa',
                ap INTEGER NOT NULL DEFAULT 280,
                dp INTEGER NOT NULL DEFAULT 350,
                silver_billions REAL NOT NULL DEFAULT 12.5,
                goal TEXT NOT NULL DEFAULT 'gear'
            )
        """)

        connection.execute("""
            INSERT OR IGNORE INTO profile (id)
            VALUES (1)
        """)

        snapshots.initialize_schema(connection)
        valuation.initialize_schema(connection)
        account.initialize_schema(connection)
        knowledge_names.initialize_schema(connection)
        game_data.initialize_schema(connection)


def opcode_profile() -> Path | None:
    """Профіль опкодів bdo-toolkit для знімків інвентаря: BDO_OPCODE_PROFILE або backend/opcodes.local."""
    path = Path(os.environ.get("BDO_OPCODE_PROFILE") or BASE_DIR / "opcodes.local")
    return path if path.is_file() else None


def import_agent_snapshot(data: dict, character: str) -> dict:
    with get_connection() as connection:
        summary = snapshots.import_snapshot(connection, data, character)
    # Як і для ручного імпорту: недоступний arsha.io не відкочує вже збережений знімок.
    with get_connection() as connection:
        summary["missing_names"] = refresh_item_names(connection)
    return summary


# DB_PATH читається під час кожного з'єднання, тож тести можуть його підміняти.
agent = agent_module.Agent(
    lambda: get_connection(),
    inventory_profile=lambda: opcode_profile(),
    import_snapshot=lambda data, character: import_agent_snapshot(data, character),
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    initialize_database()
    if os.environ.get("BDO_AGENT_AUTOSTART") == "1":
        agent.start()
    yield
    agent.stop()


app = FastAPI(
    title="BDO Assistant API",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    # Dev-сервер Next може стартувати не на 3000, якщо порт зайнятий.
    allow_origin_regex=r"http://(localhost|127\.0\.0\.1):\d+",
    allow_credentials=False,
    allow_methods=["GET", "PUT", "POST"],
    allow_headers=["Content-Type"],
)


class ProfileUpdate(BaseModel):
    character_name: str = Field(min_length=1, max_length=100)
    character_class: str = Field(min_length=1, max_length=100)
    ap: int = Field(ge=0, le=10000)
    dp: int = Field(ge=0, le=10000)
    silver_billions: float = Field(ge=0, le=1_000_000_000)
    goal: str = Field(pattern=r"^(gear|silver|pve|life)$")


def profile_to_dict(row):
    return {
        "character_name": row["character_name"],
        "character_class": row["character_class"],
        "ap": row["ap"],
        "dp": row["dp"],
        "silver_billions": row["silver_billions"],
        "goal": row["goal"],
    }


@app.get("/api/health")
def health():
    return {"status": "ok", "service": "BDO Assistant API"}


@app.get("/api/profile")
def get_profile():
    with get_connection() as connection:
        row = connection.execute(
            "SELECT * FROM profile WHERE id = 1"
        ).fetchone()

    if row is None:
        raise HTTPException(status_code=404, detail="Profile not found")

    return profile_to_dict(row)


@app.put("/api/profile")
def update_profile(profile: ProfileUpdate):
    with get_connection() as connection:
        connection.execute(
            """
            UPDATE profile
            SET character_name = ?,
                character_class = ?,
                ap = ?,
                dp = ?,
                silver_billions = ?,
                goal = ?
            WHERE id = 1
            """,
            (
                profile.character_name,
                profile.character_class,
                profile.ap,
                profile.dp,
                profile.silver_billions,
                profile.goal,
            ),
        )

        row = connection.execute(
            "SELECT * FROM profile WHERE id = 1"
        ).fetchone()

    return profile_to_dict(row)


def refresh_item_names(connection):
    """Дотягує з arsha.io назви предметів, яких ще немає в кеші.

    Повертає кількість предметів, що лишилися без назви.
    """
    def missing_ids():
        return sorted(set(snapshots.missing_item_ids(connection)) | set(account.missing_gear_item_ids(connection)))

    missing = missing_ids()
    if missing:
        try:
            snapshots.save_items(connection, arsha.fetch_items(missing))
        except (OSError, ValueError):
            # arsha.io неофіційний і може не відповісти; назви дотягнемо пізніше.
            pass
    return len(missing_ids())


@app.get("/api/snapshots")
def get_snapshots():
    with get_connection() as connection:
        return snapshots.list_snapshots(connection)


@app.post("/api/snapshots", status_code=201)
def import_snapshot(data: dict = Body(...), character: str | None = None):
    with get_connection() as connection:
        if not character:
            character = connection.execute(
                "SELECT character_name FROM profile WHERE id = 1"
            ).fetchone()[0]

        try:
            summary = snapshots.import_snapshot(connection, data, character)
        except snapshots.DuplicateSnapshotError as error:
            raise HTTPException(status_code=409, detail=str(error))
        except snapshots.SnapshotError as error:
            raise HTTPException(status_code=422, detail=str(error))

    # Імпорт уже закомічено: недоступний arsha.io не має його відкотити.
    with get_connection() as connection:
        summary["missing_names"] = refresh_item_names(connection)

    return summary


@app.get("/api/holdings")
def get_holdings():
    with get_connection() as connection:
        containers = snapshots.current_holdings(connection)
        prices = valuation.unit_prices(connection)
        for container in containers:
            for holding in container["items"]:
                price = prices.get((holding["item_id"], holding["enhancement"]))
                holding["unit_price"] = price
                holding["value"] = None if price is None else price * holding["quantity"]

        return {
            "containers": containers,
            "missing_names": len(snapshots.missing_item_ids(connection)),
        }


@app.get("/api/account")
def get_account():
    with get_connection() as connection:
        return valuation.account_value(connection)


@app.post("/api/prices/refresh")
def refresh_prices(full: bool = False):
    # full=true перепитує й предмети, які раніше були поза ринком.
    with get_connection() as connection:
        item_ids = valuation.item_ids_to_price(connection, include_off_market=full)
        gear_ids = {row[0] for row in connection.execute("SELECT DISTINCT item_id FROM servant_gear")}
        # Результати рецептів, які можна зробити зі складів: без їхніх цін не видно вигоди.
        known_off_market = {row[0] for row in connection.execute("SELECT item_id FROM prices WHERE base_price = 0")}
        outputs = {r["output_id"] for r in game_data.craftable(connection, snapshots.current_holdings(connection), {})}
        item_ids = sorted(set(item_ids) | gear_ids | (outputs if full else outputs - known_off_market))

    try:
        entries = arsha.fetch_market(item_ids)
    except (OSError, ValueError) as error:
        raise HTTPException(status_code=502, detail=f"arsha.io недоступний: {error}")

    with get_connection() as connection:
        valuation.save_prices(connection, item_ids, entries)
        return {
            "requested": len(item_ids),
            "prices_fetched_at": valuation.prices_fetched_at(connection),
        }


@app.post("/api/items/refresh")
def refresh_items():
    with get_connection() as connection:
        return {"missing_names": refresh_item_names(connection)}


@app.get("/api/agent")
def get_agent():
    return agent.status()


@app.post("/api/agent/start")
def start_agent():
    return agent.start()


@app.post("/api/agent/stop")
def stop_agent():
    return agent.stop()


def _is_placeholder(name: str | None) -> bool:
    """Назва-заглушка з довідників bdo_toolkit, як-от "class#13" чи "town#9999"."""
    return not name or "#" in name


@app.get("/api/characters")
def get_characters():
    with get_connection() as connection:
        characters = account.list_characters(connection)
        names = game_data.lookup(connection, "character")
    # Клас — це character key класу (Ranger = 2), тож назва береться з тієї ж таблиці персонажів.
    for character in characters:
        if _is_placeholder(character["class_name"]) and character["class_id"] is not None:
            character["class_name"] = names.get(str(character["class_id"]), character["class_name"])
    return characters


@app.get("/api/family")
def get_family():
    with get_connection() as connection:
        return account.family_summary(connection)


@app.get("/api/nodes")
def get_nodes():
    """Вкладені вузли сім'ї з назвами, територіями й продуктами з власного клієнта."""
    with get_connection() as connection:
        invested = account.invested_node_ids(connection)
        names = game_data.lookup(connection, "node")
        details = game_data.node_details(connection, invested)
        points = account.contribution(connection)
    nodes = []
    for node_id in invested:
        info = details.get(node_id, {})
        manager = info.get("manager_id")
        nodes.append({
            "node_id": node_id,
            "name": names.get(str(node_id), f"Вузол #{node_id}"),
            "territory": info.get("territory"),
            "manager_id": manager,
            "manager_name": names.get(str(manager)) if manager else None,
            "contribution": info.get("contribution"),
            "products": info.get("products", []),
        })
    return {"contribution": points, "nodes": nodes}


@app.get("/api/journals")
def get_journals():
    """Журнали пригод з прогресом по всій сім'ї (за списками квестів з трафіку)."""
    with get_connection() as connection:
        status = account.quest_status(connection)
        journal_list = game_data.journals(connection, status)
        bonuses = game_data.family_bonuses(connection, status)
    return {"journals": journal_list, "bonuses": bonuses, "quests_known": bool(status)}


@app.get("/api/quests")
def get_quests(q: str = ""):
    """Пошук квестів; без запиту — лише підсумок."""
    with get_connection() as connection:
        status = account.quest_status(connection)
        found = game_data.search_quests(connection, status, q) if len(q.strip()) >= 2 else []
        characters = connection.execute("SELECT COUNT(DISTINCT character_id) FROM quests").fetchone()[0]
    return {
        "characters": characters,
        "done": sum(s == "done" for s in status.values()),
        "open": sum(s == "open" for s in status.values()),
        "quests": found,
    }


class GearStats(BaseModel):
    ap: int = Field(ge=0, le=1000)
    dp: int = Field(ge=0, le=1000)


def _gear(connection) -> dict:
    row = connection.execute("SELECT value FROM settings WHERE key = 'gear'").fetchone()
    return json.loads(row[0]) if row else {"ap": None, "dp": None}


@app.get("/api/gear")
def get_gear():
    """AP/DP персонажа вводить гравець: сервер їх не надсилає, клієнт рахує сам."""
    with get_connection() as connection:
        return _gear(connection)


@app.put("/api/gear")
def put_gear(stats: GearStats):
    with get_connection() as connection:
        connection.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('gear', ?)",
                           (json.dumps(stats.model_dump()),))
        return _gear(connection)


@app.get("/api/grind")
def get_grind():
    with get_connection() as connection:
        gear = _gear(connection)
        return {"gear": gear, "spots": game_data.grind_spots(connection, gear["ap"], gear["dp"])}


@app.get("/api/recipes")
def get_recipes():
    """Що можна зробити з поточного інвентаря й складів (за останнім знімком агента)."""
    with get_connection() as connection:
        containers = snapshots.current_holdings(connection)
        prices = valuation.unit_prices(connection)
        recipes = game_data.craftable(connection, containers, prices)
        total = connection.execute("SELECT COUNT(*) FROM game_recipes").fetchone()[0]
    return {"recipes": recipes, "known": total, "holdings": bool(containers)}


@app.get("/api/map")
def get_map():
    """Шари карти, вузли й NPC для ще не зібраних знань; null, доки плиток карти немає."""
    with get_connection() as connection:
        invested = set(account.invested_node_ids(connection))
        gained = {row[0] for row in connection.execute("SELECT knowledge_id FROM knowledge")}
        return game_data.map_data(connection, invested, gained)


@app.get("/api/game-data/map-tiles/{layer}/{z}/{x}/{y}")
def get_map_tile(layer: str, z: int, x: int, y: int):
    with get_connection() as connection:
        path = game_data.map_tile(connection, layer, z, x, y)
    if path is None:
        raise HTTPException(status_code=404, detail="Плитки немає")
    return FileResponse(path, media_type="image/webp", headers=IMAGE_HEADERS)


@app.get("/api/workers")
def get_workers():
    with get_connection() as connection:
        workers = account.list_workers(connection)
        characters = game_data.lookup(connection, "character")
        nodes = game_data.lookup(connection, "node")
        skills = game_data.lookup(connection, "worker_skill")
    # Назви з власного клієнта (якщо імпортовано) мають перевагу над вбудованими довідниками.
    for worker in workers:
        worker["type_name"] = characters.get(str(worker["type_id"]), worker["type_name"])
        worker["town_name"] = nodes.get(str(worker["town_id"]), worker["town_name"])
        for skill in worker["skills"]:
            skill["name"] = skills.get(str(skill["id"]), skill["name"])
    return workers


@app.get("/api/game-data")
def get_game_data():
    with get_connection() as connection:
        status = game_data.status(connection)
        if status is not None:
            status["images"] = game_data.images(connection)
        return status


# Картинки з клієнта змінюються лише з патчем гри, тож браузер може тримати їх у кеші добу.
IMAGE_HEADERS = {"Cache-Control": "max-age=86400"}


@app.get("/api/game-data/icons/item/{item_id}")
def get_item_icon(item_id: int):
    with get_connection() as connection:
        path = game_data.item_icon(connection, item_id)
    if path is None:
        raise HTTPException(status_code=404, detail="Іконки немає")
    return FileResponse(path, media_type="image/webp", headers=IMAGE_HEADERS)


@app.get("/api/game-data/icons/knowledge/{knowledge_id}")
def get_knowledge_image(knowledge_id: int):
    with get_connection() as connection:
        path = game_data.knowledge_image(connection, knowledge_id)
    if path is None:
        raise HTTPException(status_code=404, detail="Картинки немає")
    return FileResponse(path, media_type="image/webp", headers=IMAGE_HEADERS)


class GameDataImport(BaseModel):
    path: str = Field(min_length=1, max_length=1000)


@app.post("/api/game-data/import")
def import_game_data(request: GameDataImport):
    """Читає вивід bdo-data-extractor з локальної папки (бекенд працює на тому ж ПК)."""
    try:
        with get_connection() as connection:
            return game_data.import_directory(connection, request.path)
    except game_data.GameDataError as error:
        raise HTTPException(status_code=422, detail=str(error))
    except (OSError, ValueError, KeyError, TypeError) as error:
        raise HTTPException(status_code=422, detail=f"Не вдалося прочитати вивід extractor: {error!r}")


@app.get("/api/knowledge")
def get_knowledge():
    with get_connection() as connection:
        summary = account.knowledge_summary(connection, knowledge_names.graded_ids(connection))
        summary["names_loaded"] = knowledge_names.names_loaded(connection)
        return summary


@app.get("/api/knowledge/categories")
def get_knowledge_categories(parent: int = 0):
    with get_connection() as connection:
        return knowledge_names.category_view(connection, parent)


@app.post("/api/knowledge/import")
async def import_knowledge_names(request: Request):
    """Тіло — збережена сторінка bdocodex.com/us/knowledge/ (HTML)."""
    text = (await request.body()).decode("utf-8", errors="replace")
    try:
        with get_connection() as connection:
            return knowledge_names.import_page(connection, text)
    except knowledge_names.KnowledgeImportError as error:
        raise HTTPException(status_code=422, detail=str(error))


@app.get("/api/servants")
def get_servants():
    with get_connection() as connection:
        servants = account.list_servants(connection, valuation.unit_prices(connection))
        characters = game_data.lookup(connection, "character")
        for servant in servants:
            # Тип транспорту — character key (31048 = Epheria Caravel), не предмет. Ключ — молодші
            # 16 біт: у коней мрії старші біти зайняті (162655 → 31583 Arduanatt).
            servant["kind_name"] = characters.get(str(servant["kind_id"] & 0xFFFF))
        return {
            "servants": servants,
            "missing_names": len(account.missing_gear_item_ids(connection)),
        }


class FrontendFiles(StaticFiles):
    """Статика Next з `output: "export"`. Клієнт підвантажує сегменти як
    `__next.workers.__PAGE__.txt`, а експорт кладе їх у `__next.workers/__PAGE__.txt`."""

    async def get_response(self, path: str, scope):
        head, sep, tail = path.rpartition(".__PAGE__")
        segment = bool(sep) and "__next." in head
        try:
            response = await super().get_response(path, scope)
        except StarletteHTTPException as error:
            if error.status_code != 404 or not segment:
                raise
        else:
            # З html=True відсутній файл віддається як out/404.html зі статусом 404, без винятку.
            if response.status_code != 404 or not segment:
                return response
        return await super().get_response(f"{head}/__PAGE__{tail}", scope)


def mount_frontend(target: FastAPI, directory: Path) -> bool:
    """Роздає статичний фронт з `directory` на `/`; монтується останнім, щоб не перекривати /api."""
    if not (directory / "index.html").is_file():
        return False
    target.mount("/", FrontendFiles(directory=directory, html=True), name="frontend")
    return True


mount_frontend(app, FRONTEND_DIR)
