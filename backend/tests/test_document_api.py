import json
from collections.abc import Iterator
from io import BytesIO
import tempfile
import unittest
import zipfile
from pathlib import Path
from typing import Any
from uuid import uuid4

import httpx
import pymupdf

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
                metadata={
                    "source_name": source_path.name,
                    **(
                        {"page_number": 1}
                        if source_path.suffix == ".pdf"
                        else {}
                    ),
                },
            )
        ]


class FakeEmbeddingClient:
    async def embed_texts(self, texts: list[str]) -> list[list[float]]:
        return [[0.1, 0.2, 0.3, 0.4] for _ in texts]


class FakeMilvusStore:
    def __init__(self) -> None:
        self.records: list[dict[str, Any]] = []
        self.embedding_dimension = 4

    def insert_chunks(self, records: list[dict[str, Any]]) -> int:
        self.records.extend(records)
        return len(records)

    def iter_document_chunks(
        self,
        owner_id: str,
        document_id: str,
        is_shared: bool = False,
    ) -> Iterator[dict[str, Any]]:
        return (
            record
            for record in self.records
            if record["document_id"] == document_id
            and (
                record["metadata"]["owner_id"] == owner_id
                or (
                    is_shared
                    and record["metadata"].get("visibility") == "shared"
                )
            )
        )

    def hybrid_search(
        self,
        query: str,
        query_embedding: list[float],
        limit: int,
        document_id: str | None = None,
        owner_id: str | None = None,
    ) -> list[list[dict[str, Any]]]:
        matching_records = [
            record
            for record in self.records
            if (
                record["metadata"]["owner_id"] == str(owner_id)
                or record["metadata"].get("visibility") == "shared"
            )
            and (
                document_id is None
                or record["document_id"] == str(document_id)
            )
        ][:limit]
        return [[
            {
                "id": record["id"],
                "distance": 0.9,
                "entity": {
                    key: record[key]
                    for key in ("document_id", "chunk_index", "content", "metadata")
                },
            }
            for record in matching_records
        ]]

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
        app.state.document_image_dir = Path(self.temporary_directory.name) / "images"
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
        if hasattr(app.state, "document_image_dir"):
            del app.state.document_image_dir
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
        self.assertFalse(response.json()["is_shared"])
        self.assertEqual(
            self.milvus_store.records[0]["metadata"]["visibility"],
            "private",
        )

    async def test_shared_document_is_available_to_other_users(self) -> None:
        private_response = await self.client.post(
            "/api/documents",
            files={"file": ("private.txt", b"Private content", "text/plain")},
        )
        shared_response = await self.client.post(
            "/api/documents",
            files={"file": ("shared.txt", b"Shared content", "text/plain")},
            data={"is_shared": "true"},
        )
        self.assertEqual(private_response.status_code, 201)
        self.assertEqual(shared_response.status_code, 201)
        self.assertFalse(private_response.json()["is_shared"])
        self.assertTrue(shared_response.json()["is_shared"])

        shared_document_id = shared_response.json()["document_id"]
        shared_record = next(
            record
            for record in self.milvus_store.records
            if record["document_id"] == shared_document_id
        )
        image_id = uuid4()
        shared_record["metadata"]["image_asset_ids"] = [str(image_id)]
        image_path = (
            app.state.document_image_dir
            / shared_document_id
            / f"{image_id.hex}.jpg"
        )
        image_path.parent.mkdir(parents=True)
        image_path.write_bytes(b"shared-image")

        other_user = self.conversation_store.upsert_oidc_user(
            "https://issuer.example",
            "shared-document-subject",
            "shared@example.com",
            "Shared User",
        )
        other_user_id = str(other_user["id"])
        app.dependency_overrides[get_current_user] = lambda: AuthenticatedUser(
            id=other_user_id,
            issuer=str(other_user["issuer"]),
            subject=str(other_user["subject"]),
            email=other_user["email"],
            display_name=str(other_user["display_name"]),
        )

        documents = await self.client.get("/api/documents")
        search = await self.client.post(
            "/api/search",
            json={"query": "shared content"},
        )
        image = await self.client.get(
            f"/api/documents/{shared_document_id}/images/{image_id}"
        )

        self.assertEqual(documents.status_code, 200)
        self.assertEqual(
            [document["source_name"] for document in documents.json()],
            ["shared.txt"],
        )
        self.assertTrue(documents.json()[0]["is_shared"])
        self.assertEqual(search.status_code, 200, search.text)
        self.assertEqual(
            [result["document_id"] for result in search.json()["results"]],
            [shared_document_id],
        )
        self.assertEqual(image.status_code, 200)
        self.assertEqual(image.content, b"shared-image")

    async def test_document_images_are_private_to_the_document_owner(self) -> None:
        document_id = uuid4()
        image_id = uuid4()
        self.conversation_store.register_document(
            self.user_id,
            str(document_id),
            "report.pdf",
            1,
        )
        image_path = (
            app.state.document_image_dir
            / str(document_id)
            / f"{image_id.hex}.jpg"
        )
        image_path.parent.mkdir(parents=True)
        image_path.write_bytes(b"image")

        owner_response = await self.client.get(
            f"/api/documents/{document_id}/images/{image_id}"
        )

        self.assertEqual(owner_response.status_code, 200)
        self.assertEqual(owner_response.headers["content-type"], "image/jpeg")
        self.assertEqual(owner_response.headers["cache-control"], "private, no-store")
        self.assertEqual(owner_response.content, b"image")

        other_user = self.conversation_store.upsert_oidc_user(
            "https://issuer.example",
            "other-document-subject",
            "other-document@example.com",
            "Other Document User",
        )
        app.dependency_overrides[get_current_user] = lambda: AuthenticatedUser(
            id=str(other_user["id"]),
            issuer=str(other_user["issuer"]),
            subject=str(other_user["subject"]),
            email=other_user["email"],
            display_name=str(other_user["display_name"]),
        )
        private_response = await self.client.get(
            f"/api/documents/{document_id}/images/{image_id}"
        )

        self.assertEqual(private_response.status_code, 404)

    async def test_upload_indexes_and_serves_a_relevant_pdf_page_image(self) -> None:
        document = pymupdf.open()
        page = document.new_page()
        page.draw_rect(pymupdf.Rect(30, 30, 160, 110), color=(0, 0, 1))
        pdf_data = document.tobytes()
        document.close()

        response = await self.client.post(
            "/api/documents",
            files={"file": ("chart.pdf", pdf_data, "application/pdf")},
        )

        self.assertEqual(response.status_code, 201)
        image_ids = self.milvus_store.records[0]["metadata"]["image_asset_ids"]
        self.assertEqual(len(image_ids), 1)
        image_response = await self.client.get(
            f"/api/documents/{response.json()['document_id']}/images/{image_ids[0]}"
        )
        self.assertEqual(image_response.status_code, 200)
        self.assertGreater(len(image_response.content), 100)

    async def test_rag_archive_import_merges_and_skips_repeated_documents(self) -> None:
        document_id = str(uuid4())
        image_id = uuid4()
        self.conversation_store.register_document(
            self.user_id,
            document_id,
            "report.pdf",
            1,
            is_shared=True,
        )
        self.milvus_store.records.append(
            {
                "id": f"{document_id}:0",
                "document_id": document_id,
                "chunk_index": 0,
                "content": "Searchable indexed content",
                "embedding": [0.1, 0.2, 0.3, 0.4],
                "metadata": {
                    "owner_id": self.user_id,
                    "visibility": "shared",
                    "source_name": "report.pdf",
                    "image_asset_ids": [str(image_id)],
                    "page_number": 1,
                },
            }
        )
        source_image = (
            app.state.document_image_dir
            / document_id
            / f"{image_id.hex}.jpg"
        )
        source_image.parent.mkdir(parents=True)
        source_image.write_bytes(b"indexed-image")

        export_response = await self.client.get("/api/documents/export")
        self.assertEqual(export_response.status_code, 200)
        with zipfile.ZipFile(BytesIO(export_response.content)) as archive:
            manifest = json.loads(archive.read("manifest.json"))
            self.assertEqual(
                manifest["documents"][0]["source_document_id"],
                document_id,
            )
            self.assertTrue(manifest["documents"][0]["is_shared"])
            self.assertIn(
                f"images/{document_id}/{image_id}.jpg",
                archive.namelist(),
            )
            chunks = json.loads(
                archive.read(f"chunks/{document_id}.jsonl").splitlines()[0]
            )
            self.assertNotIn("owner_id", chunks["metadata"])

        destination_store = ConversationStore(
            str(Path(self.temporary_directory.name) / "destination.sqlite3")
        )
        destination_store.ensure_schema()
        destination_user = destination_store.upsert_oidc_user(
            "https://issuer.example",
            "rag-destination",
            "destination@example.com",
            "Destination User",
        )
        destination_id = str(destination_user["id"])
        destination_milvus = FakeMilvusStore()
        destination_image_dir = (
            Path(self.temporary_directory.name) / "destination-images"
        )
        app.state.conversation_store = destination_store
        app.state.milvus_store = destination_milvus
        app.state.document_image_dir = destination_image_dir
        app.dependency_overrides[get_current_user] = lambda: AuthenticatedUser(
            id=destination_id,
            issuer=str(destination_user["issuer"]),
            subject=str(destination_user["subject"]),
            email=destination_user["email"],
            display_name=str(destination_user["display_name"]),
        )
        import_response = await self.client.post(
            "/api/documents/import",
            files={
                "file": (
                    "RAG.zip",
                    export_response.content,
                    "application/zip",
                )
            },
        )

        self.assertEqual(import_response.status_code, 200, import_response.text)
        self.assertEqual(import_response.json(), {"imported": 1, "skipped": 0})
        destination_documents = destination_store.list_documents(destination_id)
        self.assertEqual(len(destination_documents), 1)
        self.assertTrue(destination_documents[0]["is_shared"])
        destination_document_id = str(destination_documents[0]["document_id"])
        self.assertEqual(destination_document_id, document_id)
        self.assertEqual(
            destination_store.imported_document_ids(destination_id)[document_id],
            destination_document_id,
        )
        imported_record = next(
            record
            for record in destination_milvus.records
            if record["document_id"] == destination_document_id
            and record["metadata"]["owner_id"] == destination_id
        )
        self.assertEqual(imported_record["content"], "Searchable indexed content")
        self.assertEqual(imported_record["embedding"], [0.1, 0.2, 0.3, 0.4])
        image_response = await self.client.get(
            f"/api/documents/{destination_document_id}/images/{image_id}"
        )
        self.assertEqual(image_response.status_code, 200)
        self.assertEqual(image_response.content, b"indexed-image")

        repeated_import = await self.client.post(
            "/api/documents/import",
            files={
                "file": (
                    "RAG.zip",
                    export_response.content,
                    "application/zip",
                )
            },
        )
        self.assertEqual(repeated_import.status_code, 200, repeated_import.text)
        self.assertEqual(repeated_import.json(), {"imported": 0, "skipped": 1})
        self.assertEqual(
            len(destination_store.list_documents(destination_id)),
            1,
        )


if __name__ == "__main__":
    unittest.main()
