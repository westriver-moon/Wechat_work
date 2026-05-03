import json
import os
import secrets
import sqlite3
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

BASE_DIR = Path(__file__).resolve().parent
_DB_PATH = Path(os.getenv("DB_PATH", str(BASE_DIR / "feature3.db")))


def set_db_path(path: str) -> None:
    global _DB_PATH
    _DB_PATH = Path(path)


def get_db_path() -> Path:
    return _DB_PATH


def _now_ts() -> int:
    return int(time.time())


def _dict_row(row: Optional[sqlite3.Row]) -> Optional[Dict[str, Any]]:
    if row is None:
        return None
    return dict(row)


def _connect() -> sqlite3.Connection:
    _DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(_DB_PATH), timeout=30, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA foreign_keys=ON;")
    return conn


def init_db() -> None:
    with _connect() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                identity TEXT UNIQUE NOT NULL,
                role TEXT NOT NULL DEFAULT 'freshman',
                source TEXT NOT NULL DEFAULT 'web',
                nickname TEXT,
                created_at INTEGER NOT NULL
            );

            CREATE TABLE IF NOT EXISTS questions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                from_user_id INTEGER NOT NULL,
                title TEXT,
                content TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending',
                view_code TEXT NOT NULL,
                channel TEXT NOT NULL DEFAULT 'web',
                client_id TEXT,
                created_at INTEGER NOT NULL,
                updated_at INTEGER NOT NULL,
                FOREIGN KEY (from_user_id) REFERENCES users(id)
            );

            CREATE TABLE IF NOT EXISTS answers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                question_id INTEGER UNIQUE NOT NULL,
                answerer_id INTEGER,
                answer_type TEXT NOT NULL DEFAULT 'senior',
                content TEXT NOT NULL,
                created_at INTEGER NOT NULL,
                updated_at INTEGER NOT NULL,
                FOREIGN KEY (question_id) REFERENCES questions(id),
                FOREIGN KEY (answerer_id) REFERENCES users(id)
            );

            CREATE TABLE IF NOT EXISTS tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                type TEXT NOT NULL,
                payload TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'queued',
                attempts INTEGER NOT NULL DEFAULT 0,
                max_attempts INTEGER NOT NULL DEFAULT 5,
                last_error TEXT,
                created_at INTEGER NOT NULL,
                updated_at INTEGER NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_questions_status ON questions(status);
            CREATE INDEX IF NOT EXISTS idx_questions_client_id ON questions(client_id);
            CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status);

            CREATE TABLE IF NOT EXISTS auth_identities (
                student_code TEXT PRIMARY KEY,
                display_name TEXT,
                permissions INTEGER NOT NULL DEFAULT 0,
                enabled INTEGER NOT NULL DEFAULT 1,
                note TEXT,
                created_at INTEGER NOT NULL,
                updated_at INTEGER NOT NULL
            );
            """
        )


def get_or_create_user(identity: str, role: str = "freshman", source: str = "web", nickname: str = "") -> Dict[str, Any]:
    now = _now_ts()
    with _connect() as conn:
        row = conn.execute("SELECT * FROM users WHERE identity = ?", (identity,)).fetchone()
        if row is not None:
            return dict(row)

        conn.execute(
            "INSERT INTO users (identity, role, source, nickname, created_at) VALUES (?, ?, ?, ?, ?)",
            (identity, role, source, nickname, now),
        )
        row = conn.execute("SELECT * FROM users WHERE identity = ?", (identity,)).fetchone()
        return dict(row)


def set_user_role(identity: str, role: str, source: str = "manual") -> Dict[str, Any]:
    user = get_or_create_user(identity=identity, role=role, source=source)
    with _connect() as conn:
        conn.execute("UPDATE users SET role = ? WHERE id = ?", (role, user["id"]))
        row = conn.execute("SELECT * FROM users WHERE id = ?", (user["id"],)).fetchone()
        return dict(row)


def create_question(
    from_user_id: int,
    content: str,
    title: str = "",
    channel: str = "web",
    client_id: Optional[str] = None,
    view_code: Optional[str] = None,
) -> Dict[str, Any]:
    now = _now_ts()
    safe_view_code = view_code or secrets.token_hex(4).upper()
    with _connect() as conn:
        cur = conn.execute(
            """
            INSERT INTO questions (from_user_id, title, content, status, view_code, channel, client_id, created_at, updated_at)
            VALUES (?, ?, ?, 'pending', ?, ?, ?, ?, ?)
            """,
            (from_user_id, title or "", content, safe_view_code, channel, client_id, now, now),
        )
        qid = int(cur.lastrowid)
    return {"id": qid, "view_code": safe_view_code}


def get_question(question_id: int) -> Optional[Dict[str, Any]]:
    with _connect() as conn:
        row = conn.execute(
            """
            SELECT
                q.*,
                u.identity AS from_user_identity,
                u.role AS from_user_role,
                COALESCE(NULLIF(u.nickname, ''), u.identity) AS from_user_display
            FROM questions q
            JOIN users u ON u.id = q.from_user_id
            WHERE q.id = ?
            """,
            (question_id,),
        ).fetchone()
        return _dict_row(row)


def get_tracked_question(question_id: int, view_code: str) -> Optional[Dict[str, Any]]:
    with _connect() as conn:
        row = conn.execute(
            """
            SELECT
                q.id,
                q.title,
                q.content,
                q.status,
                q.view_code,
                q.channel,
                q.created_at,
                COALESCE(NULLIF(u.nickname, ''), u.identity) AS from_user_display,
                a.content AS answer,
                a.answer_type,
                a.updated_at AS answered_at
            FROM questions q
            JOIN users u ON u.id = q.from_user_id
            LEFT JOIN answers a ON a.question_id = q.id
            WHERE q.id = ? AND q.view_code = ?
            """,
            (question_id, view_code),
        ).fetchone()
        return _dict_row(row)


def list_questions_by_client(client_id: str, limit: int = 50) -> List[Dict[str, Any]]:
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT
                q.id,
                q.title,
                q.content,
                q.status,
                q.view_code,
                q.channel,
                q.created_at,
                q.updated_at,
                a.content AS answer,
                a.answer_type,
                a.updated_at AS answered_at
            FROM questions q
            LEFT JOIN answers a ON a.question_id = q.id
            WHERE q.client_id = ?
            ORDER BY q.id DESC
            LIMIT ?
            """,
            (client_id, limit),
        ).fetchall()
        return [dict(r) for r in rows]


