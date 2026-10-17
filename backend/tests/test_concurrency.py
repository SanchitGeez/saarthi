import asyncio
from datetime import timedelta
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select

from agents import doval, saarthi
from core import schemas, service
from core.errors import Problem
from core.models import Conversation, Knowledge, User, now
from tests.conftest import sign_in, start


def test_overlapping_sends_end_and_expired_claim(factory, settings, client, monkeypatch):
    sign_in(client)
    conv_id = UUID(start(client))
    user_id = UUID(client.get("/me").json()["id"])

    async def scenario():
        entered, release = asyncio.Event(), asyncio.Event()

        async def slow_reply(*args):
            entered.set()
            await release.wait()
            return "Saved once"

        monkeypatch.setattr(saarthi, "reply", slow_reply)
        message = schemas.Send(id=uuid4(), content="Hello")
        task = asyncio.create_task(service.generate(factory, settings, user_id, conv_id, message))
        await entered.wait()
        for operation in [
            service.generate(factory, settings, user_id, conv_id, message),
            service.generate(
                factory, settings, user_id, conv_id, schemas.Send(id=uuid4(), content="Second")
            ),
            service.end_conversation(factory, settings, user_id, conv_id),
        ]:
            with pytest.raises(Problem) as error:
                await operation
            assert error.value.status == 409
        release.set()
        await task
        assert len(service.get_conversation(factory, user_id, conv_id)["messages"]) == 3

    asyncio.run(scenario())


def test_manual_edit_delete_win_during_extraction_and_retry(factory, settings, client, monkeypatch):
    sign_in(client)
    edited = client.post("/knowledge", json={"type": "factual", "content": "Old job"}).json()
    deleted = client.post(
        "/knowledge", json={"type": "contextual", "content": "Moving home"}
    ).json()
    conv_id = UUID(start(client))
    user_id = UUID(client.get("/me").json()["id"])

    async def scenario():
        entered, release = asyncio.Event(), asyncio.Event()
        calls = 0

        async def extraction(*args):
            nonlocal calls
            calls += 1
            entered.set()
            await release.wait()
            return doval.ChangeSet(
                additions=[{"type": "contextual", "content": "Planning to move house"}],
                updates=[
                    {
                        "id": edited["id"],
                        "type": "factual",
                        "content": "Agent job",
                        "status": "active",
                    }
                ],
                deactivate_ids=[deleted["id"]],
                summary=["Work and moving"],
            )

        monkeypatch.setattr(doval, "extract", extraction)
        task = asyncio.create_task(service.end_conversation(factory, settings, user_id, conv_id))
        await entered.wait()
        service.edit_knowledge(factory, user_id, {"content": "Manual new job"}, UUID(edited["id"]))
        service.edit_knowledge(factory, user_id, {}, UUID(deleted["id"]), delete=True)
        with pytest.raises(Problem):
            await service.end_conversation(factory, settings, user_id, conv_id)
        release.set()
        await task
        await service.end_conversation(factory, settings, user_id, conv_id)
        assert calls == 1
        rows = service.list_knowledge(factory, user_id)["items"]
        assert [r["content"] for r in rows if r["type"] != "summary"] == ["Manual new job"]
        with factory() as db:
            assert db.get(Knowledge, UUID(deleted["id"])).deleted_at is not None

    asyncio.run(scenario())


def test_deleted_detail_blocked_on_same_chat_retry_but_later_chat_can_learn(client, monkeypatch):
    sign_in(client)
    record = client.post("/knowledge", json={"type": "contextual", "content": "Moving"}).json()
    conv = start(client)
    original = doval.extract

    async def fail(*args):
        raise ValueError()

    monkeypatch.setattr(doval, "extract", fail)
    assert client.post(f"/conversations/{conv}/end").status_code == 502
    client.delete(f"/knowledge/{record['id']}")

    async def extraction(*args):
        return doval.ChangeSet(
            additions=[{"type": "contextual", "content": "Moving to a new home"}],
            updates=[],
            deactivate_ids=[],
            summary=["Moving"],
        )

    monkeypatch.setattr(doval, "extract", extraction)
    assert client.post(f"/conversations/{conv}/end").status_code == 200
    assert all(r["type"] == "summary" for r in client.get("/knowledge").json()["items"])
    second = start(client)
    client.post(
        f"/conversations/{second}/messages",
        json={"id": str(uuid4()), "content": "I am moving to a new home."},
    )
    assert client.post(f"/conversations/{second}/end").status_code == 200
    assert any(
        r["content"] == "Moving to a new home" for r in client.get("/knowledge").json()["items"]
    )
    monkeypatch.setattr(doval, "extract", original)


def test_extraction_lease_recovers_and_old_worker_cannot_commit(
    factory, settings, client, monkeypatch
):
    sign_in(client)
    conv_id = UUID(start(client))
    user_id = UUID(client.get("/me").json()["id"])

    async def scenario():
        entered, release = asyncio.Event(), asyncio.Event()
        calls = 0

        async def extraction(*args):
            nonlocal calls
            calls += 1
            number = calls
            if number == 1:
                entered.set()
                await release.wait()
            return doval.ChangeSet(
                additions=[], updates=[], deactivate_ids=[], summary=[f"Attempt {number}"]
            )

        monkeypatch.setattr(doval, "extract", extraction)
        first = asyncio.create_task(service.end_conversation(factory, settings, user_id, conv_id))
        await entered.wait()
        with factory.begin() as db:
            db.get(Conversation, conv_id).claim_expires_at = now() - timedelta(seconds=1)
        await service.end_conversation(factory, settings, user_id, conv_id)
        release.set()
        with pytest.raises(Problem) as error:
            await first
        assert error.value.code == "operation_superseded"
        summaries = [
            r for r in service.list_knowledge(factory, user_id)["items"] if r["type"] == "summary"
        ]
        assert [r["content"] for r in summaries] == ["- Attempt 2"]

    asyncio.run(scenario())


def test_provider_has_no_database_transaction_open(factory, settings, client, monkeypatch):
    sign_in(client)
    conv_id = UUID(start(client))
    user_id = UUID(client.get("/me").json()["id"])

    async def check(*args):
        # A second connection can immediately acquire the user lock during model generation.
        with factory.begin() as db:
            db.scalar(select(User).where(User.id == user_id).with_for_update(nowait=True))
        return "No transaction held"

    monkeypatch.setattr(saarthi, "reply", check)
    asyncio.run(
        service.generate(
            factory, settings, user_id, conv_id, schemas.Send(id=uuid4(), content="Check lock")
        )
    )
