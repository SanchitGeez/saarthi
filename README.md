# Saarthi

A minimal FastAPI API and React Native app using Expo and TypeScript.

## API

Requires Python 3.11+ and [uv](https://docs.astral.sh/uv/).

```sh
cd backend
uv sync
uv run uvicorn main:app --reload
```

`GET http://localhost:8000/health` returns `{"status":"ok"}`.
Interactive API docs: <http://localhost:8000/docs>.

## Mobile

Requires Node.js 22.13+ and npm.

```sh
cd mobile
npm ci
npm start
```

Open in Expo Go, or press `a` for an Android emulator or `i` for an iOS
simulator (macOS). Use `npm run web` for the browser.

Start building in `mobile/App.tsx`. Check TypeScript with `npm run typecheck`.

## Backup

The previous application, including the last uncommitted icon change, is preserved
on the remote branch `backup/full-app-2026-10-17`.
