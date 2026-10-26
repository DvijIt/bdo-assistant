
from contextlib import asynccontextmanager, contextmanager
from pathlib import Path
import sqlite3

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field


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

        
        connection.execute("""
            CREATE TABLE IF NOT EXISTS inventory (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                category TEXT NOT NULL DEFAULT 'material',
                quantity INTEGER NOT NULL DEFAULT 1,
                notes TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
        """)



@asynccontextmanager
async def lifespan(app: FastAPI):
    initialize_database()
    yield


app = FastAPI(
    title="BDO Assistant API",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=False,
    allow_methods=["GET", "PUT", "POST", "DELETE"],
    allow_headers=["Content-Type"],
)


class ProfileUpdate(BaseModel):
    character_name: str = Field(min_length=1, max_length=100)
    character_class: str = Field(min_length=1, max_length=100)
    ap: int = Field(ge=0, le=10000)
    dp: int = Field(ge=0, le=10000)
    silver_billions: float = Field(ge=0, le=1_000_000_000)
    goal: str = Field(pattern=r"^(gear|silver|pve|life)$")

    
class InventoryItemCreate(BaseModel):
    name: str = Field(min_length=1, max_length=150)
    category: str = Field(
        default="material",
        pattern=r"^(gear|material|consumable|other)$"
    )
    quantity: int = Field(default=1, ge=1, le=2_000_000_000)
    notes: str = Field(default="", max_length=500)



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


def inventory_item_to_dict(row):
    return {
        "id": row["id"],
        "name": row["name"],
        "category": row["category"],
        "quantity": row["quantity"],
        "notes": row["notes"],
        "created_at": row["created_at"],
    }


@app.get("/api/inventory")
def get_inventory():
    with get_connection() as connection:
        rows = connection.execute(
            "SELECT * FROM inventory ORDER BY id DESC"
        ).fetchall()

    return [inventory_item_to_dict(row) for row in rows]


@app.post("/api/inventory", status_code=201)
def add_inventory_item(item: InventoryItemCreate):
    name = item.name.strip()

    if not name:
        raise HTTPException(
            status_code=422,
            detail="Назва предмета не може бути порожньою"
        )

    with get_connection() as connection:
        cursor = connection.execute(
            """
            INSERT INTO inventory (name, category, quantity, notes)
            VALUES (?, ?, ?, ?)
            """,
            (name, item.category, item.quantity, item.notes.strip()),
        )

        row = connection.execute(
            "SELECT * FROM inventory WHERE id = ?",
            (cursor.lastrowid,),
        ).fetchone()

    return inventory_item_to_dict(row)


@app.delete("/api/inventory/{item_id}")
def delete_inventory_item(item_id: int):
    with get_connection() as connection:
        cursor = connection.execute(
            "DELETE FROM inventory WHERE id = ?",
            (item_id,),
        )

        if cursor.rowcount == 0:
            raise HTTPException(
                status_code=404,
                detail="Предмет не знайдено"
            )

    return {"deleted": True, "id": item_id}

