import tempfile
import unittest
from pathlib import Path

import httpx

from app.main import app
from app.services.conversation_store import ConversationStore


class AuthApiTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        app.dependency_overrides.clear()
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.conversation_store = ConversationStore(
            str(Path(self.temporary_directory.name) / "auth.sqlite3")
        )
        self.conversation_store.ensure_schema()
        app.state.conversation_store = self.conversation_store
        self.client = httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://test",
        )

    async def asyncTearDown(self) -> None:
        await self.client.aclose()
        self.temporary_directory.cleanup()

    async def test_protected_resources_require_login(self) -> None:
        response = await self.client.get("/api/conversations")

        self.assertEqual(response.status_code, 401)

    async def test_register_login_and_logout(self) -> None:
        registered = await self.client.post(
            "/api/auth/register",
            json={
                "email": "  Test.User@Example.com ",
                "display_name": " Test User ",
                "password": "correct horse battery",
            },
        )

        self.assertEqual(registered.status_code, 201)
        self.assertEqual(registered.json()["email"], "test.user@example.com")
        self.assertEqual(registered.json()["display_name"], "Test User")
        stored_user = self.conversation_store.get_local_user_for_authentication(
            "test.user@example.com"
        )
        self.assertIsNotNone(stored_user)
        self.assertNotEqual(stored_user["password_hash"], "correct horse battery")

        await self.client.post("/api/auth/logout")
        signed_in = await self.client.post(
            "/api/auth/login",
            json={
                "email": "TEST.USER@example.com",
                "password": "correct horse battery",
            },
        )
        self.assertEqual(signed_in.status_code, 200)
        self.assertEqual(signed_in.json()["id"], registered.json()["id"])
        self.assertEqual((await self.client.get("/api/auth/me")).status_code, 200)

        await self.client.post("/api/auth/logout")
        self.assertEqual((await self.client.get("/api/auth/me")).status_code, 401)

    async def test_duplicate_registration_and_invalid_login_are_rejected(self) -> None:
        account = {
            "email": "person@example.com",
            "password": "valid-password",
        }
        self.assertEqual(
            (await self.client.post("/api/auth/register", json=account)).status_code,
            201,
        )
        duplicate = await self.client.post("/api/auth/register", json=account)
        self.assertEqual(duplicate.status_code, 409)

        invalid_login = await self.client.post(
            "/api/auth/login",
            json={**account, "password": "wrong-password"},
        )
        unknown_login = await self.client.post(
            "/api/auth/login",
            json={"email": "missing@example.com", "password": "wrong-password"},
        )
        self.assertEqual(invalid_login.status_code, 401)
        self.assertEqual(unknown_login.status_code, 401)
        self.assertEqual(invalid_login.json(), unknown_login.json())

    async def test_untrusted_browser_origin_cannot_mutate_api(self) -> None:
        response = await self.client.post(
            "/api/auth/register",
            headers={"Origin": "https://attacker.example"},
            json={
                "email": "person@example.com",
                "password": "valid-password",
            },
        )

        self.assertEqual(response.status_code, 403)


if __name__ == "__main__":
    unittest.main()
