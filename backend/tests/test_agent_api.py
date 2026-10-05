import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import httpx

from app.auth import AuthenticatedUser, get_current_user
from app.api_models import AgentRunResponse
from app.main import app
from app.services.conversation_store import ConversationStore


class FakeAgentService:
    def __init__(self) -> None:
        self.prompt: str | None = None

    async def run(self, prompt: str) -> AgentRunResponse:
        self.prompt = prompt
        return AgentRunResponse(answer="Agent reply", tool_calls=[])


class AgentApiTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.conversation_store = ConversationStore(
            str(Path(self.temporary_directory.name) / "agent.sqlite3")
        )
        self.conversation_store.ensure_schema()
        stored_user = self.conversation_store.upsert_oidc_user(
            "https://issuer.example",
            "agent-subject",
            "agent@example.com",
            "Agent User",
        )
        self.user_id = str(stored_user["id"])
        app.state.conversation_store = self.conversation_store
        self.agent_service = FakeAgentService()
        app.state.agent_service = self.agent_service
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

    async def test_agent_uses_conversation_history_and_persists_turn(self) -> None:
        conversation = self.conversation_store.create_conversation(self.user_id)
        self.conversation_store.add_message(
            self.user_id,
            conversation["id"],
            "user",
            "Remember that the project codename is Atlas.",
        )
        self.conversation_store.add_message(
            self.user_id,
            conversation["id"],
            "assistant",
            "I will remember that.",
        )

        response = await self.client.post(
            "/api/agent/run",
            json={
                "prompt": "What is the project codename?",
                "conversation_id": conversation["id"],
            },
        )
        detail = await self.client.get(
            f"/api/conversations/{conversation['id']}"
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn("project codename is Atlas", self.agent_service.prompt or "")
        self.assertIn("What is the project codename?", self.agent_service.prompt or "")
        self.assertEqual(
            [message["role"] for message in detail.json()["messages"]],
            ["user", "assistant", "user", "assistant"],
        )

    async def test_agent_rejects_an_attachment_owned_by_another_user(self) -> None:
        conversation = self.conversation_store.create_conversation(self.user_id)
        other_user = self.conversation_store.upsert_oidc_user(
            "https://issuer.example",
            "another-subject",
            "another@example.com",
            "Another User",
        )
        document_id = str(uuid4())
        self.conversation_store.register_document(
            str(other_user["id"]),
            document_id,
            "private.txt",
            1,
        )

        response = await self.client.post(
            "/api/agent/run",
            json={
                "prompt": "Summarize this file.",
                "conversation_id": conversation["id"],
                "attachment_ids": [document_id],
            },
        )

        self.assertEqual(response.status_code, 404)
        self.assertIsNone(self.agent_service.prompt)

    async def test_agent_attaches_relevant_images_to_its_answer(self) -> None:
        conversation = self.conversation_store.create_conversation(self.user_id)
        document_id = str(uuid4())
        image_id = str(uuid4())
        self.conversation_store.register_document(
            self.user_id,
            document_id,
            "slides.pptx",
            1,
        )
        hits = [
            {
                "entity": {
                    "document_id": document_id,
                    "metadata": {
                        "source_name": "slides.pptx",
                        "slide_number": 2,
                        "image_asset_ids": [image_id],
                    },
                }
            }
        ]
        with patch(
            "app.main._build_workspace_prompt",
            new=AsyncMock(return_value=("prompt", hits)),
        ):
            response = await self.client.post(
                "/api/agent/run",
                json={
                    "prompt": "Explain the diagram.",
                    "conversation_id": conversation["id"],
                },
            )
        detail = await self.client.get(
            f"/api/conversations/{conversation['id']}"
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["images"][0]["image_id"], image_id)
        self.assertEqual(
            detail.json()["messages"][-1]["images"][0]["location"],
            "第 2 張投影片",
        )


if __name__ == "__main__":
    unittest.main()
