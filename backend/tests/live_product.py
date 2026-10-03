"""Real-service integration checks. No model, DB, or API mocks.

Run with two isolated APIs: normal port 8001; port 8002 configured with
GEMINI_MODEL=gemini-saarthi-test-unavailable and GEMINI_FALLBACK_MODEL=.
The gemini- prefix routes to the real provider, which rejects the nonexistent
model. --keep leaves the disposable account for browser QA.
"""
import argparse
import asyncio
import json
from pathlib import Path
from uuid import uuid4

import httpx


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", default="http://127.0.0.1:8001/api")
    parser.add_argument("--failure-base", default="http://127.0.0.1:8002/api")
    parser.add_argument("--keep", action="store_true")
    args = parser.parse_args()
    results = []
    accounts = []
    completed = False
    async with httpx.AsyncClient(timeout=115) as client:
        async def call(method, path, expected=200, headers=None, base=None, **kwargs):
            response = await client.request(method, (base or args.base) + path, headers=headers, **kwargs)
            assert response.status_code == expected, (path, response.status_code, response.text[:250])
            return response.json() if response.content else None
        def check(name, condition):
            assert condition, name
            results.append(name)
            print("PASS", name, flush=True)
        async def signup():
            email = f"saarthi-polish-{uuid4().hex[:12]}@example.com"
            code = (await call("POST", "/auth/request-code", json={"email": email}))["dev_code"]
            response = await call("POST", "/auth/verify-code", json={"email": email, "code": code})
            headers = {"Authorization": f"Bearer {response['access_token']}"}
            accounts.append(headers)
            return email, headers
        try:
            await call("GET", "/health")
            await call("GET", "/conversations", expected=401)
            email, headers = await signup()
            private_state = Path("/tmp/saarthi-test-cleanup.json")
            private_state.write_text(json.dumps({"headers": headers, "base": args.base}))
            private_state.chmod(0o600)
            check("development sign-in and unauthorized access", True)
            conv = await call("POST", "/conversations", headers=headers, json={"private": False})
            path = f"/conversations/{conv['id']}"
            await call("POST", path + "/turns", expected=422, headers=headers, json={"text": "   "})
            turn_id = str(uuid4())
            prompt = ("I work as a software engineer in Pune. That's a lasting detail about me; remember my work and city. "
                      "I've spent months working toward promotion, and now I am terrified of the result. "
                      "Please help me reflect using the original Gita 2.47 and explain how it applies.")
            reply = await call("POST", path + "/turns", headers=headers, json={"text": prompt, "client_id": turn_id})
            check("real Gemini reply with verified Sanskrit and Hindi/English rendering",
                  reply["role"] == "assistant" and reply["verses"] and reply["verses"][0]["reference"] == "2.47"
                  and "[[gita:2.47]]" in reply["text"])
            original = reply["id"]
            repeated = await call("POST", path + "/turns", headers=headers, json={"text": prompt, "client_id": turn_id})
            history = await call("GET", path + "/messages", headers=headers)
            check("idempotency: one question and one reply after duplicate delivery", repeated["id"] == original and len(history) == 2 and history[0]["status"] == "completed")
            await call("POST", path + "/turns", expected=409, headers=headers, json={"text": "changed", "client_id": turn_id})
            check("same id cannot overwrite another message", True)
            memories = await call("GET", "/memories", headers=headers)
            check("lasting detail auto-saved without individual approval", len(memories) == 1 and memories[0]["status"] == "confirmed")
            fail_id = str(uuid4())
            failed_text = "I feel tired today. Could we think about what to do next?"
            await call("POST", path + "/turns", expected=502, base=args.failure_base, headers=headers, json={"text": failed_text, "client_id": fail_id})
            history = await call("GET", path + "/messages", headers=headers)
            check("real upstream failure persisted as a retryable message", len(history) == 3 and history[-1]["status"] == "failed" and history[-1]["turn_id"] == fail_id)
            after_failure = await call("GET", "/memories", headers=headers)
            check("failed reply did not save any memories", len(after_failure) == len(memories))
            retried = await call("POST", path + "/turns", headers=headers, json={"text": failed_text, "client_id": fail_id})
            history = await call("GET", path + "/messages", headers=headers)
            check("retry recovers the same saved message without a duplicate", len(history) == 4 and history[2]["id"] == fail_id and history[2]["status"] == "completed")
            check("temporary emotion not stored as a personality fact", len(await call("GET", "/memories", headers=headers)) == 1)
            fresh = await call("POST", "/conversations", headers=headers, json={"private": False})
            recall = await call("POST", f"/conversations/{fresh['id']}/turns", headers=headers, json={"text": "What do you remember about my job and where I work?", "client_id": str(uuid4())})
            check("real cross-conversation memory recall", "pune" in recall["text"].lower() and ("engineer" in recall["text"].lower() or "software" in recall["text"].lower()))
            private = await call("POST", "/conversations", headers=headers, json={"private": True})
            await call("POST", f"/conversations/{private['id']}/turns", headers=headers, json={"text": "Remember that my long-term goal is to move to Jaipur. What work and city do you know about me?", "client_id": str(uuid4())})
            check("private chat did not write memories", len(await call("GET", "/memories", headers=headers)) == 1)
            await call("PATCH", "/me/preferences", headers=headers, json={"language": "hi", "memory_enabled": False})
            profile = await call("GET", "/auth/me", headers=headers)
            check("language and memory preferences persist", profile["language"] == "hi" and not profile["memory_enabled"])
            await call("PATCH", "/me/preferences", headers=headers, json={"language": "en", "memory_enabled": True})
            _, stranger = await signup()
            await call("GET", path + "/messages", expected=404, headers=stranger)
            await call("POST", path + "/turns", expected=404, headers=stranger, json={"text": "hello", "client_id": str(uuid4())})
            await call("PATCH", f"/memories/{memories[0]['id']}", expected=404, headers=stranger, json={"content": "unauthorized"})
            check("conversation, message, and memory ownership enforced", True)
            edited = await call("PATCH", f"/memories/{memories[0]['id']}", headers=headers, json={"content": "I work as a software engineer in Pune and prefer plain language."})
            check("memory editable with no approval step", edited["status"] == "confirmed")
            await call("PATCH", f"/memories/{memories[0]['id']}", expected=422, headers=headers, json={"content": "   "})
            check("blank memory rejected", True)
            # Leave one real failed turn to exercise retry controls in the browser.
            pending_id = str(uuid4())
            await call("POST", path + "/turns", expected=502, base=args.failure_base, headers=headers, json={"text": "My plans changed today. Help me find a calm next step.", "client_id": pending_id})
            report = {"email": email, "conversation_id": conv["id"], "checks": results}
            Path("/tmp/saarthi-product-results.json").write_text(json.dumps(report, indent=2))
            # Keep tokens out of output. This file is only for subsequent authorised local cleanup.
            private_state = Path("/tmp/saarthi-test-cleanup.json")
            private_state.write_text(json.dumps({"headers": headers, "base": args.base}))
            private_state.chmod(0o600)
            completed = True
            print(f"RESULT: {len(results)} checks passed", flush=True)
        finally:
            for index, auth in enumerate(accounts):
                if args.keep and completed and index == 0:
                    continue
                await client.delete(args.base + "/auth/me", headers=auth)


if __name__ == "__main__":
    asyncio.run(main())
