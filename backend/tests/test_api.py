from datetime import timedelta
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from agents import doval, saarthi
from agents.runner import AgentFailure
from config import Settings
from core.models import Conversation, Knowledge, User, now
from main import create_app
from tests.conftest import sign_in, start


def test_auth_boundaries(client, factory, settings):
    assert client.get("/me").status_code == 401
    assert client.post("/auth/otp/request", json={"phone": "123"}).status_code == 422
    assert client.post("/auth/otp/request", json={"phone": "+1 9876543210"}).status_code == 422
    assert (
        client.post("/auth/otp/verify", json={"phone": "9876543210", "otp": " "}).status_code == 422
    )
    response = client.post("/auth/otp/verify", json={"phone": "+91 (98765) 43210", "otp": "abc"})
    assert response.json()["user"]["phone"] == "+919876543210"
    assert "httponly" in response.headers["set-cookie"].lower()
    assert "samesite=lax" in response.headers["set-cookie"].lower()
    token = client.cookies.get("saarthi_session")
    with factory() as db:
        user = db.scalar(select(User))
        assert user.session_token_hash != token and len(user.session_token_hash) == 64
        assert token not in response.text and user.session_token_hash not in response.text
    assert client.get("/conversations").status_code == 403
    assert client.get("/knowledge").status_code == 403
    assert client.patch("/me", json={"name": " ", "gender": "male", "age": 20}).status_code == 422
    assert (
        client.patch(
            "/me", json={"name": "Aman", "gender": "self-described", "age": True}
        ).status_code
        == 422
    )
    assert (
        client.patch("/me", json={"name": "Aman", "gender": "self-described", "age": 1}).status_code
        == 200
    )
    with TestClient(
        create_app(settings, factory), headers={"Origin": settings.app_origin}
    ) as other:
        sign_in(other)
        assert client.get("/me").status_code == 401
        assert other.post("/auth/logout").status_code == 204
        assert other.get("/me").status_code == 401
    sign_in(client)
    with factory.begin() as db:
        db.scalar(select(User)).session_expires_at = now() - timedelta(seconds=1)
    assert client.get("/me").status_code == 401


def test_config_rejects_deployment_and_insecure_remote_origin():
    for values in [
        {"environment": "production"},
        {"app_origin": "http://example.com"},
        {"database_url": "sqlite://"},
        {"app_origin": "https://host/path"},
    ]:
        with pytest.raises(ValueError):
            Settings(_env_file=None, **values)


def test_origin_and_error_envelopes(client):
    for origin in ["", "https://evil.example"]:
        response = client.post(
            "/auth/otp/request", json={"phone": "9876543210"}, headers={"Origin": origin}
        )
        assert response.status_code == 403
    assert (
        client.post(
            "/auth/otp/request",
            json={"phone": "9876543210"},
            headers={"Sec-Fetch-Site": "cross-site"},
        ).status_code
        == 403
    )
    response = client.post("/auth/otp/verify", json={"phone": "secret", "otp": ""})
    assert response.status_code == 422 and response.json()["error"]["code"] == "invalid_input"
    assert "secret" not in response.text
    assert client.get("/health").json() == {"status": "ok"}
    assert client.get("/").status_code == 200
    assert "script-src 'self'" in client.get("/").headers["content-security-policy"]


def test_chat_lifecycle_retry_and_context(client, agents):
    sign_in(client)
    client.post("/knowledge", json={"type": "factual", "content": "Works as an engineer."})
    client.post(
        "/knowledge", json={"type": "contextual", "content": "Old context", "status": "inactive"}
    )
    identifier = start(client)
    opening = client.post("/conversations", json={"id": identifier})
    assert opening.status_code == 201
    assert len(agents["chat"]) == 1
    assert agents["chat"][0]["opening"] is True
    assert agents["chat"][0]["transcript"] == []
    assert [r["content"] for r in agents["chat"][0]["knowledge"]] == ["Works as an engineer."]
    assert client.post("/conversations", json={"id": str(uuid4())}).status_code == 409
    body = {"id": str(uuid4()), "content": "I feel stuck at work."}
    response = client.post(f"/conversations/{identifier}/messages", json=body)
    assert response.status_code == 201
    assert client.post(f"/conversations/{identifier}/messages", json=body).json() == response.json()
    assert len(agents["chat"]) == 2
    assert [m["content"] for m in agents["chat"][-1]["transcript"]].count(body["content"]) == 1
    assert (
        client.post(
            f"/conversations/{identifier}/messages", json={**body, "content": "different"}
        ).status_code
        == 409
    )
    assert client.get("/conversations").json()["active_conversation_id"] == identifier
    assert len(client.get(f"/conversations/{identifier}").json()["messages"]) == 3
    assert (
        client.post(f"/conversations/{identifier}/end").json()["conversation"]["knowledge_status"]
        == "completed"
    )
    assert client.post(f"/conversations/{identifier}/end").status_code == 200
    assert len(agents["extraction"]) == 1
    assert (
        client.post(
            f"/conversations/{identifier}/messages", json={"id": str(uuid4()), "content": "hello"}
        ).status_code
        == 409
    )
    assert len(client.get("/knowledge").json()["items"]) == 4
    start(client)
    assert agents["chat"][-1]["latest_summary"] == "- Discussed work."


