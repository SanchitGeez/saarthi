# Saarthi

A private conversation companion inspired by the Bhagavad Gita. Talk with Parth in a temple setting, or use Type. The first build targets Android and iOS with Expo React Native and a small FastAPI service.

Saarthi is an original AI companion, not a deity or therapist. Supports live calls with LiveKit, English/Hindi/Hinglish text, voice notes, spoken replies, separate conversations, and selective cross-chat memory. Saarthi saves finalized call transcripts but does not record call audio. Speech and AI providers may retain data under their own policies.

## Start locally

1. Copy the root `.env.example` to `.env` if this checkout does not already have one, then set `GOOGLE_API_KEY`. Gemini handles chat responses. Local development may also read the optional OpenAI-compatible embedding and ElevenLabs speech credentials from `../mindlap/.env`; it uses its separate `SAARTHI_DATABASE_URL` and ignores that project's database settings.
2. Start this project's PostgreSQL database with `docker compose up -d postgres`.
3. Install the API dependencies from `backend` with `uv sync`, then run `uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000` from that directory. The API is at `http://localhost:8000`; its interactive docs are at `http://localhost:8000/docs`.
4. If `mobile/.env` is missing, copy `mobile/.env.example` to it. For a physical phone, set `EXPO_PUBLIC_API_URL=http://<your-laptop-Wi-Fi-IP>:8000/api`; `10.0.2.2` works only in the Android emulator. Install mobile dependencies with `npm install` in `mobile`.
5. For live calls, add `LIVEKIT_URL`, `LIVEKIT_API_KEY`, and `LIVEKIT_API_SECRET` to the root `.env`. The configured ElevenLabs account needs funded realtime STT and TTS access. From `backend`, run `uv run python -m app.voice_worker download-files` once, then run `uv run python -m app.voice_worker dev` alongside the API. The worker name must match `LIVEKIT_AGENT_NAME`.
6. From `mobile`, run `npm run android` to build/install the native Android app, or `npm run ios` on macOS. LiveKit needs native WebRTC modules, so use a development build rather than Expo Go. Keep the device and laptop on the same Wi-Fi. A production build connects to your deployed API and a running worker. Expo Go can still use Type; trying a live call shows a build requirement.

When the API runs in development without SMTP settings, the sign-in screen receives the one-time code directly so local setup works. Production requires SMTP values and a strong `JWT_SECRET`; it never returns the sign-in code to the app.

If scanning stays on a spinner, open `http://<your-laptop-Wi-Fi-IP>:8081/status` in the phone's browser. It should show `packager-status:running`. If it cannot connect, resolve the Wi-Fi/VPN/firewall issue or try Expo's `--tunnel` connection (the backend still needs a phone-reachable address). If Metro is reachable, check Expo Go's detailed error log and SDK compatibility. Run `npm run doctor` from `mobile` for config/dependency checks; restart Metro after dependency or environment changes.

## Services and data

The mobile app sends authenticated requests to FastAPI. FastAPI verifies the account, owns conversation and memory rules, and calls a single Google ADK Runner configured with the Gemini model in `GEMINI_MODEL` (default `gemini-3.8-flash`). The `chat_turns` table is the delivery record: one user message, reply, and processing/completed/failed state per stable ID. Each ADK invocation reconstructs context from successful typed exchanges and finalized voice messages; failed events cannot pollute the next prompt. Existing ADK history is imported lazily when opened. A single configurable fallback Gemini model is tried on upstream 429/503, within the same deadline.

The text app owns these PostgreSQL tables: `users`, `conversations`, `chat_turns`, `memories`, and short-lived `auth_codes`. PostgreSQL with pgvector stores an embedding next to each memory when the optional OpenAI-compatible embedding endpoint is configured. Memory retrieval uses bounded, owner-scoped text ranking and includes useful preferences/context even when exact query words do not match. Embeddings remain optional for edited memories. Live calls add `voice_sessions` and `voice_messages`. Both are additive tables created at startup for existing local databases. There is no audio recording table, object store, or job queue. A LiveKit worker runs only while a call is active; PostgreSQL supplies continuity between calls.

Email codes use SMTP in production and a development-only code response locally. ElevenLabs handles speech-to-text and on-demand text-to-speech. Recordings are uploaded for transcription and discarded on success. A failed note stays temporarily on the device for Retry/Discard and is cleared when the chat screen unmounts; it is not restored on app launch. Spoken replies are returned as a response and held in the phone's cache only for playback. Murf credentials may exist in the neighboring environment, but Murf is not called by this version.

## Explore the updated app

Launch opens a dim temple. Baat karein connects a live call, lights the scene, plays a quiet bell, and lets the LLM choose an opening from allowed context. Type opens typed chat. A reconnect does not replay the opening. Use mute and End during a call; calls end when the app goes to the background, after the configured idle timeout, or at the absolute time limit. Voice and text share history; use the drawer to search older conversations, start a chat without memory, open Memory & settings, or sign out. Failed messages show Retry and Remove. Memory saves are automatic for selected lasting facts, with edit/delete controls in settings. Relevant shlok cards offer Sanskrit, English/Hindi switches, and source links.

For web preview, run `npm run web` from `mobile` with `EXPO_PUBLIC_API_URL=http://localhost:8000/api`. For device testing, retain the LAN address in `mobile/.env` and start Uvicorn with `--host 0.0.0.0`. Restart Metro after changing the app configuration or dependencies.

## Inspect mobile API calls

Keep the app open in Expo Go and press `j` in the Metro terminal to open React Native DevTools. Select **Network** (or **Expo Network**), then perform the action on the phone. Filter for `voice/speak`, `turns`, or another route; select a request to inspect its URL, method, status, JSON payload, headers, and response. Open DevTools before reproducing the action because earlier requests may not be recorded. See [Expo's network inspection guide](https://docs.expo.dev/debugging/tools/#inspecting-network-requests-expo-only).

The API client explicitly uses `expo/fetch`; use Expo Network for these requests. The Console also shows development-only `[api]` logs with method, route, status, duration, and validation field errors. These logs omit tokens and message bodies. The Network inspector itself displays request contents; avoid publishing an unredacted capture.

The phone inspector shows phone-to-FastAPI traffic. Gemini/ElevenLabs calls happen on the backend, so inspect Uvicorn logs for those. `/docs` lets you call backend endpoints directly; it is not a monitor of phone traffic. For Listen, expect `POST /api/voice/speak`, JSON `{"text":"..."}`, HTTP 200, and `audio/mpeg` in the response.

## Product and architecture notes

- [Live voice setup, architecture and testing](docs/live-voice.md)
- [Product brief](PRODUCT.md)
- [Design system](DESIGN.md)
- [Lean architecture and implemented boundaries](docs/architecture-lean-candidate.md)
- [Product discovery](docs/product-discovery.md)
- [Marketing and product angles](docs/marketing-and-product-angles.md)
- [API end-to-end testing runbook](docs/api-e2e-testing.md)
- [Product polish and verification](docs/product-polish-testing.md)
- [Agent handoff and remaining device checks](docs/agent-handoff.md)

Saarthi uses a small source-checked scripture collection in `backend/app/scripture.py`. The app inserts original Sanskrit and an English/Hindi rendering into relevant replies; wider scripture coverage is not yet implemented. It does not claim clinical efficacy. A production launch still needs a reviewed safety policy, provider/privacy terms, rate limits, deployment secrets, and a real SMTP sender.
