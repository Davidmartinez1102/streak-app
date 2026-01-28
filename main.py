from __future__ import annotations

import sqlite3
from datetime import date, timedelta
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

DB_NAME = "streak_habits.db"

app = FastAPI(title="Streak Habits")

# Para que el frontend (index.html) pueda llamar a la API si lo abres desde archivo o desde otro host
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


def get_connection() -> sqlite3.Connection:
    # check_same_thread=False ayuda en algunos escenarios con uvicorn reload/hilos
    return sqlite3.connect(DB_NAME, check_same_thread=False)


def init_db() -> None:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS checkins (
            date TEXT PRIMARY KEY,
            completed INTEGER NOT NULL,
            note TEXT
        )
        """
    )
    conn.commit()
    conn.close()


@app.on_event("startup")
def on_startup() -> None:
    init_db()


class CheckIn(BaseModel):
    date: str  # ISO YYYY-MM-DD
    completed: bool
    note: Optional[str] = None


def parse_iso(d: str) -> date:
    try:
        return date.fromisoformat(d)
    except ValueError:
        raise HTTPException(status_code=422, detail="date debe estar en formato YYYY-MM-DD")


@app.get("/", response_class=HTMLResponse)
def home():
    # Servimos el HTML directamente desde archivo para que sea fácil
    try:
        with open("index.html", "r", encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        return "<h1>index.html no encontrado</h1>"


@app.post("/checkin")
def create_checkin(data: CheckIn):
    # Validar formato fecha
    parse_iso(data.date)

    conn = get_connection()
    cur = conn.cursor()

    try:
        cur.execute(
            "INSERT INTO checkins (date, completed, note) VALUES (?, ?, ?)",
            (data.date, int(data.completed), data.note),
        )
        conn.commit()
    except sqlite3.IntegrityError:
        # date ya existe (PRIMARY KEY)
        raise HTTPException(status_code=409, detail="Ese día ya fue registrado")
    finally:
        conn.close()

    return {"ok": True}


@app.get("/checkins")
def list_checkins(limit: int = 3650):
    # Devuelve historial (para calendario / tabla)
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "SELECT date, completed, COALESCE(note, '') FROM checkins ORDER BY date DESC LIMIT ?",
        (limit,),
    )
    rows = cur.fetchall()
    conn.close()

    items = [
        {"date": r[0], "completed": bool(r[1]), "note": r[2]}
        for r in rows
    ]
    return {"items": items}


def compute_streaks(rows_completed_dates_desc: list[str]) -> tuple[int, int]:
    """
    rows_completed_dates_desc: lista de fechas ISO de días completed=1 en orden DESC.
    Devuelve (current_streak, best_streak)
    """
    if not rows_completed_dates_desc:
        return 0, 0

    dates = [date.fromisoformat(x) for x in rows_completed_dates_desc]

    # best streak: recorrer secuencias consecutivas
    best = 1
    run = 1
    for i in range(1, len(dates)):
        if dates[i - 1] - dates[i] == timedelta(days=1):
            run += 1
            if run > best:
                best = run
        else:
            run = 1

    # current streak: secuencia consecutiva que termina hoy
    today = date.today()
    dset = set(dates)

    current = 0
    cur_day = today
    while cur_day in dset:
        current += 1
        cur_day = cur_day - timedelta(days=1)

    return current, best


@app.get("/streak")
def get_streak():
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "SELECT date FROM checkins WHERE completed = 1 ORDER BY date DESC"
    )
    rows = [r[0] for r in cur.fetchall()]
    conn.close()

    current, best = compute_streaks(rows)
    return {
        "current_streak": current,
        "best_streak": best,
    }