def test_foreign_ownership(client, factory, settings):
    sign_in(client)
    conv = start(client)
    record = client.post(
        "/knowledge", json={"type": "factual", "content": "Private detail"}
    ).json()["id"]
    message = client.post(
        f"/conversations/{conv}/messages", json={"id": str(uuid4()), "content": "Private message"}
    ).json()["user_message"]["id"]
    with TestClient(
        create_app(settings, factory), headers={"Origin": settings.app_origin}
    ) as other:
        sign_in(other, "8765432109")
        for path in [
            f"/conversations/{conv}",
            f"/conversations/{conv}/end",
            f"/conversations/{conv}/messages",
        ]:
            response = (
                other.get(path)
                if path.endswith(conv)
                else other.post(
                    path,
                    json={"id": str(uuid4()), "content": "x"}
                    if path.endswith("messages")
                    else None,
                )
            )
            assert response.status_code == 404
        assert other.post("/conversations", json={"id": conv}).status_code == 404
        assert other.patch(f"/knowledge/{record}", json={"content": "hacked"}).status_code == 404
        assert other.delete(f"/knowledge/{record}").status_code == 404
        assert other.get("/knowledge").json()["items"] == []
        other_conv = start(other)
        assert (
            other.post(
                f"/conversations/{other_conv}/messages",
                json={"id": message, "content": "Private message"},
            ).status_code
            == 409
        )


def test_generation_failure_and_recovery(client, monkeypatch, agents, factory):
    sign_in(client)
    original = saarthi.reply

    async def fail(*args):
        raise AgentFailure(timeout=True)

    monkeypatch.setattr(saarthi, "reply", fail)
    identifier = str(uuid4())
    assert client.post("/conversations", json={"id": identifier}).status_code == 504
    assert (
        client.get(f"/conversations/{identifier}").json()["conversation"]["generation_status"]
        == "failed"
    )
    monkeypatch.setattr(saarthi, "reply", original)
    assert client.post("/conversations", json={"id": identifier}).status_code == 201
    monkeypatch.setattr(saarthi, "reply", fail)
    body = {"id": str(uuid4()), "content": "Can you help?"}
    assert client.post(f"/conversations/{identifier}/messages", json=body).status_code == 504
    assert len(client.get(f"/conversations/{identifier}").json()["messages"]) == 2
    assert (
        client.post(
            f"/conversations/{identifier}/messages", json={"id": str(uuid4()), "content": "new"}
        ).status_code
        == 409
    )
    # Simulate a worker dying after claiming the persisted user message.
    with factory.begin() as db:
        row = db.get(Conversation, UUID(identifier))
        row.generation_status = "processing"
        row.claim_token = uuid4()
        row.claim_expires_at = now() - timedelta(seconds=1)
    monkeypatch.setattr(saarthi, "reply", original)
    assert client.post(f"/conversations/{identifier}/messages", json=body).status_code == 201
    assert len(client.get(f"/conversations/{identifier}").json()["messages"]) == 3


def test_failed_extraction_preserves_end_and_allows_new_chat(client, monkeypatch, agents):
    sign_in(client)
    conv = start(client)
    original = doval.extract

    async def fail(*args):
        raise ValueError("invalid schema")

    monkeypatch.setattr(doval, "extract", fail)
    result = client.post(f"/conversations/{conv}/end")
    assert result.status_code == 502
    assert result.json()["error"]["knowledge_status"] == "failed"
    assert client.get(f"/conversations/{conv}").json()["conversation"]["status"] == "ended"
    assert client.get("/knowledge").json()["items"] == []
    second = start(client)
    monkeypatch.setattr(doval, "extract", original)
    assert client.post(f"/conversations/{second}/end").status_code == 200
    assert client.post(f"/conversations/{conv}/end").status_code == 200
    start(client)
    # A late retry cannot make the older summary current.
    with client.app.state.db() as db:
        rows = list(db.scalars(select(Knowledge).where(Knowledge.type == "summary")))
        assert len(rows) == 2
        older = next(r for r in rows if str(r.source_conversation_id) == conv)
    client.patch(f"/knowledge/{older.id}", json={"content": "Edited older summary"})
    third = client.get("/conversations").json()["active_conversation_id"]
    client.post(
        f"/conversations/{third}/messages", json={"id": str(uuid4()), "content": "continue"}
    )
    assert agents["chat"][-1]["latest_summary"] == "- Discussed work."


