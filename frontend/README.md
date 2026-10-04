# NexuX frontend

This is the Next.js App Router dashboard for the Multimodal AI Knowledge Platform.
It uses Tailwind CSS, Zustand for dashboard UI state, and Lucide icons.

## Run with Docker

From the project root:

```powershell
docker compose up --build -d frontend
docker compose logs --tail 100 frontend
```

Open <http://localhost:3000>. The frontend container runs the Next.js development
server and mounts the source directory for live reload. Phase 4.1 provides the
dashboard shell and theme. Phase 4.2 connects OIDC sign-in, model selection,
SSE chat, owner-scoped document upload/search, Agent skills, and conversation
history stored in the `nexux-data` SQLite volume. The dashboard interface is
presented in Traditional Chinese (`zh-Hant`).

## OIDC setup

Copy the root `.env.example` to `.env`, then set `OIDC_ISSUER_URL`,
`OIDC_CLIENT_ID`, `OIDC_CLIENT_SECRET`, and a strong random `SESSION_SECRET`.
Register `OIDC_REDIRECT_URI` as an allowed callback URL with the identity
provider. Keep `.env` local and never paste or commit the client secret.

For HTTPS deployments, set `COOKIE_SECURE=true` and use HTTPS for both the
frontend and OIDC callback URLs. The default HTTP URLs are for local development
only.

To stop the services while retaining database volumes:

```powershell
docker compose down
```

## Local Node.js

If Node.js 22 or newer is installed on the host, the app can also run directly:

```powershell
npm ci
npm run dev
```

Then open <http://localhost:3000>.
