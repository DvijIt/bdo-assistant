
from contextlib import asynccontextmanager, contextmanager
import os
from pathlib import Path
import sqlite3

from fastapi import Body, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

import account
import agent as agent_module
import arsha
import snapshots
import valuation


BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "bdo_assistant.db"


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


# DB_PATH читається під час кожного з'єднання, тож тести можуть його підміняти.
agent = agent_module.Agent(lambda: get_connection())


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
        item_ids = sorted(set(item_ids) | gear_ids)

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


@app.get("/api/characters")
def get_characters():
    with get_connection() as connection:
        return account.list_characters(connection)


@app.get("/api/workers")
def get_workers():
    with get_connection() as connection:
        return account.list_workers(connection)


@app.get("/api/servants")
def get_servants():
    with get_connection() as connection:
        return {
            "servants": account.list_servants(connection, valuation.unit_prices(connection)),
            "missing_names": len(account.missing_gear_item_ids(connection)),
        }
