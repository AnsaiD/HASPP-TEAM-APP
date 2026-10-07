"""
HASPP Team App — backend (SQLAlchemy)
Multi-user team workspace: login, admin permissions, shared kanban boards.
Database: PostgreSQL when DATABASE_URL is set, otherwise local SQLite.
First registered user automatically becomes admin.
Run: uvicorn app:app --host 0.0.0.0 --port 8000
"""
import hashlib
import os
import secrets
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from fastapi.staticfiles import StaticFiles
from jose import JWTError, jwt
from pydantic import BaseModel, Field
from sqlalchemy import (Boolean, Column, ForeignKey, Integer, String, Text,
                        create_engine, func, select)
from sqlalchemy.orm import Session, declarative_base, sessionmaker

BASE_DIR = Path(__file__).resolve().parent
FRONTEND_DIR = BASE_DIR.parent / "frontend"

SECRET_KEY = os.environ.get("SECRET_KEY") or secrets.token_hex(32)
ALGORITHM = "HS256"
TOKEN_HOURS = 720  # 30 days — stay logged in

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    # Local development only: set ALLOW_SQLITE=true to use a local file DB.
    if os.getenv("ALLOW_SQLITE", "").lower() == "true":
        DATABASE_URL = "sqlite:///./haspp_team.db"
    else:
        raise RuntimeError(
            "DATABASE_URL is not set. Refusing to start with an ephemeral "
            "SQLite database in production (all data would be lost on redeploy). "
            "Set DATABASE_URL to your PostgreSQL/Neon connection string."
        )
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

if DATABASE_URL.startswith("postgresql"):
    engine = create_engine(DATABASE_URL, pool_pre_ping=True)
else:
    engine = create_engine(
        f"sqlite:///{BASE_DIR / 'haspp_team.db'}",
        connect_args={"check_same_thread": False},
    )

SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
Base = declarative_base()


# ---------------- models ----------------
class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(80), nullable=False)
    email = Column(String(120), nullable=False, unique=True)
    password_hash = Column(String(256), nullable=False)
    role = Column(String(16), nullable=False, default="member")  # admin | member
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(String(40), nullable=False)


class Board(Base):
    __tablename__ = "boards"
    id = Column(Integer, primary_key=True, autoincrement=True)
    title = Column(String(120), nullable=False)
    description = Column(Text, nullable=False, default="")
    created_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    created_at = Column(String(40), nullable=False)


class BoardMember(Base):
    __tablename__ = "board_members"
    board_id = Column(Integer, ForeignKey("boards.id", ondelete="CASCADE"), primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    role = Column(String(16), nullable=False, default="member")  # admin | member


class List(Base):
    __tablename__ = "lists"
    id = Column(Integer, primary_key=True, autoincrement=True)
    board_id = Column(Integer, ForeignKey("boards.id", ondelete="CASCADE"), nullable=False)
    title = Column(String(120), nullable=False)
    position = Column(Integer, nullable=False, default=0)


class Card(Base):
    __tablename__ = "cards"
    id = Column(Integer, primary_key=True, autoincrement=True)
    board_id = Column(Integer, ForeignKey("boards.id", ondelete="CASCADE"), nullable=False)
    list_id = Column(Integer, ForeignKey("lists.id", ondelete="CASCADE"), nullable=False)
    title = Column(String(200), nullable=False)
    description = Column(Text, nullable=False, default="")
    assignee_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    due_date = Column(String(20), nullable=True)
    position = Column(Integer, nullable=False, default=0)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    created_at = Column(String(40), nullable=False)


Base.metadata.create_all(engine)

app = FastAPI(title="HASPP Team App")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
security = HTTPBearer(auto_error=False)


# ---------------- helpers ----------------
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


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


def user_dict(u: User) -> dict:
    return {
        "id": u.id,
        "name": u.name,
        "email": u.email,
        "role": u.role,
        "is_active": bool(u.is_active),
        "created_at": u.created_at,
    }


def get_current_user(
    creds: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db),
) -> dict:
    if not creds:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not authenticated")
    try:
        payload = jwt.decode(creds.credentials, SECRET_KEY, algorithms=[ALGORITHM])
        user_id = int(payload["sub"])
    except (JWTError, ValueError, KeyError):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid token")
    u = db.get(User, user_id)
    if not u or not u.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "User inactive or missing")
    return user_dict(u)