def list_questions_by_owner_identity(owner_identity: str, limit: int = 50) -> List[Dict[str, Any]]:
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT
                q.id,
                q.title,
                q.content,
                q.status,
                q.view_code,
                q.channel,
                q.created_at,
                q.updated_at,
                a.content AS answer,
                a.answer_type,
                a.updated_at AS answered_at
            FROM questions q
            JOIN users u ON u.id = q.from_user_id
            LEFT JOIN answers a ON a.question_id = q.id
            WHERE u.identity = ?
            ORDER BY q.id DESC
            LIMIT ?
            """,
            (owner_identity, limit),
        ).fetchall()
        return [dict(r) for r in rows]


def list_pending_questions(limit: int = 50) -> List[Dict[str, Any]]:
    return list_pending_questions_with_query(limit=limit, query="")


def list_pending_questions_with_query(limit: int = 50, query: str = "") -> List[Dict[str, Any]]:
    query = (query or "").strip()
    safe_limit = max(1, min(int(limit), 300))
    with _connect() as conn:
        if query:
            like = f"%{query}%"
            rows = conn.execute(
                """
                SELECT
                    q.id,
                    q.title,
                    q.content,
                    q.status,
                    q.view_code,
                    q.channel,
                    q.created_at,
                    u.identity AS from_user_identity,
                    COALESCE(NULLIF(u.nickname, ''), u.identity) AS from_user_display
                FROM questions q
                JOIN users u ON u.id = q.from_user_id
                WHERE q.status = 'pending'
                  AND (
                    CAST(q.id AS TEXT) LIKE ?
                    OR q.title LIKE ?
                    OR q.content LIKE ?
                    OR q.view_code LIKE ?
                    OR u.identity LIKE ?
                  )
                ORDER BY q.id ASC
                LIMIT ?
                """,
                (like, like, like, like, like, safe_limit),
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT
                    q.id,
                    q.title,
                    q.content,
                    q.status,
                    q.view_code,
                    q.channel,
                    q.created_at,
                    u.identity AS from_user_identity,
                    COALESCE(NULLIF(u.nickname, ''), u.identity) AS from_user_display
                FROM questions q
                JOIN users u ON u.id = q.from_user_id
                WHERE q.status = 'pending'
                ORDER BY q.id ASC
                LIMIT ?
                """,
                (safe_limit,),
            ).fetchall()
        return [dict(r) for r in rows]


