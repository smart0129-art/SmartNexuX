import os
import unittest
from unittest.mock import patch

from app.services.oidc_provider import OIDCSettings, build_oidc_client


class OIDCSettingsTests(unittest.TestCase):
    def test_builds_generic_discovery_configuration(self) -> None:
        environment = {
            "OIDC_ISSUER_URL": "https://identity.example.test/realm",
            "OIDC_CLIENT_ID": "test-client",
            "OIDC_CLIENT_SECRET": "test-only-placeholder",
        }
        with patch.dict(os.environ, environment, clear=True):
            settings = OIDCSettings.from_environment()
            client = build_oidc_client(settings)

        self.assertTrue(settings.configured)
        self.assertEqual(
            settings.discovery_url,
            "https://identity.example.test/realm/.well-known/openid-configuration",
        )
        self.assertIsNotNone(client.create_client("oidc"))

    def test_http_issuer_is_only_allowed_for_localhost(self) -> None:
        with patch.dict(
            os.environ,
            {"OIDC_ISSUER_URL": "http://identity.example.test"},
            clear=True,
        ):
            with self.assertRaisesRegex(ValueError, "must use HTTPS"):
                OIDCSettings.from_environment()

    def test_client_secret_is_required_to_enable_oidc(self) -> None:
        environment = {
            "OIDC_ISSUER_URL": "https://identity.example.test",
            "OIDC_CLIENT_ID": "test-client",
            "OIDC_CLIENT_SECRET": "",
        }
        with patch.dict(os.environ, environment, clear=True):
            settings = OIDCSettings.from_environment()

        self.assertFalse(settings.configured)


if __name__ == "__main__":
    unittest.main()
