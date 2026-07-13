"""
试剑靶场系统 - 后端
FastAPI + SQLite + JWT
有意漏洞: GET /api/tasks?search= 用 f-string 拼接 SQL
"""

import json
import os
import sqlite3
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

import jwt
import uvicorn
from fastapi import FastAPI, File, Form, Header, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel, EmailStr, Field

# ---------------------------------------------------------------------------
# App & CORS
# ---------------------------------------------------------------------------

app = FastAPI(title="试剑靶场", version="3.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Serve frontend
FRONTEND_PATH = Path(__file__).resolve().parent / "index.html"


@app.get("/", response_class=HTMLResponse, include_in_schema=False)
def serve_frontend():
    if FRONTEND_PATH.exists():
        return HTMLResponse(FRONTEND_PATH.read_text(encoding="utf-8"))
    return HTMLResponse("<h1>Frontend not found</h1>", status_code=404)

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

SECRET_KEY = "shijian-v3-target-secret-key-2026"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 120
DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "target.db")

# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------


def get_db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db() -> None:
    conn = get_db()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            email TEXT NOT NULL,
            role TEXT NOT NULL DEFAULT 'user',
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            description TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL DEFAULT 'todo',
            priority TEXT NOT NULL DEFAULT 'medium',
            user_id INTEGER NOT NULL,
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at TEXT NOT NULL DEFAULT (datetime('now')),
            FOREIGN KEY (user_id) REFERENCES users(id)
        );
        INSERT OR IGNORE INTO users (id, username, password_hash, email, role)
        VALUES (1, 'admin',
                'pbkdf2:sha256:600000$fake$240be518fabd2724ddb6f04eeb1da596',
                'admin@shijian.test', 'admin');
    """)
    conn.commit()
    conn.close()


init_db()

# ---------------------------------------------------------------------------
# Pydantic Schemas (response_model)
# ---------------------------------------------------------------------------


class UserOut(BaseModel):
    id: int
    username: str
    email: str
    role: str
    created_at: str


class TaskOut(BaseModel):
    id: int
    title: str
    description: str
    status: str
    priority: str
    user_id: int
    created_at: str
    updated_at: str


class TaskWithUser(TaskOut):
    user: UserOut


class TaskCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)
    description: str = Field(default="", max_length=2000)
    priority: str = Field(default="medium", pattern=r"^(low|medium|high)$")


class TaskUpdate(BaseModel):
    title: Optional[str] = Field(default=None, min_length=1, max_length=200)
    description: Optional[str] = Field(default=None, max_length=2000)
    priority: Optional[str] = Field(default=None, pattern=r"^(low|medium|high)$")


class TaskStatusUpdate(BaseModel):
    status: str = Field(..., pattern=r"^(todo|doing|done|archived)$")


class RegisterIn(BaseModel):
    username: str = Field(..., min_length=2, max_length=50)
    password: str = Field(..., min_length=4, max_length=100)
    email: str = Field(..., max_length=100)


class LoginIn(BaseModel):
    username: str
    password: str


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut


class MessageOut(BaseModel):
    message: str


class ErrorOut(BaseModel):
    detail: str


class TaskPageOut(BaseModel):
    items: list[TaskOut]
    total: int
    page: int
    limit: int


class AdminUsersOut(BaseModel):
    users: list[UserOut]


class UploadOut(BaseModel):
    filename: str
    size: int
    message: str


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _hash_password(password: str) -> str:
    import hashlib
    return "pbkdf2:sha256:600000$fake$" + hashlib.sha256(password.encode()).hexdigest()[:32]


def _verify_password(plain: str, stored: str) -> bool:
    return _hash_password(plain) == stored


def _create_token(user_id: int, role: str) -> str:
    payload = {
        "sub": str(user_id),
        "role": role,
        "exp": datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES),
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def _get_current_user(authorization: Optional[str] = None) -> tuple[sqlite3.Row, str]:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(401, "Not authenticated")
    token = authorization[7:]
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except jwt.ExpiredSignatureError:
        raise HTTPException(401, "Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(401, "Invalid token")
    conn = get_db()
    user = conn.execute("SELECT * FROM users WHERE id = ?", (int(payload["sub"]),)).fetchone()
    conn.close()
    if not user:
        raise HTTPException(401, "User not found")
    return user, payload["role"]


def _row_to_task(row: sqlite3.Row) -> dict:
    return dict(row)


def _row_to_user(row: sqlite3.Row) -> dict:
    return {"id": row["id"], "username": row["username"], "email": row["email"],
            "role": row["role"], "created_at": row["created_at"]}

# ---------------------------------------------------------------------------
# Auth Endpoints
# ---------------------------------------------------------------------------


@app.post("/api/register", status_code=201, response_model=UserOut)
def register(body: RegisterIn):
    conn = get_db()
    try:
        cur = conn.execute(
            "INSERT INTO users (username, password_hash, email, role) VALUES (?, ?, ?, 'user')",
            (body.username, _hash_password(body.password), body.email),
        )
        conn.commit()
        user = conn.execute("SELECT * FROM users WHERE id = ?", (cur.lastrowid,)).fetchone()
        return _row_to_user(user)
    except sqlite3.IntegrityError:
        raise HTTPException(400, "Username already exists")
    finally:
        conn.close()


@app.post("/api/login", response_model=TokenOut)
def login(body: LoginIn):
    conn = get_db()
    user = conn.execute("SELECT * FROM users WHERE username = ?", (body.username,)).fetchone()
    conn.close()
    if not user or not _verify_password(body.password, user["password_hash"]):
        raise HTTPException(401, "Invalid username or password")
    token = _create_token(user["id"], user["role"])
    return {"access_token": token, "token_type": "bearer", "user": _row_to_user(user)}


@app.get("/api/me", response_model=UserOut)
def me(authorization: Optional[str] = Header(None, alias="Authorization", include_in_schema=False)):
    user, _ = _get_current_user(authorization)
    return _row_to_user(user)

# ---------------------------------------------------------------------------
# Task Endpoints
# ---------------------------------------------------------------------------


@app.get("/api/tasks", response_model=TaskPageOut)
def list_tasks(
    status: Optional[str] = Query(None, pattern=r"^(todo|doing|done|archived)?$"),
    page: int = Query(1, ge=1),
    limit: int = Query(10, ge=1, le=100),
    search: Optional[str] = Query(None),
    authorization: Optional[str] = Header(None, alias="Authorization", include_in_schema=False),
):
    _get_current_user(authorization)
    conn = get_db()

    # --- SQL 注入漏洞: f-string 拼接 search ---
    where_clauses: list[str] = []
    params: list = []

    if status:
        where_clauses.append("status = ?")
        params.append(status)

    if search:
        where_clauses.append(f"title LIKE '%{search}%'")  # 故意不安全！f-string 拼接
        # 注意：这里不用 params.append 因为已经拼进去了

    where_sql = " AND ".join(where_clauses) if where_clauses else "1=1"

    total = conn.execute(
        f"SELECT COUNT(*) FROM tasks WHERE {where_sql}", params
    ).fetchone()[0]

    offset = (page - 1) * limit
    rows = conn.execute(
        f"SELECT * FROM tasks WHERE {where_sql} ORDER BY created_at DESC LIMIT ? OFFSET ?",
        params + [limit, offset],
    ).fetchall()
    conn.close()

    return {
        "items": [dict(r) for r in rows],
        "total": total,
        "page": page,
        "limit": limit,
    }


@app.post("/api/tasks", status_code=201, response_model=TaskOut)
def create_task(
    body: TaskCreate,
    authorization: Optional[str] = Header(None, alias="Authorization", include_in_schema=False),
):
    user, _ = _get_current_user(authorization)
    conn = get_db()
    cur = conn.execute(
        "INSERT INTO tasks (title, description, priority, user_id) VALUES (?, ?, ?, ?)",
        (body.title, body.description, body.priority, user["id"]),
    )
    conn.commit()
    row = conn.execute("SELECT * FROM tasks WHERE id = ?", (cur.lastrowid,)).fetchone()
    conn.close()
    return dict(row)


@app.get("/api/tasks/{task_id}", response_model=TaskWithUser)
def get_task(
    task_id: int,
    authorization: Optional[str] = Header(None, alias="Authorization", include_in_schema=False),
):
    _get_current_user(authorization)
    conn = get_db()
    row = conn.execute(
        "SELECT tasks.*, users.id AS u_id, users.username, users.email, users.role, users.created_at AS u_created_at "
        "FROM tasks JOIN users ON tasks.user_id = users.id WHERE tasks.id = ?",
        (task_id,),
    ).fetchone()
    conn.close()
    if not row:
        raise HTTPException(404, "Task not found")
    task = dict(row)
    task["user"] = {
        "id": row["u_id"],
        "username": row["username"],
        "email": row["email"],
        "role": row["role"],
        "created_at": row["u_created_at"],
    }
    del task["u_id"], task["username"], task["email"], task["role"], task["u_created_at"]
    return task


@app.put("/api/tasks/{task_id}", response_model=TaskOut)
def update_task(
    task_id: int,
    body: TaskUpdate,
    authorization: Optional[str] = Header(None, alias="Authorization", include_in_schema=False),
):
    user, _ = _get_current_user(authorization)
    conn = get_db()
    task = conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
    if not task:
        conn.close()
        raise HTTPException(404, "Task not found")
    if task["user_id"] != user["id"] and user["role"] != "admin":
        conn.close()
        raise HTTPException(403, "Not authorized to update this task")

    updates: dict[str, str] = {}
    if body.title is not None:
        updates["title"] = body.title
    if body.description is not None:
        updates["description"] = body.description
    if body.priority is not None:
        updates["priority"] = body.priority

    if not updates:
        conn.close()
        raise HTTPException(400, "No fields to update")

    updates["updated_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    set_clause = ", ".join(f"{k} = ?" for k in updates)
    conn.execute(
        f"UPDATE tasks SET {set_clause} WHERE id = ?",
        list(updates.values()) + [task_id],
    )
    conn.commit()
    row = conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
    conn.close()
    return dict(row)


@app.put("/api/tasks/{task_id}/status", response_model=TaskOut)
def update_task_status(
    task_id: int,
    body: TaskStatusUpdate,
    authorization: Optional[str] = Header(None, alias="Authorization", include_in_schema=False),
):
    _get_current_user(authorization)
    conn = get_db()
    task = conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
    if not task:
        conn.close()
        raise HTTPException(404, "Task not found")

    flow = {"todo": "doing", "doing": "done", "done": "archived"}
    if body.status != flow.get(task["status"]) and body.status != "archived":
        conn.close()
        raise HTTPException(400, f"Invalid status transition: {task['status']} -> {body['status']}")

    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    conn.execute(
        "UPDATE tasks SET status = ?, updated_at = ? WHERE id = ?",
        (body.status, now, task_id),
    )
    conn.commit()
    row = conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
    conn.close()
    return dict(row)


@app.delete("/api/tasks/{task_id}", status_code=204)
def delete_task(
    task_id: int,
    authorization: Optional[str] = Header(None, alias="Authorization", include_in_schema=False),
):
    user, role = _get_current_user(authorization)
    if role != "admin":
        raise HTTPException(403, "Only admins can delete tasks")
    conn = get_db()
    task = conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
    if not task:
        conn.close()
        raise HTTPException(404, "Task not found")
    conn.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
    conn.commit()
    conn.close()
    return JSONResponse(status_code=204, content=None)

# ---------------------------------------------------------------------------
# Other Endpoints
# ---------------------------------------------------------------------------


@app.post("/api/upload", response_model=UploadOut)
async def upload_file(
    file: UploadFile = File(...),
    authorization: Optional[str] = Header(None, alias="Authorization", include_in_schema=False),
):
    _get_current_user(authorization)
    content = await file.read()
    return {
        "filename": file.filename or "unknown",
        "size": len(content),
        "message": "File uploaded successfully",
    }


@app.get("/api/slow", response_model=MessageOut)
def slow_endpoint(
    delay: int = Query(5, ge=1, le=30),
    seconds: Optional[int] = Query(None, ge=1, le=30),
):
    actual_delay = seconds or delay
    time.sleep(actual_delay)
    return {"message": f"Response after {actual_delay}s delay"}


@app.get("/api/debug")
def debug_endpoint():
    return {"status": "ok", "environment": "test"}


@app.get("/api/error/{code}")
def error_endpoint(code: int):
    status_map = {
        200: {"detail": "OK"},
        400: {"detail": "Bad request"},
        401: {"detail": "Unauthorized"},
        403: {"detail": "Forbidden"},
        404: {"detail": "Not found"},
        422: {"detail": "Unprocessable entity"},
        500: {"detail": "Internal server error"},
        503: {"detail": "Service unavailable"},
    }
    if code not in status_map:
        raise HTTPException(400, "Supported codes: 200, 400, 401, 403, 404, 422, 500")
    if code == 200:
        return status_map[code]
    raise HTTPException(code, status_map[code]["detail"])


@app.get("/api/admin/users", response_model=AdminUsersOut)
def admin_users(
    authorization: Optional[str] = Header(None, alias="Authorization", include_in_schema=False),
):
    _, role = _get_current_user(authorization)
    if role != "admin":
        raise HTTPException(403, "Admin access required")
    conn = get_db()
    rows = conn.execute("SELECT * FROM users").fetchall()
    conn.close()
    return {"users": [_row_to_user(r) for r in rows]}

# ---------------------------------------------------------------------------
# Entry
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8003, reload=False)
