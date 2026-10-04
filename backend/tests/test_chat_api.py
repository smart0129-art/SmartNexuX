import json
import tempfile
import unittest
from pathlib import Path

import httpx

from app.auth import AuthenticatedUser, get_current_user
from app.main import app
from app.services.chat_router import ChatModelRouter
from app.services.conversation_store import ConversationStore


def make_stream_response() -> httpx.Response:
    parts = [
        {
            "id": "chatcmpl-api",
            "object": "chat.completion.chunk",
            "created": 1,
            "model": "qwen2.5vl:3b",
            "choices": [
                {
                    "index": 0,
                    "delta": {"content": "Hello"},
                    "finish_reason": None,
                }
            ],
        },
        {
            "id": "chatcmpl-api",
            "object": "chat.completion.chunk",
            "created": 1,
            "model": "qwen2.5vl:3b",
            "choices": [],
            "usage": {
                "prompt_tokens": 7,
                "completion_tokens": 1,
                "total_tokens": 8,
            },
        },
    ]
    body = "".join(
        f"data: {json.dumps(part)}\n\n"
        for part in parts
    ) + "data: [DONE]\n\n"
    return httpx.Response(
        200,
        headers={"content-type": "text/event-stream"},
        content=body.encode(),
    )


class ChatApiTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.conversation_store = ConversationStore(
            str(Path(self.temporary_directory.name) / "test.sqlite3")
        )
        self.conversation_store.ensure_schema()
        stored_user = self.conversation_store.upsert_oidc_user(
            "https://issuer.example",
            "test-subject",
            "test@example.com",
            "Test User",
        )
        app.state.conversation_store = self.conversation_store
        app.dependency_overrides[get_current_user] = lambda: AuthenticatedUser(
            id=str(stored_user["id"]),
            issuer=str(stored_user["issuer"]),
            subject=str(stored_user["subject"]),
            email=stored_user["email"],
            display_name=str(stored_user["display_name"]),
        )
        self.provider_client = httpx.AsyncClient(
            transport=httpx.MockTransport(
                lambda request: make_stream_response()
            )
        )
        self.router = ChatModelRouter(
            ollama_models="qwen2.5vl:3b",
            external_models="gpt-4o-mini",
            external_api_key="",
            http_client=self.provider_client,
        )
        app.state.chat_model_router = self.router
        self.api_client = httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://test",
        )

    async def asyncTearDown(self) -> None:
        await self.api_client.aclose()
        await self.router.close()
        await self.provider_client.aclose()
        app.dependency_overrides.clear()
        self.temporary_directory.cleanup()

    async def test_lists_models_and_streams_sse_token_and_usage(self) -> None:
        catalog = await self.api_client.get("/api/models")

        self.assertEqual(catalog.status_code, 200)
        self.assertEqual(catalog.json()["default_model"], "qwen2.5vl:3b")
        self.assertFalse(catalog.json()["models"][1]["configured"])

        response = await self.api_client.post(
            "/api/chat/stream",
            json={"prompt": "Say hello."},
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn("text/event-stream", response.headers["content-type"])
        self.assertIn(
            'event: meta\ndata: {"provider":"ollama","model":"qwen2.5vl:3b",'
            '"conversation_id":null}',
            response.text,
        )
        self.assertIn('event: token\ndata: {"token":"Hello"}', response.text)
        self.assertIn('"prompt_tokens":7', response.text)
        self.assertIn('"source":"provider"', response.text)

    async def test_stream_persists_messages_for_the_owning_conversation(self) -> None:
        created = await self.api_client.post("/api/conversations", json={})
        conversation_id = created.json()["id"]

        response = await self.api_client.post(
            "/api/chat/stream",
            json={
                "prompt": "Say hello.",
                "conversation_id": conversation_id,
            },
        )
        detail = await self.api_client.get(
            f"/api/conversations/{conversation_id}"
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(detail.status_code, 200)
        self.assertEqual(
            [message["role"] for message in detail.json()["messages"]],
            ["user", "assistant"],
        )
        self.assertEqual(detail.json()["messages"][1]["content"], "Hello")
        self.assertEqual(
            detail.json()["messages"][1]["usage"]["source"],
            "provider",
        )
        other_user = self.conversation_store.upsert_oidc_user(
            "https://issuer.example",
            "other-subject",
            "other@example.com",
            "Other User",
        )
        app.dependency_overrides[get_current_user] = lambda: AuthenticatedUser(
            id=str(other_user["id"]),
            issuer=str(other_user["issuer"]),
            subject=str(other_user["subject"]),
            email=other_user["email"],
            display_name=str(other_user["display_name"]),
        )
        private_detail = await self.api_client.get(
            f"/api/conversations/{conversation_id}"
        )
        other_sessions = await self.api_client.get("/api/conversations")

        self.assertEqual(private_detail.status_code, 404)
        self.assertEqual(other_sessions.json(), [])

    async def test_rejects_unconfigured_models_and_external_provider(self) -> None:
        unknown_model = await self.api_client.post(
            "/api/chat/stream",
            json={"prompt": "Hello", "model": "not-configured"},
        )
        missing_key = await self.api_client.post(
            "/api/chat/stream",
            json={
                "prompt": "Hello",
                "provider": "openai_compatible",
                "model": "gpt-4o-mini",
            },
        )

        self.assertEqual(unknown_model.status_code, 422)
        self.assertEqual(missing_key.status_code, 503)


if __name__ == "__main__":
    unittest.main()
