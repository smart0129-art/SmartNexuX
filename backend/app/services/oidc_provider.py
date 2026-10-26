import os
from dataclasses import dataclass
from urllib.parse import urlparse

from authlib.integrations.starlette_client import OAuth


@dataclass(frozen=True)
class OIDCSettings:
    issuer_url: str
    client_id: str
    client_secret: str
    redirect_uri: str
    frontend_url: str

    @property
    def configured(self) -> bool:
        return bool(self.issuer_url and self.client_id and self.client_secret)

    @property
    def discovery_url(self) -> str:
        return f"{self.issuer_url.rstrip('/')}/.well-known/openid-configuration"

    @classmethod
    def from_environment(cls) -> "OIDCSettings":
        return cls(
            issuer_url=_https_or_local_http("OIDC_ISSUER_URL"),
            client_id=_trimmed("OIDC_CLIENT_ID"),
            client_secret=_trimmed("OIDC_CLIENT_SECRET"),
            redirect_uri=_trimmed(
                "OIDC_REDIRECT_URI",
                "http://localhost:8000/api/auth/callback",
            ),
            frontend_url=_trimmed("FRONTEND_URL", "http://localhost:3000").rstrip("/"),
        )


def build_oidc_client(settings: OIDCSettings) -> OAuth:
    oauth = OAuth()
    if settings.configured:
        oauth.register(
            name="oidc",
            client_id=settings.client_id,
            client_secret=settings.client_secret,
            server_metadata_url=settings.discovery_url,
            client_kwargs={"scope": "openid email profile"},
        )
    return oauth


def _trimmed(name: str, default: str = "") -> str:
    return os.getenv(name, default).strip()


def _https_or_local_http(name: str) -> str:
    value = os.getenv(name, "").strip().rstrip("/")
    if not value:
        return ""
    parsed = urlparse(value)
    if parsed.scheme != "https" and not (
        parsed.scheme == "http" and parsed.hostname in {"localhost", "127.0.0.1"}
    ):
        raise ValueError(f"{name} must use HTTPS (HTTP is allowed for localhost)")
    return value
