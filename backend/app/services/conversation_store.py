import json
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator, Literal
from uuid import uuid4


class ConversationStore:
    def __init__(self, database_path: str | None = None) -> None:
        self.database_path = database_path or os.getenv(
            "DATABASE_PATH", "/data/nexux.sqlite3"
        )

    def _connect(self) -> sqlite3.Connection:
        if self.database_path != ":memory:":
            Path(self.database_path).parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.database_path, timeout=15)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 15000")
        return connection

    @contextmanager
    def _connection(self) -> Iterator[sqlite3.Connection]:
        connection = self._connect()
        try:
            yield connection
            connection.commit()
        except BaseException:
            connection.rollback()
            raise
        finally:
            connection.close()

    def ensure_schema(self) -> None:
        with self._connection() as connection:
            connection.execute("PRAGMA journal_mode = WAL")
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS users (
                    id TEXT PRIMARY KEY,
                    issuer TEXT NOT NULL,
                    subject TEXT NOT NULL,
                    email TEXT,
                    display_name TEXT NOT NULL,
                    password_hash TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    UNIQUE (issuer, subject)
                );
                CREATE TABLE IF NOT EXISTS conversations (
                    id TEXT PRIMARY KEY,
                    owner_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    title TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS conversations_owner_updated
                    ON conversations(owner_id, updated_at DESC);
                CREATE TABLE IF NOT EXISTS messages (
                    id TEXT PRIMARY KEY,
                    conversation_id TEXT NOT NULL
                        REFERENCES conversations(id) ON DELETE CASCADE,
                    role TEXT NOT NULL CHECK (role IN ('user', 'assistant')),
                    content TEXT NOT NULL,
                    metadata_json TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS messages_conversation_created
                    ON messages(conversation_id, created_at);
                CREATE TABLE IF NOT EXISTS documents (
                    document_id TEXT PRIMARY KEY,
                    owner_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    source_name TEXT NOT NULL,
                    chunks_indexed INTEGER NOT NULL,
                    uploaded_at TEXT NOT NULL,
                    is_shared INTEGER NOT NULL DEFAULT 0
                );
                CREATE INDEX IF NOT EXISTS documents_owner_uploaded
                    ON documents(owner_id, uploaded_at DESC);
                CREATE TABLE IF NOT EXISTS imported_documents (
                    owner_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    source_document_id TEXT NOT NULL,
                    document_id TEXT NOT NULL UNIQUE
                        REFERENCES documents(document_id) ON DELETE CASCADE,
                    PRIMARY KEY (owner_id, source_document_id)
                );
                """
            )
            user_columns = {
                row["name"] for row in connection.execute("PRAGMA table_info(users)")
            }
            if "password_hash" not in user_columns:
                connection.execute("ALTER TABLE users ADD COLUMN password_hash TEXT")
            document_columns = {
                row["name"]
                for row in connection.execute("PRAGMA table_info(documents)")
            }
            if "is_shared" not in document_columns:
                connection.execute(
                    "ALTER TABLE documents "
                    "ADD COLUMN is_shared INTEGER NOT NULL DEFAULT 0"
                )

    def upsert_oidc_user(
        self,
        issuer: str,
        subject: str,
        email: str | None,
        display_name: str,
    ) -> dict[str, str | None]:
        now = _now()
        user_id = str(uuid4())
        with self._connection() as connection:
            connection.execute(
                """
                INSERT INTO users (
                    id, issuer, subject, email, display_name, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(issuer, subject) DO UPDATE SET
                    email = excluded.email,
                    display_name = excluded.display_name,
                    updated_at = excluded.updated_at
                """,
                (user_id, issuer, subject, email, display_name, now, now),
            )
            row = connection.execute(
                "SELECT id, issuer, subject, email, display_name "
                "FROM users WHERE issuer = ? AND subject = ?",
                (issuer, subject),
            ).fetchone()
        if row is None:
            raise RuntimeError("OIDC user upsert did not return a user")
        return dict(row)

    def create_local_user(
        self,
        email: str,
        display_name: str,
        password_hash: str,
    ) -> dict[str, str | None] | None:
        now = _now()
        user_id = str(uuid4())
        with self._connection() as connection:
            cursor = connection.execute(
                """
                INSERT INTO users (
                    id, issuer, subject, email, display_name, password_hash,
                    created_at, updated_at
                ) VALUES (?, 'local', ?, ?, ?, ?, ?, ?)
                ON CONFLICT(issuer, subject) DO NOTHING
                """,
                (
                    user_id,
                    email,
                    email,
                    display_name,
                    password_hash,
                    now,
                    now,
                ),
            )
            if cursor.rowcount == 0:
                return None
            row = connection.execute(
                "SELECT id, issuer, subject, email, display_name "
                "FROM users WHERE issuer = 'local' AND subject = ?",
                (email,),
            ).fetchone()
        if row is None:
            raise RuntimeError("Local user creation did not return a user")
        return dict(row)

    def get_local_user_for_authentication(
        self,
        email: str,
    ) -> dict[str, str | None] | None:
        with self._connection() as connection:
            row = connection.execute(
                "SELECT id, email, display_name, password_hash "
                "FROM users WHERE issuer = 'local' AND subject = ?",
                (email,),
            ).fetchone()
        return dict(row) if row is not None else None

    def get_user(self, user_id: str) -> dict[str, str | None] | None:
        with self._connection() as connection:
            row = connection.execute(
                "SELECT id, issuer, subject, email, display_name "
                "FROM users WHERE id = ?",
                (user_id,),
            ).fetchone()
        return dict(row) if row is not None else None

    def create_conversation(
        self,
        owner_id: str,
        title: str = "New conversation",
    ) -> dict[str, str]:
        conversation_id = str(uuid4())
        now = _now()
        with self._connection() as connection:
            connection.execute(
                """
                INSERT INTO conversations (id, owner_id, title, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (conversation_id, owner_id, title, now, now),
            )
        return {
            "id": conversation_id,
            "title": title,
            "created_at": now,
            "updated_at": now,
        }

    def list_conversations(self, owner_id: str) -> list[dict[str, str]]:
        with self._connection() as connection:
            rows = connection.execute(
                """
                SELECT id, title, created_at, updated_at
                FROM conversations
                WHERE owner_id = ?
                ORDER BY updated_at DESC
                """,
                (owner_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    def get_conversation(
        self,
        owner_id: str,
        conversation_id: str,
    ) -> dict[str, Any] | None:
        with self._connection() as connection:
            conversation = connection.execute(
                """
                SELECT id, title, created_at, updated_at
                FROM conversations
                WHERE id = ? AND owner_id = ?
                """,
                (conversation_id, owner_id),
            ).fetchone()
            if conversation is None:
                return None
            messages = connection.execute(
                """
                SELECT id, role, content, metadata_json, created_at
                FROM messages
                WHERE conversation_id = ?
                ORDER BY created_at, rowid
                """,
                (conversation_id,),
            ).fetchall()
        return {
            **dict(conversation),
            "messages": [_message_record(message) for message in messages],
        }

    def add_message(
        self,
        owner_id: str,
        conversation_id: str,
        role: Literal["user", "assistant"],
        content: str,
        *,
        usage: dict[str, Any] | None = None,
        tool_calls: list[dict[str, Any]] | None = None,
        attachment_ids: list[str] | None = None,
        images: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any] | None:
        now = _now()
        metadata = {
            "usage": usage,
            "tool_calls": tool_calls or [],
            "attachment_ids": attachment_ids or [],
            "images": images or [],
        }
        message_id = str(uuid4())
        with self._connection() as connection:
            conversation = connection.execute(
                "SELECT title FROM conversations WHERE id = ? AND owner_id = ?",
                (conversation_id, owner_id),
            ).fetchone()
            if conversation is None:
                return None
            connection.execute(
                """
                INSERT INTO messages (id, conversation_id, role, content, metadata_json, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    message_id,
                    conversation_id,
                    role,
                    content,
                    json.dumps(metadata, ensure_ascii=False),
                    now,
                ),
            )
            title = conversation["title"]
            if role == "user" and title == "New conversation":
                title = _conversation_title(content)
            connection.execute(
                """
                UPDATE conversations
                SET title = ?, updated_at = ?
                WHERE id = ? AND owner_id = ?
                """,
                (title, now, conversation_id, owner_id),
            )
        return {
            "id": message_id,
            "role": role,
            "content": content,
            **metadata,
            "created_at": now,
        }

    def delete_conversation(self, owner_id: str, conversation_id: str) -> bool:
        with self._connection() as connection:
            cursor = connection.execute(
                "DELETE FROM conversations WHERE id = ? AND owner_id = ?",
                (conversation_id, owner_id),
            )
        return cursor.rowcount > 0

    def register_document(
        self,
        owner_id: str,
        document_id: str,
        source_name: str,
        chunks_indexed: int,
        is_shared: bool = False,
    ) -> dict[str, Any]:
        uploaded_at = _now()
        with self._connection() as connection:
            connection.execute(
                """
                INSERT INTO documents
                    (
                        document_id, owner_id, source_name, chunks_indexed,
                        uploaded_at, is_shared
                    )
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    document_id,
                    owner_id,
                    source_name,
                    chunks_indexed,
                    uploaded_at,
                    int(is_shared),
                ),
            )
        return {
            "document_id": document_id,
            "source_name": source_name,
            "chunks_indexed": chunks_indexed,
            "uploaded_at": uploaded_at,
            "is_shared": is_shared,
        }

    def list_documents(self, owner_id: str) -> list[dict[str, Any]]:
        with self._connection() as connection:
            rows = connection.execute(
                """
                SELECT document_id, source_name, chunks_indexed, uploaded_at,
                       is_shared
                FROM documents
                WHERE owner_id = ? OR is_shared = 1
                ORDER BY uploaded_at DESC
                """,
                (owner_id,),
            ).fetchall()
        return [
            {
                **dict(row),
                "is_shared": bool(row["is_shared"]),
            }
            for row in rows
        ]

    def imported_document_ids(self, owner_id: str) -> dict[str, str]:
        with self._connection() as connection:
            rows = connection.execute(
                """
                SELECT source_document_id, document_id
                FROM imported_documents
                WHERE owner_id = ?
                """,
                (owner_id,),
            ).fetchall()
        return {
            str(row["source_document_id"]): str(row["document_id"])
            for row in rows
        }

    def document_owner(self, document_id: str) -> str | None:
        with self._connection() as connection:
            row = connection.execute(
                "SELECT owner_id FROM documents WHERE document_id = ?",
                (document_id,),
            ).fetchone()
        return str(row["owner_id"]) if row is not None else None

    def register_imported_document(
        self,
        owner_id: str,
        source_document_id: str,
        document_id: str,
        source_name: str,
        chunks_indexed: int,
        uploaded_at: str,
        is_shared: bool = False,
    ) -> None:
        with self._connection() as connection:
            connection.execute(
                """
                INSERT INTO documents
                    (
                        document_id, owner_id, source_name, chunks_indexed,
                        uploaded_at, is_shared
                    )
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    document_id,
                    owner_id,
                    source_name,
                    chunks_indexed,
                    uploaded_at,
                    int(is_shared),
                ),
            )
            connection.execute(
                """
                INSERT INTO imported_documents
                    (owner_id, source_document_id, document_id)
                VALUES (?, ?, ?)
                """,
                (owner_id, source_document_id, document_id),
            )

    def remove_imported_document(
        self,
        owner_id: str,
        source_document_id: str,
        document_id: str,
    ) -> None:
        with self._connection() as connection:
            connection.execute(
                """
                DELETE FROM imported_documents
                WHERE owner_id = ? AND source_document_id = ? AND document_id = ?
                """,
                (owner_id, source_document_id, document_id),
            )
            connection.execute(
                "DELETE FROM documents WHERE document_id = ? AND owner_id = ?",
                (document_id, owner_id),
            )


def _message_record(row: sqlite3.Row) -> dict[str, Any]:
    metadata = json.loads(row["metadata_json"])
    return {
        "id": row["id"],
        "role": row["role"],
        "content": row["content"],
        "usage": metadata.get("usage"),
        "tool_calls": metadata.get("tool_calls", []),
        "attachment_ids": metadata.get("attachment_ids", []),
        "images": metadata.get("images", []),
        "created_at": row["created_at"],
    }


def _conversation_title(content: str) -> str:
    title = " ".join(content.split())
    if len(title) > 72:
        return f"{title[:69].rstrip()}..."
    return title or "New conversation"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()
