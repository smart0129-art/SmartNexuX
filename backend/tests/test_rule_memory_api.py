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
    chunks = [
        {
            "id": "chatcmpl-rule-test",
            "object": "chat.completion.chunk",
            "created": 1,
            "model": "qwen2.5vl:3b",
            "choices": [
                {
                    "index": 0,
                    "delta": {"content": "Follow the SOP."},
                    "finish_reason": None,
                }
            ],
        },
        {
            "id": "chatcmpl-rule-test",
            "object": "chat.completion.chunk",
            "created": 1,
            "model": "qwen2.5vl:3b",
            "choices": [],
            "usage": {
                "prompt_tokens": 8,
                "completion_tokens": 3,
                "total_tokens": 11,
            },
        },
    ]
    body = "".join(
        f"data: {json.dumps(chunk)}\n\n" for chunk in chunks
    ) + "data: [DONE]\n\n"
    return httpx.Response(
        200,
        headers={"content-type": "text/event-stream"},
        content=body.encode(),
    )


class RuleMemoryApiTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.store = ConversationStore(
            str(Path(self.temporary_directory.name) / "rules.sqlite3")
        )
        self.store.ensure_schema()
        self.first_user = self.store.upsert_oidc_user(
            "https://issuer.example",
            "rule-owner",
            "owner@example.com",
            "Rule Owner",
        )
        self.second_user = self.store.upsert_oidc_user(
            "https://issuer.example",
            "other-user",
            "other@example.com",
            "Other User",
        )
        self.current_user = AuthenticatedUser(
            id=str(self.first_user["id"]),
            issuer=str(self.first_user["issuer"]),
            subject=str(self.first_user["subject"]),
            email=self.first_user["email"],
            display_name=str(self.first_user["display_name"]),
        )
        app.state.conversation_store = self.store
        app.dependency_overrides[get_current_user] = lambda: self.current_user

        self.provider_requests: list[dict[str, object]] = []

        def provider_handler(request: httpx.Request) -> httpx.Response:
            self.provider_requests.append(json.loads(request.content))
            return make_stream_response()

        self.provider_client = httpx.AsyncClient(
            transport=httpx.MockTransport(provider_handler)
        )
        self.router = ChatModelRouter(
            ollama_models="qwen2.5vl:3b",
            external_models="",
            default_provider="ollama",
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

    async def test_create_update_list_and_delete_are_owner_scoped(self) -> None:
        created = await self.api_client.post(
            "/api/rules",
            json={
                "equipment_keywords": [" CNC-900 ", "cnc-900"],
                "process_keywords": ["換線"],
                "content": "停止設備並確認防護罩固定。",
            },
        )
        self.assertEqual(created.status_code, 201)
        record = created.json()
        self.assertEqual(record["equipment_keywords"], ["CNC-900"])
        self.assertEqual(record["owner_id"], self.first_user["id"])

        self.current_user = AuthenticatedUser(
            id=str(self.second_user["id"]),
            issuer=str(self.second_user["issuer"]),
            subject=str(self.second_user["subject"]),
            email=self.second_user["email"],
            display_name=str(self.second_user["display_name"]),
        )
        self.assertEqual((await self.api_client.get("/api/rules")).json(), [])
        forbidden_update = await self.api_client.put(
            f"/api/rules/{record['rule_id']}",
            json={
                "equipment_keywords": ["CNC-900"],
                "process_keywords": [],
                "content": "Unauthorised change",
            },
        )
        self.assertEqual(forbidden_update.status_code, 404)

        self.current_user = AuthenticatedUser(
            id=str(self.first_user["id"]),
            issuer=str(self.first_user["issuer"]),
            subject=str(self.first_user["subject"]),
            email=self.first_user["email"],
            display_name=str(self.first_user["display_name"]),
        )
        updated = await self.api_client.put(
            f"/api/rules/{record['rule_id']}",
            json={
                "equipment_keywords": ["CNC-900"],
                "process_keywords": ["換線"],
                "content": "停機後執行鎖定掛牌並確認零能量。",
            },
        )
        self.assertEqual(updated.status_code, 200)
        self.assertEqual(
            updated.json()["content"],
            "停機後執行鎖定掛牌並確認零能量。",
        )
        self.assertEqual(len((await self.api_client.get("/api/rules")).json()), 1)

        deleted = await self.api_client.delete(f"/api/rules/{record['rule_id']}")
        self.assertEqual(deleted.status_code, 204)
        self.assertEqual((await self.api_client.get("/api/rules")).json(), [])

    async def test_rejects_rules_without_keywords_or_content(self) -> None:
        no_keywords = await self.api_client.post(
            "/api/rules",
            json={"content": "Do not operate the machine."},
        )
        blank_content = await self.api_client.post(
            "/api/rules",
            json={
                "equipment_keywords": ["CNC-900"],
                "content": "  ",
            },
        )
        self.assertEqual(no_keywords.status_code, 422)
        self.assertEqual(blank_content.status_code, 422)

    async def test_matching_rule_is_injected_before_rag_and_question(self) -> None:
        created = await self.api_client.post(
            "/api/rules",
            json={
                "equipment_keywords": ["CNC-900"],
                "process_keywords": ["換線"],
                "content": "先停機、執行鎖定掛牌，再開始換線。",
            },
        )
        self.assertEqual(created.status_code, 201)

        response = await self.api_client.post(
            "/api/chat/stream",
            json={"prompt": "CNC-900 換線前要做什麼？"},
        )

        self.assertEqual(response.status_code, 200)
        prompt = str(self.provider_requests[0]["messages"][1]["content"])
        section = "[強制防禦／最新SOP修正指引]"
        self.assertIn(section, prompt)
        self.assertLess(prompt.index(section), prompt.index("Current user request:"))
        self.assertIn("先停機、執行鎖定掛牌，再開始換線。", prompt)


if __name__ == "__main__":
    unittest.main()
