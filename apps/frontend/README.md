# frontend

`apps/frontend` is the Next.js user interface for AutoDS.

It connects to the FastAPI backend and provides chat, session management, dataset upload, and artifact browsing.

## Commands

```bash
make frontend-install
make frontend-dev
make frontend-lint
make frontend-build
```

Or manually:

```bash
cd apps/frontend
npm install
npm run dev
```

## Environment

The frontend reads `NEXT_PUBLIC_API_URL` and defaults to `http://localhost:8000`.

Create `apps/frontend/.env.local` if you need to point the UI at a different backend.
