import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

from app.services.conversation_store import ConversationStore


class ConversationStoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.store = ConversationStore(
            str(Path(self.temporary_directory.name) / "test.sqlite3")
        )
        self.store.ensure_schema()
        self.first_user = self.store.upsert_oidc_user(
            "https://issuer.example",
            "subject-one",
            "one@example.com",
            "User One",
        )
        self.second_user = self.store.upsert_oidc_user(
            "https://issuer.example",
            "subject-two",
            "two@example.com",
            "User Two",
        )

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def test_oidc_identity_upsert_preserves_user_id(self) -> None:
        updated = self.store.upsert_oidc_user(
            "https://issuer.example",
            "subject-one",
            "updated@example.com",
            "Updated Name",
        )

        self.assertEqual(updated["id"], self.first_user["id"])
        self.assertEqual(updated["email"], "updated@example.com")

    def test_conversations_and_messages_are_owner_scoped(self) -> None:
        conversation = self.store.create_conversation(str(self.first_user["id"]))
        self.store.add_message(
            str(self.first_user["id"]),
            conversation["id"],
            "user",
            "  A useful question\nwith details  ",
            attachment_ids=["file-id"],
        )
        self.store.add_message(
            str(self.first_user["id"]),
            conversation["id"],
            "assistant",
            "An answer",
            usage={"total_tokens": 4},
        )

        loaded = self.store.get_conversation(
            str(self.first_user["id"]),
            conversation["id"],
        )
        other_user_view = self.store.get_conversation(
            str(self.second_user["id"]),
            conversation["id"],
        )

        self.assertEqual(loaded["title"], "A useful question with details")
        self.assertEqual(loaded["messages"][0]["attachment_ids"], ["file-id"])
        self.assertEqual(loaded["messages"][1]["usage"]["total_tokens"], 4)
        self.assertIsNone(other_user_view)
        self.assertEqual(
            self.store.list_conversations(str(self.second_user["id"])),
            [],
        )

    def test_document_listing_includes_shared_but_hides_other_private_documents(self) -> None:
        registered = self.store.register_document(
            str(self.first_user["id"]),
            "d74ae210-a60e-4a19-afd0-adde08a8f135",
            "private.pdf",
            3,
        )
        shared = self.store.register_document(
            str(self.first_user["id"]),
            "d74ae210-a60e-4a19-afd0-adde08a8f136",
            "shared.pdf",
            2,
            is_shared=True,
        )

        first_user_documents = self.store.list_documents(str(self.first_user["id"]))
        second_user_documents = self.store.list_documents(str(self.second_user["id"]))

        first_documents = {
            document["source_name"]: document for document in first_user_documents
        }
        second_documents = {
            document["source_name"]: document for document in second_user_documents
        }
        self.assertFalse(first_documents["private.pdf"]["is_shared"])
        self.assertTrue(first_documents["shared.pdf"]["is_shared"])
        self.assertEqual(first_documents["private.pdf"]["uploaded_at"], registered["uploaded_at"])
        self.assertEqual(first_documents["shared.pdf"]["uploaded_at"], shared["uploaded_at"])
        self.assertEqual(set(second_documents), {"shared.pdf"})

    def test_legacy_users_table_gets_password_hash_column(self) -> None:
        legacy_path = Path(self.temporary_directory.name) / "legacy.sqlite3"
        with closing(sqlite3.connect(legacy_path)) as connection:
            connection.execute(
                """
                CREATE TABLE users (
                    id TEXT PRIMARY KEY,
                    issuer TEXT NOT NULL,
                    subject TEXT NOT NULL,
                    email TEXT,
                    display_name TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    UNIQUE (issuer, subject)
                )
                """
            )
            connection.execute(
                """
                INSERT INTO users (
                    id, issuer, subject, email, display_name, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "legacy-user",
                    "https://issuer.example",
                    "legacy-subject",
                    "legacy@example.com",
                    "Legacy User",
                    "2026-01-01T00:00:00+00:00",
                    "2026-01-01T00:00:00+00:00",
                ),
            )
            connection.execute(
                """
                CREATE TABLE documents (
                    document_id TEXT PRIMARY KEY,
                    owner_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    source_name TEXT NOT NULL,
                    chunks_indexed INTEGER NOT NULL,
                    uploaded_at TEXT NOT NULL
                )
                """
            )
            connection.execute(
                """
                INSERT INTO documents (
                    document_id, owner_id, source_name, chunks_indexed, uploaded_at
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (
                    "legacy-document",
                    "legacy-user",
                    "legacy.pdf",
                    1,
                    "2026-01-01T00:00:00+00:00",
                ),
            )
            connection.commit()

        legacy_store = ConversationStore(str(legacy_path))
        legacy_store.ensure_schema()

        self.assertEqual(legacy_store.get_user("legacy-user")["email"], "legacy@example.com")
        with closing(sqlite3.connect(legacy_path)) as connection:
            user_columns = {
                row[1] for row in connection.execute("PRAGMA table_info(users)")
            }
            document_columns = {
                row[1] for row in connection.execute("PRAGMA table_info(documents)")
            }
        self.assertIn("password_hash", user_columns)
        self.assertIn("is_shared", document_columns)
        self.assertFalse(legacy_store.list_documents("legacy-user")[0]["is_shared"])


if __name__ == "__main__":
    unittest.main()
