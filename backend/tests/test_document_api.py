import tempfile
import unittest
from pathlib import Path
from typing import Any
from uuid import uuid4

import httpx

from app.auth import AuthenticatedUser, get_current_user
from app.main import app
from app.services.conversation_store import ConversationStore
from app.services.document_parser import DocumentChunk


class FakeDocumentParser:
    async def parse(self, source_path: Path) -> list[DocumentChunk]:
        self.filename = source_path.name
        return [
            DocumentChunk(
                chunk_index=0,
                content="A private test document.",
                metadata={"source_name": source_path.name},
            )
        ]


class FakeEmbeddingClient:
    async def embed_texts(self, texts: list[str]) -> list[list[float]]:
        return [[0.1, 0.2, 0.3, 0.4] for _ in texts]


class FakeMilvusStore:
    def __init__(self) -> None:
        self.records: list[dict[str, Any]] = []

    def insert_chunks(self, records: list[dict[str, Any]]) -> int:
        self.records.extend(records)
        return len(records)

    def delete_document(self, document_id: str) -> int:
        self.records = [
            record
            for record in self.records
            if record["document_id"] != str(document_id)
        ]
        return 1


class DocumentApiTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.conversation_store = ConversationStore(
            str(Path(self.temporary_directory.name) / "documents.sqlite3")
        )
        self.conversation_store.ensure_schema()
        stored_user = self.conversation_store.upsert_oidc_user(
            "https://issuer.example",
            "document-subject",
            "document@example.com",
            "Document User",
        )
        self.user_id = str(stored_user["id"])
        self.parser = FakeDocumentParser()
        self.milvus_store = FakeMilvusStore()
        app.state.conversation_store = self.conversation_store
        app.state.document_parser = self.parser
        app.state.embedding_client = FakeEmbeddingClient()
        app.state.milvus_store = self.milvus_store
        app.dependency_overrides.clear()
        app.dependency_overrides[get_current_user] = lambda: AuthenticatedUser(
            id=self.user_id,
            issuer=str(stored_user["issuer"]),
            subject=str(stored_user["subject"]),
            email=stored_user["email"],
            display_name=str(stored_user["display_name"]),
        )
        self.client = httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://test",
        )

    async def asyncTearDown(self) -> None:
        await self.client.aclose()
        app.dependency_overrides.clear()
        self.temporary_directory.cleanup()

    async def test_upload_registers_owner_and_returns_timestamp(self) -> None:
        response = await self.client.post(
            "/api/documents",
            files={"file": ("private.txt", b"Private document content", "text/plain")},
        )
        documents = await self.client.get("/api/documents")

        self.assertEqual(response.status_code, 201)
        self.assertEqual(len(self.milvus_store.records), 1)
        self.assertEqual(
            self.milvus_store.records[0]["metadata"]["owner_id"],
            self.user_id,
        )
        self.assertEqual(documents.json()[0]["document_id"], response.json()["document_id"])
        self.assertEqual(documents.json()[0]["uploaded_at"], response.json()["uploaded_at"])
        self.assertEqual(response.json()["source_name"], "private.txt")


if __name__ == "__main__":
    unittest.main()
