"""
HASPP Team App — backend
Multi-user team workspace: login, admin permissions, shared kanban boards.
First registered user automatically becomes admin.
Run: uvicorn app:app --host 0.0.0.0 --port 8000
"""
import hashlib
import os
import secrets
import sqlite3
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from fastapi.staticfiles import StaticFiles
from jose import JWTError, jwt
from pydantic import BaseModel, Field

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "haspp_team.db"
FRONTEND_DIR = BASE_DIR.parent / "frontend"

SECRET_KEY = os.environ.get("SECRET_KEY") or secrets.token_hex(32)
ALGORITHM = "HS256"
TOKEN_HOURS = 72

app = FastAPI(title="HASPP Team App")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
security = HTTPBearer(auto_error=False)


# ---------------- database ----------------
def db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    conn = db()
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL,
            role TEXT NOT NULL DEFAULT 'member',   -- admin | member
            is_active INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS boards (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            description TEXT DEFAULT '',
            created_by INTEGER NOT NULL REFERENCES users(id),
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS board_members (
            board_id INTEGER NOT NULL REFERENCES boards(id) ON DELETE CASCADE,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            role TEXT NOT NULL DEFAULT 'member',   -- admin | member
            PRIMARY KEY (board_id, user_id)
        );
        CREATE TABLE IF NOT EXISTS lists (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            board_id INTEGER NOT NULL REFERENCES boards(id) ON DELETE CASCADE,
            title TEXT NOT NULL,
            position INTEGER NOT NULL DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS cards (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            board_id INTEGER NOT NULL REFERENCES boards(id) ON DELETE CASCADE,
            list_id INTEGER NOT NULL REFERENCES lists(id) ON DELETE CASCADE,
            title TEXT NOT NULL,
            description TEXT DEFAULT '',
            assignee_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
            due_date TEXT,
            position INTEGER NOT NULL DEFAULT 0,
            created_by INTEGER NOT NULL REFERENCES users(id),
            created_at TEXT NOT NULL
        );
        """
    )
    conn.commit()
    conn.close()


init_db()


# ---------------- helpers ----------------
def now_iso():
    return datetime.now(timezone.utc).isoformat()


def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 200_000)
    return f"{salt}${dk.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        salt, hexed = stored.split("$", 1)
    except ValueError:
        return False
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 200_000)
    return secrets.compare_digest(dk.hex(), hexed)


def make_token(user_id: int) -> str:
    exp = datetime.now(timezone.utc) + timedelta(hours=TOKEN_HOURS)
    return jwt.encode({"sub": str(user_id), "exp": exp}, SECRET_KEY, algorithm=ALGORITHM)


def row_to_user(r) -> dict:
    return {
        "id": r["id"],
        "name": r["name"],
        "email": r["email"],
        "role": r["role"],
        "is_active": bool(r["is_active"]),
        "created_at": r["created_at"],
    }


def get_current_user(
    creds: HTTPAuthorizationCredentials = Depends(security),
) -> dict:
    if not creds:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not authenticated")
    try:
        payload = jwt.decode(creds.credentials, SECRET_KEY, algorithms=[ALGORITHM])
        user_id = int(payload["sub"])
    except (JWTError, ValueError, KeyError):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid token")
    conn = db()
    r = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    conn.close()
    if not r or not r["is_active"]:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "User inactive or missing")
    return row_to_user(r)


def require_admin(user: dict) -> dict:
    if user["role"] != "admin":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Admin only")
    return user


def can_access_board(conn, user: dict, board_id: int) -> bool:
    if user["role"] == "admin":
        return True
    r = conn.execute(
        "SELECT 1 FROM board_members WHERE board_id = ? AND user_id = ?",
        (board_id, user["id"]),
    ).fetchone()
    return r is not None


def is_board_admin(conn, user: dict, board_id: int) -> bool:
    if user["role"] == "admin":
        return True
    r = conn.execute(
        "SELECT role FROM board_members WHERE board_id = ? AND user_id = ?",
        (board_id, user["id"]),
    ).fetchone()
    return r is not None and r["role"] == "admin"


def board_detail(conn, board_id: int) -> dict:
    b = conn.execute("SELECT * FROM boards WHERE id = ?", (board_id,)).fetchone()
    if not b:
        raise HTTPException(404, "Board not found")
    lists = conn.execute(
        "SELECT * FROM lists WHERE board_id = ? ORDER BY position, id", (board_id,)
    ).fetchall()
    members = conn.execute(
        """SELECT u.id, u.name, u.email, bm.role FROM board_members bm
           JOIN users u ON u.id = bm.user_id WHERE bm.board_id = ?""",
        (board_id,),
    ).fetchall()
    out_lists = []
    for lst in lists:
        cards = conn.execute(
            """SELECT c.*, u.name AS assignee_name FROM cards c
               LEFT JOIN users u ON u.id = c.assignee_id
               WHERE c.list_id = ? ORDER BY c.position, c.id""",
            (lst["id"],),
        ).fetchall()
        out_lists.append(
            {
                "id": lst["id"],
                "title": lst["title"],
                "position": lst["position"],
                "cards": [
                    {
                        "id": c["id"],
                        "title": c["title"],
                        "description": c["description"],
                        "assignee_id": c["assignee_id"],
                        "assignee_name": c["assignee_name"],
                        "due_date": c["due_date"],
                        "position": c["position"],
                    }
                    for c in cards
                ],
            }
        )
    return {
        "id": b["id"],
        "title": b["title"],
        "description": b["description"],
        "created_at": b["created_at"],
        "lists": out_lists,
        "members": [
            {"id": m["id"], "name": m["name"], "email": m["email"], "role": m["role"]}
            for m in members
        ],
    }


# ---------------- schemas ----------------
class RegisterIn(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    email: str = Field(min_length=3, max_length=120)
    password: str = Field(min_length=6, max_length=128)


class LoginIn(BaseModel):
    email: str
    password: str


class BoardIn(BaseModel):
    title: str = Field(min_length=1, max_length=120)
    description: str = ""


class ListIn(BaseModel):
    title: str = Field(min_length=1, max_length=120)


class CardIn(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    description: str = ""
    assignee_id: int | None = None
    due_date: str | None = None


class CardMove(BaseModel):
    list_id: int | None = None
    position: int | None = None
    title: str | None = None
    description: str | None = None
    assignee_id: int | None = None
    due_date: str | None = None


class MemberAdd(BaseModel):
    user_id: int
    role: str = "member"


class UserUpdate(BaseModel):
    role: str | None = None
    is_active: bool | None = None


# ---------------- auth routes ----------------
@app.post("/api/register")
def register(data: RegisterIn):
    conn = db()
    email = data.email.strip().lower()
    if conn.execute("SELECT 1 FROM users WHERE email = ?", (email,)).fetchone():
        conn.close()
        raise HTTPException(400, "Email already registered")
    count = conn.execute("SELECT COUNT(*) AS c FROM users").fetchone()["c"]
    role = "admin" if count == 0 else "member"  # first user becomes admin
    cur = conn.execute(
        "INSERT INTO users (name, email, password_hash, role, created_at) VALUES (?,?,?,?,?)",
        (data.name.strip(), email, hash_password(data.password), role, now_iso()),
    )
    conn.commit()
    user_id = cur.lastrowid
    r = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    conn.close()
    return {"token": make_token(user_id), "user": row_to_user(r)}


@app.post("/api/login")
def login(data: LoginIn):
    conn = db()
    r = conn.execute(
        "SELECT * FROM users WHERE email = ?", (data.email.strip().lower(),)
    ).fetchone()
    conn.close()
    if not r or not verify_password(data.password, r["password_hash"]):
        raise HTTPException(401, "Wrong email or password")
    if not r["is_active"]:
        raise HTTPException(403, "Account deactivated")
    return {"token": make_token(r["id"]), "user": row_to_user(r)}


@app.get("/api/me")
def me(user: dict = Depends(get_current_user)):
    return user


# ---------------- user admin routes ----------------
@app.get("/api/users")
def list_users(user: dict = Depends(get_current_user)):
    require_admin(user)
    conn = db()
    rows = conn.execute("SELECT * FROM users ORDER BY id").fetchall()
    conn.close()
    return [row_to_user(r) for r in rows]


@app.patch("/api/users/{uid}")
def update_user(uid: int, data: UserUpdate, user: dict = Depends(get_current_user)):
    require_admin(user)
    if uid == user["id"] and data.is_active is False:
        raise HTTPException(400, "You cannot deactivate yourself")
    conn = db()
    if data.role is not None:
        if data.role not in ("admin", "member"):
            conn.close()
            raise HTTPException(400, "Invalid role")
        conn.execute("UPDATE users SET role = ? WHERE id = ?", (data.role, uid))
    if data.is_active is not None:
        conn.execute(
            "UPDATE users SET is_active = ? WHERE id = ?", (1 if data.is_active else 0, uid)
        )
    conn.commit()
    r = conn.execute("SELECT * FROM users WHERE id = ?", (uid,)).fetchone()
    conn.close()
    if not r:
        raise HTTPException(404, "User not found")
    return row_to_user(r)


# ---------------- board routes ----------------
@app.get("/api/boards")
def list_boards(user: dict = Depends(get_current_user)):
    conn = db()
    if user["role"] == "admin":
        rows = conn.execute("SELECT * FROM boards ORDER BY id DESC").fetchall()
    else:
        rows = conn.execute(
            """SELECT b.* FROM boards b JOIN board_members bm ON bm.board_id = b.id
               WHERE bm.user_id = ? ORDER BY b.id DESC""",
            (user["id"],),
        ).fetchall()
    conn.close()
    return [
        {"id": r["id"], "title": r["title"], "description": r["description"]}
        for r in rows
    ]


@app.post("/api/boards")
def create_board(data: BoardIn, user: dict = Depends(get_current_user)):
    conn = db()
    cur = conn.execute(
        "INSERT INTO boards (title, description, created_by, created_at) VALUES (?,?,?,?)",
        (data.title.strip(), data.description.strip(), user["id"], now_iso()),
    )
    board_id = cur.lastrowid
    conn.execute(
        "INSERT INTO board_members (board_id, user_id, role) VALUES (?,?,?)",
        (board_id, user["id"], "admin"),
    )
    for i, title in enumerate(["To Do", "In Progress", "Done"]):
        conn.execute(
            "INSERT INTO lists (board_id, title, position) VALUES (?,?,?)",
            (board_id, title, i),
        )
    conn.commit()
    detail = board_detail(conn, board_id)
    conn.close()
    return detail


@app.get("/api/boards/{bid}")
def get_board(bid: int, user: dict = Depends(get_current_user)):
    conn = db()
    if not can_access_board(conn, user, bid):
        conn.close()
        raise HTTPException(403, "No access to this board")
    detail = board_detail(conn, bid)
    conn.close()
    return detail


@app.delete("/api/boards/{bid}")
def delete_board(bid: int, user: dict = Depends(get_current_user)):
    conn = db()
    if not is_board_admin(conn, user, bid):
        conn.close()
        raise HTTPException(403, "Board admin only")
    conn.execute("DELETE FROM boards WHERE id = ?", (bid,))
    conn.commit()
    conn.close()
    return {"ok": True}


@app.post("/api/boards/{bid}/members")
def add_member(bid: int, data: MemberAdd, user: dict = Depends(get_current_user)):
    conn = db()
    if not is_board_admin(conn, user, bid):
        conn.close()
        raise HTTPException(403, "Board admin only")
    target = conn.execute("SELECT * FROM users WHERE id = ?", (data.user_id,)).fetchone()
    if not target or not target["is_active"]:
        conn.close()
        raise HTTPException(404, "User not found or inactive")
    if data.role not in ("admin", "member"):
        conn.close()
        raise HTTPException(400, "Invalid role")
    conn.execute(
        "INSERT OR REPLACE INTO board_members (board_id, user_id, role) VALUES (?,?,?)",
        (bid, data.user_id, data.role),
    )
    conn.commit()
    conn.close()
    return {"ok": True}


@app.delete("/api/boards/{bid}/members/{uid}")
def remove_member(bid: int, uid: int, user: dict = Depends(get_current_user)):
    conn = db()
    if not is_board_admin(conn, user, bid):
        conn.close()
        raise HTTPException(403, "Board admin only")
    conn.execute(
        "DELETE FROM board_members WHERE board_id = ? AND user_id = ?", (bid, uid)
    )
    conn.commit()
    conn.close()
    return {"ok": True}


# ---------------- list routes ----------------
@app.post("/api/boards/{bid}/lists")
def create_list(bid: int, data: ListIn, user: dict = Depends(get_current_user)):
    conn = db()
    if not can_access_board(conn, user, bid):
        conn.close()
        raise HTTPException(403, "No access to this board")
    mx = conn.execute(
        "SELECT COALESCE(MAX(position), -1) AS m FROM lists WHERE board_id = ?", (bid,)
    ).fetchone()["m"]
    cur = conn.execute(
        "INSERT INTO lists (board_id, title, position) VALUES (?,?,?)",
        (bid, data.title.strip(), mx + 1),
    )
    conn.commit()
    lid = cur.lastrowid
    conn.close()
    return {"id": lid, "title": data.title.strip(), "cards": []}


@app.delete("/api/lists/{lid}")
def delete_list(lid: int, user: dict = Depends(get_current_user)):
    conn = db()
    lst = conn.execute("SELECT * FROM lists WHERE id = ?", (lid,)).fetchone()
    if not lst:
        conn.close()
        raise HTTPException(404, "List not found")
    if not is_board_admin(conn, user, lst["board_id"]):
        conn.close()
        raise HTTPException(403, "Board admin only")
    conn.execute("DELETE FROM lists WHERE id = ?", (lid,))
    conn.commit()
    conn.close()
    return {"ok": True}


# ---------------- card routes ----------------
@app.post("/api/lists/{lid}/cards")
def create_card(lid: int, data: CardIn, user: dict = Depends(get_current_user)):
    conn = db()
    lst = conn.execute("SELECT * FROM lists WHERE id = ?", (lid,)).fetchone()
    if not lst:
        conn.close()
        raise HTTPException(404, "List not found")
    if not can_access_board(conn, user, lst["board_id"]):
        conn.close()
        raise HTTPException(403, "No access to this board")
    if data.assignee_id:
        ok = conn.execute(
            "SELECT 1 FROM board_members WHERE board_id = ? AND user_id = ?",
            (lst["board_id"], data.assignee_id),
        ).fetchone()
        if not ok:
            conn.close()
            raise HTTPException(400, "Assignee is not a board member")
    mx = conn.execute(
        "SELECT COALESCE(MAX(position), -1) AS m FROM cards WHERE list_id = ?", (lid,)
    ).fetchone()["m"]
    cur = conn.execute(
        """INSERT INTO cards (board_id, list_id, title, description, assignee_id,
           due_date, position, created_by, created_at)
           VALUES (?,?,?,?,?,?,?,?,?)""",
        (
            lst["board_id"], lid, data.title.strip(), data.description.strip(),
            data.assignee_id, data.due_date, mx + 1, user["id"], now_iso(),
        ),
    )
    conn.commit()
    cid = cur.lastrowid
    conn.close()
    return {"id": cid, "title": data.title.strip()}


@app.patch("/api/cards/{cid}")
def update_card(cid: int, data: CardMove, user: dict = Depends(get_current_user)):
    conn = db()
    c = conn.execute("SELECT * FROM cards WHERE id = ?", (cid,)).fetchone()
    if not c:
        conn.close()
        raise HTTPException(404, "Card not found")
    if not can_access_board(conn, user, c["board_id"]):
        conn.close()
        raise HTTPException(403, "No access to this board")
    fields, vals = [], []
    if data.title is not None:
        fields.append("title = ?")
        vals.append(data.title.strip())
    if data.description is not None:
        fields.append("description = ?")
        vals.append(data.description.strip())
    if data.assignee_id is not None:
        ok = conn.execute(
            "SELECT 1 FROM board_members WHERE board_id = ? AND user_id = ?",
            (c["board_id"], data.assignee_id),
        ).fetchone()
        if not ok:
            conn.close()
            raise HTTPException(400, "Assignee is not a board member")
        fields.append("assignee_id = ?")
        vals.append(data.assignee_id)
    if data.due_date is not None:
        fields.append("due_date = ?")
        vals.append(data.due_date or None)
    if data.list_id is not None:
        lst = conn.execute("SELECT * FROM lists WHERE id = ?", (data.list_id,)).fetchone()
        if not lst or lst["board_id"] != c["board_id"]:
            conn.close()
            raise HTTPException(400, "Invalid target list")
        fields.append("list_id = ?")
        vals.append(data.list_id)
    if data.position is not None:
        fields.append("position = ?")
        vals.append(data.position)
    if fields:
        vals.append(cid)
        conn.execute(f"UPDATE cards SET {', '.join(fields)} WHERE id = ?", vals)
        conn.commit()
    conn.close()
    return {"ok": True}


@app.delete("/api/cards/{cid}")
def delete_card(cid: int, user: dict = Depends(get_current_user)):
    conn = db()
    c = conn.execute("SELECT * FROM cards WHERE id = ?", (cid,)).fetchone()
    if not c:
        conn.close()
        raise HTTPException(404, "Card not found")
    if not can_access_board(conn, user, c["board_id"]):
        conn.close()
        raise HTTPException(403, "No access to this board")
    conn.execute("DELETE FROM cards WHERE id = ?", (cid,))
    conn.commit()
    conn.close()
    return {"ok": True}


# ---------------- frontend ----------------
if FRONTEND_DIR.exists():
    app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")
else:

    @app.get("/")
    def root():
        return {"status": "ok", "message": "Frontend not built yet"}