def test_invalid_extraction_atomic_and_retry(client, monkeypatch):
    sign_in(client)
    record = client.post("/knowledge", json={"type": "factual", "content": "Original"}).json()
    conv = start(client)
    original = doval.extract

    async def invalid(*args):
        return doval.ChangeSet(
            additions=[{"type": "factual", "content": "Must roll back"}],
            updates=[{"id": uuid4(), "type": "factual", "content": "Bad ID", "status": "active"}],
            deactivate_ids=[],
            summary=["Invalid"],
        )

    monkeypatch.setattr(doval, "extract", invalid)
    assert client.post(f"/conversations/{conv}/end").status_code == 502
    assert [r["content"] for r in client.get("/knowledge").json()["items"]] == ["Original"]

    async def conflicting(*args):
        return doval.ChangeSet(
            additions=[],
            updates=[
                {"id": record["id"], "type": "factual", "content": "Changed", "status": "active"}
            ],
            deactivate_ids=[record["id"]],
            summary=["Conflict"],
        )

    monkeypatch.setattr(doval, "extract", conflicting)
    assert client.post(f"/conversations/{conv}/end").status_code == 502
    monkeypatch.setattr(doval, "extract", original)
    assert client.post(f"/conversations/{conv}/end").status_code == 200
    assert client.post(f"/conversations/{conv}/end").status_code == 200
    assert len(client.get("/knowledge").json()["items"]) == 3


def test_knowledge_crud_validation_and_context_limits(client):
    sign_in(client)
    assert client.post("/knowledge", json={"type": "invalid", "content": "x"}).status_code == 422
    record = client.post(
        "/knowledge", json={"type": "behavioural", "content": "May avoid conflict."}
    ).json()
    assert client.patch(f"/knowledge/{record['id']}", json={}).status_code == 422
    assert client.patch(f"/knowledge/{record['id']}", json={"content": None}).status_code == 422
    assert (
        client.patch(f"/knowledge/{record['id']}", json={"status": "inactive"}).status_code == 200
    )
    for n in range(5):
        assert (
            client.post(
                "/knowledge", json={"type": "factual", "content": str(n) * 2000}
            ).status_code
            == 201
        )
    response = client.post("/knowledge", json={"type": "factual", "content": "x" * 2000})
    assert response.status_code == 409
    assert client.delete(f"/knowledge/{record['id']}").status_code == 204
    assert (
        client.patch(f"/knowledge/{record['id']}", json={"content": "resurrect"}).status_code == 404
    )


def test_cursor_validation_and_pages(client):
    sign_in(client)
    for _ in range(3):
        conv = start(client)
        client.post(f"/conversations/{conv}/end")
    first = client.get("/conversations?limit=2").json()
    second = client.get(
        "/conversations", params={"limit": 2, "before": first["next_cursor"]}
    ).json()
    assert len(first["items"]) == 2 and len(second["items"]) == 1
    assert set(r["id"] for r in first["items"]).isdisjoint(r["id"] for r in second["items"])
    assert client.get("/conversations?before=garbage").status_code == 422
    assert client.get("/conversations?limit=101").status_code == 422


def test_transcript_capacity_does_not_append_rejected_message(client, factory):
    from core.models import Message

    sign_in(client)
    conv = start(client)
    with factory.begin() as db:
        for _ in range(2):
            user_message = Message(conversation_id=UUID(conv), role="user", content="x" * 8000)
            db.add(user_message)
            db.flush()
            db.add(
                Message(
                    conversation_id=UUID(conv),
                    role="assistant",
                    content="x" * 8000,
                    reply_to_id=user_message.id,
                )
            )
            db.flush()
    before = client.get(f"/conversations/{conv}").json()["messages"]
    response = client.post(
        f"/conversations/{conv}/messages", json={"id": str(uuid4()), "content": "One more"}
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "transcript_limit"
    assert client.get(f"/conversations/{conv}").json()["messages"] == before
    assert client.post(f"/conversations/{conv}/end").status_code == 200


def test_multilingual_knowledge_limit_and_paging(client):
    sign_in(client)
    for _ in range(2):
        assert (
            client.post("/knowledge", json={"type": "factual", "content": "अ" * 1500}).status_code
            == 201
        )
    too_large = client.post("/knowledge", json={"type": "factual", "content": "अ" * 1500})
    assert too_large.status_code == 409
    first = client.get("/knowledge?limit=1").json()
    second = client.get("/knowledge", params={"limit": 1, "after": first["next_cursor"]}).json()
    assert first["items"][0]["id"] != second["items"][0]["id"]
    assert second["next_cursor"] is None