def list_answered_questions(limit: int = 50, query: str = "") -> List[Dict[str, Any]]:
    query = (query or "").strip()
    safe_limit = max(1, min(int(limit), 300))
    with _connect() as conn:
        if query:
            like = f"%{query}%"
            rows = conn.execute(
                """
                SELECT
                    q.id,
                    q.title,
                    q.content,
                    q.status,
                    q.view_code,
                    q.channel,
                    q.created_at,
                    q.updated_at,
                    u.identity AS from_user_identity,
                    COALESCE(NULLIF(u.nickname, ''), u.identity) AS from_user_display,
                    a.content AS answer,
                    a.answer_type,
                    a.updated_at AS answered_at,
                    su.identity AS answerer_identity,
                    su.nickname AS answerer_nickname,
                    COALESCE(NULLIF(su.nickname, ''), su.identity) AS answerer_display
                FROM questions q
                JOIN users u ON u.id = q.from_user_id
                JOIN answers a ON a.question_id = q.id
                LEFT JOIN users su ON su.id = a.answerer_id
                WHERE q.status IN ('answered', 'closed')
                  AND (
                    CAST(q.id AS TEXT) LIKE ?
                    OR q.title LIKE ?
                    OR q.content LIKE ?
                    OR q.view_code LIKE ?
                    OR u.identity LIKE ?
                    OR a.content LIKE ?
                    OR COALESCE(su.nickname, '') LIKE ?
                    OR COALESCE(su.identity, '') LIKE ?
                  )
                ORDER BY a.updated_at DESC, q.id DESC
                LIMIT ?
                """,
                (like, like, like, like, like, like, like, like, safe_limit),
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT
                    q.id,
                    q.title,
                    q.content,
                    q.status,
                    q.view_code,
                    q.channel,
                    q.created_at,
                    q.updated_at,
                    u.identity AS from_user_identity,
                    COALESCE(NULLIF(u.nickname, ''), u.identity) AS from_user_display,
                    a.content AS answer,
                    a.answer_type,
                    a.updated_at AS answered_at,
                    su.identity AS answerer_identity,
                    su.nickname AS answerer_nickname,
                    COALESCE(NULLIF(su.nickname, ''), su.identity) AS answerer_display
                FROM questions q
                JOIN users u ON u.id = q.from_user_id
                JOIN answers a ON a.question_id = q.id
                LEFT JOIN users su ON su.id = a.answerer_id
                WHERE q.status IN ('answered', 'closed')
                ORDER BY a.updated_at DESC, q.id DESC
                LIMIT ?
                """,
                (safe_limit,),
            ).fetchall()
        return [dict(r) for r in rows]


def save_answer(
    question_id: int,
    content: str,
    answerer_id: Optional[int] = None,
    answer_type: str = "senior",
) -> Dict[str, Any]:
    now = _now_ts()
    with _connect() as conn:
        existing = conn.execute(
            "SELECT id FROM answers WHERE question_id = ?",
            (question_id,),
        ).fetchone()
        if existing is None:
            conn.execute(
                """
                INSERT INTO answers (question_id, answerer_id, answer_type, content, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (question_id, answerer_id, answer_type, content, now, now),
            )
        else:
            conn.execute(
                """
                UPDATE answers
                SET answerer_id = ?, answer_type = ?, content = ?, updated_at = ?
                WHERE question_id = ?
                """,
                (answerer_id, answer_type, content, now, question_id),
            )

        conn.execute(
            "UPDATE questions SET status = 'answered', updated_at = ? WHERE id = ?",
            (now, question_id),
        )

        row = conn.execute(
            "SELECT * FROM answers WHERE question_id = ?",
            (question_id,),
        ).fetchone()
        return dict(row)


def close_question(question_id: int, owner_identity: Optional[str] = None, view_code: Optional[str] = None) -> bool:
    with _connect() as conn:
        row = conn.execute(
            """
            SELECT q.id, q.view_code, u.identity AS owner_identity
            FROM questions q
            JOIN users u ON u.id = q.from_user_id
            WHERE q.id = ?
            """,
            (question_id,),
        ).fetchone()
        if row is None:
            return False

        if owner_identity and row["owner_identity"] != owner_identity:
            return False
        if view_code and row["view_code"] != view_code:
            return False

        conn.execute(
            "UPDATE questions SET status = 'closed', updated_at = ? WHERE id = ?",
            (_now_ts(), question_id),
        )
        return True


def enqueue_task(task_type: str, payload: Dict[str, Any], max_attempts: int = 5) -> int:
    now = _now_ts()
    payload_text = json.dumps(payload, ensure_ascii=False)
    with _connect() as conn:
        cur = conn.execute(
            """
            INSERT INTO tasks (type, payload, status, attempts, max_attempts, last_error, created_at, updated_at)
            VALUES (?, ?, 'queued', 0, ?, '', ?, ?)
            """,
            (task_type, payload_text, max_attempts, now, now),
        )
        return int(cur.lastrowid)


def claim_next_task() -> Optional[Dict[str, Any]]:
    conn = _connect()
    try:
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute(
            """
            SELECT *
            FROM tasks
            WHERE status = 'queued' AND attempts < max_attempts
            ORDER BY id ASC
            LIMIT 1
            """
        ).fetchone()
        if row is None:
            conn.commit()
            return None

        task_id = int(row["id"])
        conn.execute(
            "UPDATE tasks SET status = 'processing', attempts = attempts + 1, updated_at = ? WHERE id = ?",
            (_now_ts(), task_id),
        )
        updated = conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
        conn.commit()

        task = dict(updated)
        try:
            task["payload"] = json.loads(task.get("payload") or "{}")
        except Exception:
            task["payload"] = {}
        return task
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def mark_task_done(task_id: int) -> None:
    with _connect() as conn:
        conn.execute(
            "UPDATE tasks SET status = 'done', updated_at = ? WHERE id = ?",
            (_now_ts(), task_id),
        )


def mark_task_retry(task_id: int, error: str) -> None:
    with _connect() as conn:
        row = conn.execute(
            "SELECT attempts, max_attempts FROM tasks WHERE id = ?",
            (task_id,),
        ).fetchone()
        if row is None:
            return

        attempts = int(row["attempts"])
        max_attempts = int(row["max_attempts"])
        next_status = "failed" if attempts >= max_attempts else "queued"
        conn.execute(
            "UPDATE tasks SET status = ?, last_error = ?, updated_at = ? WHERE id = ?",
            (next_status, error[:400], _now_ts(), task_id),
        )


def get_task_summary() -> Dict[str, int]:
    with _connect() as conn:
        rows = conn.execute("SELECT status, COUNT(*) AS cnt FROM tasks GROUP BY status").fetchall()
        summary = {"queued": 0, "processing": 0, "done": 0, "failed": 0}
        for r in rows:
            summary[str(r["status"])] = int(r["cnt"])
        return summary


def get_auth_identity(student_code: str) -> Optional[Dict[str, Any]]:
    with _connect() as conn:
        row = conn.execute(
            "SELECT * FROM auth_identities WHERE student_code = ?",
            (student_code,),
        ).fetchone()
        return _dict_row(row)


def upsert_auth_identity(
    student_code: str,
    display_name: str = "",
    permissions: int = 0,
    enabled: bool = True,
    note: str = "",
) -> Dict[str, Any]:
    now = _now_ts()
    with _connect() as conn:
        existing = conn.execute(
            "SELECT student_code FROM auth_identities WHERE student_code = ?",
            (student_code,),
        ).fetchone()
        if existing is None:
            conn.execute(
                """
                INSERT INTO auth_identities (student_code, display_name, permissions, enabled, note, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (student_code, display_name, int(permissions), 1 if enabled else 0, note, now, now),
            )
        else:
            conn.execute(
                """
                UPDATE auth_identities
                SET display_name = ?, permissions = ?, enabled = ?, note = ?, updated_at = ?
                WHERE student_code = ?
                """,
                (display_name, int(permissions), 1 if enabled else 0, note, now, student_code),
            )
        row = conn.execute(
            "SELECT * FROM auth_identities WHERE student_code = ?",
            (student_code,),
        ).fetchone()
        return dict(row)
