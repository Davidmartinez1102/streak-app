from __future__ import annotations
from fastapi.responses import FileResponse





import os
import sqlite3
from datetime import date, timedelta
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# En Vercel, solo /tmp es escribible
from pathlib import Path


if os.environ.get("VERCEL") == "1":
    DB_NAME = "/tmp/streak_habits.db"
else:
    DB_NAME = str(Path(__file__).with_name("streak_habits.db"))


app = FastAPI(title="Streak Habits")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

def get_connection() -> sqlite3.Connection:
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
    date: str
    completed: bool
    note: Optional[str] = None

def parse_iso(d: str) -> date:
    try:
        return date.fromisoformat(d)
    except ValueError:
        raise HTTPException(status_code=422, detail="date debe estar en formato YYYY-MM-DD")

@app.post("/checkin")
def create_checkin(data: CheckIn):
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
        raise HTTPException(status_code=409, detail="Ese día ya fue registrado")
    finally:
        conn.close()
    return {"ok": True}

@app.get("/checkins")
def list_checkins(limit: int = 3650):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "SELECT date, completed, COALESCE(note, '') FROM checkins ORDER BY date DESC LIMIT ?",
        (limit,),
    )
    rows = cur.fetchall()
    conn.close()
    items = [{"date": r[0], "completed": bool(r[1]), "note": r[2]} for r in rows]
    return {"items": items}

def compute_streaks(rows_completed_dates_desc: list[str]) -> tuple[int, int]:
    if not rows_completed_dates_desc:
        return 0, 0
    dates = [date.fromisoformat(x) for x in rows_completed_dates_desc]

    best = 1
    run = 1
    for i in range(1, len(dates)):
        if dates[i - 1] - dates[i] == timedelta(days=1):
            run += 1
            best = max(best, run)
        else:
            run = 1

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
    cur.execute("SELECT date FROM checkins WHERE completed = 1 ORDER BY date DESC")
    rows = [r[0] for r in cur.fetchall()]
    conn.close()
    current, best = compute_streaks(rows)
    return {"current_streak": current, "best_streak": best}

    from fastapi.responses import FileResponse
from pathlib import Path
import os
from pathlib import Path
from fastapi.responses import FileResponse
from fastapi import HTTPException

import os
from fastapi import Response

@app.get("/")
def home():
    # En Vercel: NO intentes devolver /public/index.html desde Python
    if os.environ.get("VERCEL"):
        raise HTTPException(status_code=404)

    # En local sí servimos el HTML
    html_path = Path(__file__).resolve().parents[1] / "public" / "index.html"
    if not html_path.exists():
        raise HTTPException(status_code=500, detail=f"No existe: {html_path}")
    return FileResponse(html_path)