def require_admin(user: dict) -> dict:
    if user["role"] != "admin":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Admin only")
    return user


def can_access_board(db: Session, user: dict, board_id: int) -> bool:
    if user["role"] == "admin":
        return True
    return (
        db.query(BoardMember)
        .filter_by(board_id=board_id, user_id=user["id"])
        .first()
        is not None
    )


def is_board_admin(db: Session, user: dict, board_id: int) -> bool:
    if user["role"] == "admin":
        return True
    m = (
        db.query(BoardMember)
        .filter_by(board_id=board_id, user_id=user["id"])
        .first()
    )
    return m is not None and m.role == "admin"


def board_detail(db: Session, board_id: int) -> dict:
    b = db.get(Board, board_id)
    if not b:
        raise HTTPException(404, "Board not found")
    lists = (
        db.query(List)
        .filter_by(board_id=board_id)
        .order_by(List.position, List.id)
        .all()
    )
    members = (
        db.query(BoardMember, User)
        .join(User, User.id == BoardMember.user_id)
        .filter(BoardMember.board_id == board_id)
        .all()
    )
    out_lists = []
    for lst in lists:
        cards = (
            db.query(Card, User.name.label("assignee_name"))
            .outerjoin(User, User.id == Card.assignee_id)
            .filter(Card.list_id == lst.id)
            .order_by(Card.position, Card.id)
            .all()
        )
        out_lists.append(
            {
                "id": lst.id,
                "title": lst.title,
                "position": lst.position,
                "cards": [
                    {
                        "id": c.id,
                        "title": c.title,
                        "description": c.description,
                        "assignee_id": c.assignee_id,
                        "assignee_name": aname,
                        "due_date": c.due_date,
                        "position": c.position,
                    }
                    for c, aname in cards
                ],
            }
        )
    return {
        "id": b.id,
        "title": b.title,
        "description": b.description,
        "created_at": b.created_at,
        "lists": out_lists,
        "members": [
            {"id": u.id, "name": u.name, "email": u.email, "role": bm.role}
            for bm, u in members
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
def register(data: RegisterIn, db: Session = Depends(get_db)):
    email = data.email.strip().lower()
    if db.query(User).filter_by(email=email).first():
        raise HTTPException(400, "Email already registered")
    count = db.query(func.count(User.id)).scalar()
    role = "admin" if count == 0 else "member"  # first user becomes admin
    u = User(
        name=data.name.strip(),
        email=email,
        password_hash=hash_password(data.password),
        role=role,
        is_active=True,
        created_at=now_iso(),
    )
    db.add(u)
    db.commit()
    db.refresh(u)
    return {"token": make_token(u.id), "user": user_dict(u)}


@app.post("/api/login")
def login(data: LoginIn, db: Session = Depends(get_db)):
    u = db.query(User).filter_by(email=data.email.strip().lower()).first()
    if not u or not verify_password(data.password, u.password_hash):
        raise HTTPException(401, "Wrong email or password")
    if not u.is_active:
        raise HTTPException(403, "Account deactivated")
    return {"token": make_token(u.id), "user": user_dict(u)}


@app.get("/api/me")
def me(user: dict = Depends(get_current_user)):
    return user


# ---------------- user admin routes ----------------
@app.get("/api/users")
def list_users(user: dict = Depends(get_current_user), db: Session = Depends(get_db)):
    require_admin(user)
    return [user_dict(u) for u in db.query(User).order_by(User.id).all()]


@app.patch("/api/users/{uid}")
def update_user(
    uid: int, data: UserUpdate,
    user: dict = Depends(get_current_user), db: Session = Depends(get_db),
):
    require_admin(user)
    if uid == user["id"] and data.is_active is False:
        raise HTTPException(400, "You cannot deactivate yourself")
    u = db.get(User, uid)
    if not u:
        raise HTTPException(404, "User not found")
    if data.role is not None:
        if data.role not in ("admin", "member"):
            raise HTTPException(400, "Invalid role")
        u.role = data.role
    if data.is_active is not None:
        u.is_active = bool(data.is_active)
    db.commit()
    return user_dict(u)


class AdminUserCreate(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    email: str = Field(min_length=3, max_length=120)
    password: str = Field(min_length=6, max_length=128)
    role: str = "member"


@app.post("/api/users")
def admin_create_user(
    data: AdminUserCreate,
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Admin creates a user directly (no self-registration needed)."""
    require_admin(user)
    email = data.email.strip().lower()
    if db.query(User).filter_by(email=email).first():
        raise HTTPException(400, "Email already registered")
    if data.role not in ("admin", "member"):
        raise HTTPException(400, "Invalid role")
    u = User(
        name=data.name.strip(),
        email=email,
        password_hash=hash_password(data.password),
        role=data.role,
        is_active=True,
        created_at=now_iso(),
    )
    db.add(u)
    db.commit()
    db.refresh(u)
    return user_dict(u)


@app.delete("/api/users/{uid}")
def delete_user(
    uid: int, user: dict = Depends(get_current_user), db: Session = Depends(get_db)
):
    """Admin permanently deletes a user (and their boards/cards)."""
    require_admin(user)
    if uid == user["id"]:
        raise HTTPException(400, "You cannot delete yourself")
    u = db.get(User, uid)
    if not u:
        raise HTTPException(404, "User not found")
    if u.role == "admin":
        admin_count = db.query(func.count(User.id)).filter_by(role="admin").scalar()
        if admin_count <= 1:
            raise HTTPException(400, "Cannot delete the last admin")
    # delete boards created by this user (their lists & cards cascade)
    for b in db.query(Board).filter_by(created_by=uid).all():
        db.delete(b)
    # delete cards created by this user on other boards
    db.query(Card).filter_by(created_by=uid).delete(synchronize_session=False)
    # board memberships cascade; card assignees SET NULL automatically
    db.delete(u)
    db.commit()
    return {"ok": True}


# ---------------- board routes ----------------
@app.get("/api/boards")
def list_boards(user: dict = Depends(get_current_user), db: Session = Depends(get_db)):
    if user["role"] == "admin":
        boards = db.query(Board).order_by(Board.id.desc()).all()
    else:
        boards = (
            db.query(Board)
            .join(BoardMember, BoardMember.board_id == Board.id)
            .filter(BoardMember.user_id == user["id"])
            .order_by(Board.id.desc())
            .all()
        )
    return [{"id": b.id, "title": b.title, "description": b.description} for b in boards]


@app.post("/api/boards")
def create_board(
    data: BoardIn, user: dict = Depends(get_current_user), db: Session = Depends(get_db)
):
    b = Board(
        title=data.title.strip(),
        description=data.description.strip(),
        created_by=user["id"],
        created_at=now_iso(),
    )
    db.add(b)
    db.flush()
    db.add(BoardMember(board_id=b.id, user_id=user["id"], role="admin"))
    for i, title in enumerate(["To Do", "In Progress", "Done"]):
        db.add(List(board_id=b.id, title=title, position=i))
    db.commit()
    return board_detail(db, b.id)


@app.get("/api/boards/{bid}")
def get_board(
    bid: int, user: dict = Depends(get_current_user), db: Session = Depends(get_db)
):
    if not can_access_board(db, user, bid):
        raise HTTPException(403, "No access to this board")
    return board_detail(db, bid)


@app.delete("/api/boards/{bid}")
def delete_board(
    bid: int, user: dict = Depends(get_current_user), db: Session = Depends(get_db)
):
    if not is_board_admin(db, user, bid):
        raise HTTPException(403, "Board admin only")
    b = db.get(Board, bid)
    if b:
        # delete children first (portable across SQLite/Postgres)
        db.query(Card).filter_by(board_id=bid).delete()
        db.query(List).filter_by(board_id=bid).delete()
        db.query(BoardMember).filter_by(board_id=bid).delete()
        db.delete(b)
        db.commit()
    return {"ok": True}


@app.post("/api/boards/{bid}/members")
def add_member(
    bid: int, data: MemberAdd,
    user: dict = Depends(get_current_user), db: Session = Depends(get_db),
):
    if not is_board_admin(db, user, bid):
        raise HTTPException(403, "Board admin only")
    target = db.get(User, data.user_id)
    if not target or not target.is_active:
        raise HTTPException(404, "User not found or inactive")
    if data.role not in ("admin", "member"):
        raise HTTPException(400, "Invalid role")
    m = (
        db.query(BoardMember)
        .filter_by(board_id=bid, user_id=data.user_id)
        .first()
    )
    if m:
        m.role = data.role
    else:
        db.add(BoardMember(board_id=bid, user_id=data.user_id, role=data.role))
    db.commit()
    return {"ok": True}


@app.delete("/api/boards/{bid}/members/{uid}")
def remove_member(
    bid: int, uid: int,
    user: dict = Depends(get_current_user), db: Session = Depends(get_db),
):
    if not is_board_admin(db, user, bid):
        raise HTTPException(403, "Board admin only")
    db.query(BoardMember).filter_by(board_id=bid, user_id=uid).delete()
    db.commit()
    return {"ok": True}


# ---------------- list routes ----------------
@app.post("/api/boards/{bid}/lists")
def create_list(
    bid: int, data: ListIn,
    user: dict = Depends(get_current_user), db: Session = Depends(get_db),
):
    if not can_access_board(db, user, bid):
        raise HTTPException(403, "No access to this board")
    mx = db.query(func.max(List.position)).filter_by(board_id=bid).scalar()
    lst = List(board_id=bid, title=data.title.strip(), position=(mx or 0) + 1 if mx is not None else 0)
    db.add(lst)
    db.commit()
    db.refresh(lst)
    return {"id": lst.id, "title": lst.title, "cards": []}


@app.delete("/api/lists/{lid}")
def delete_list(
    lid: int, user: dict = Depends(get_current_user), db: Session = Depends(get_db)
):
    lst = db.get(List, lid)
    if not lst:
        raise HTTPException(404, "List not found")
    if not is_board_admin(db, user, lst.board_id):
        raise HTTPException(403, "Board admin only")
    db.query(Card).filter_by(list_id=lid).delete()
    db.delete(lst)
    db.commit()
    return {"ok": True}


# ---------------- card routes ----------------
@app.post("/api/lists/{lid}/cards")
def create_card(
    lid: int, data: CardIn,
    user: dict = Depends(get_current_user), db: Session = Depends(get_db),
):
    lst = db.get(List, lid)
    if not lst:
        raise HTTPException(404, "List not found")
    if not can_access_board(db, user, lst.board_id):
        raise HTTPException(403, "No access to this board")
    if data.assignee_id:
        ok = (
            db.query(BoardMember)
            .filter_by(board_id=lst.board_id, user_id=data.assignee_id)
            .first()
        )
        if not ok:
            raise HTTPException(400, "Assignee is not a board member")
    mx = db.query(func.max(Card.position)).filter_by(list_id=lid).scalar()
    c = Card(
        board_id=lst.board_id,
        list_id=lid,
        title=data.title.strip(),
        description=data.description.strip(),
        assignee_id=data.assignee_id,
        due_date=data.due_date,
        position=(mx + 1) if mx is not None else 0,
        created_by=user["id"],
        created_at=now_iso(),
    )
    db.add(c)
    db.commit()
    db.refresh(c)
    return {"id": c.id, "title": c.title}


@app.patch("/api/cards/{cid}")
def update_card(
    cid: int, data: CardMove,
    user: dict = Depends(get_current_user), db: Session = Depends(get_db),
):
    c = db.get(Card, cid)
    if not c:
        raise HTTPException(404, "Card not found")
    if not can_access_board(db, user, c.board_id):
        raise HTTPException(403, "No access to this board")
    if data.title is not None:
        c.title = data.title.strip()
    if data.description is not None:
        c.description = data.description.strip()
    if data.assignee_id is not None:
        ok = (
            db.query(BoardMember)
            .filter_by(board_id=c.board_id, user_id=data.assignee_id)
            .first()
        )
        if not ok:
            raise HTTPException(400, "Assignee is not a board member")
        c.assignee_id = data.assignee_id
    if data.due_date is not None:
        c.due_date = data.due_date or None
    if data.list_id is not None:
        lst = db.get(List, data.list_id)
        if not lst or lst.board_id != c.board_id:
            raise HTTPException(400, "Invalid target list")
        c.list_id = data.list_id
    if data.position is not None:
        c.position = data.position
    db.commit()
    return {"ok": True}


@app.delete("/api/cards/{cid}")
def delete_card(
    cid: int, user: dict = Depends(get_current_user), db: Session = Depends(get_db)
):
    c = db.get(Card, cid)
    if not c:
        raise HTTPException(404, "Card not found")
    if not can_access_board(db, user, c.board_id):
        raise HTTPException(403, "No access to this board")
    db.delete(c)
    db.commit()
    return {"ok": True}


# ---------------- frontend ----------------
if FRONTEND_DIR.exists():
    app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")
else:

    @app.get("/")
    def root():
        return {"status": "ok", "message": "Frontend not built yet"}
