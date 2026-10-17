import os
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker

from agents import doval, saarthi
from config import Settings
from main import create_app


@pytest.fixture(scope="session")
def database():
    url = os.environ.get("TEST_DATABASE_URL")
    if not url:
        pytest.skip(
            "Set TEST_DATABASE_URL to a PostgreSQL database (tests use an isolated temporary schema)."
        )
    engine = create_engine(url)
    schema = "test_" + uuid4().hex
    with engine.begin() as db:
        db.execute(text(f"CREATE SCHEMA {schema}"))
    test_url = (
        make_url(url)
        .update_query_dict({"options": f"-csearch_path={schema}"})
        .render_as_string(hide_password=False)
    )
    previous = os.environ.get("DATABASE_URL")
    os.environ["DATABASE_URL"] = test_url
    try:
        command.upgrade(Config("alembic.ini"), "head")
        test_engine = create_engine(test_url)
        yield test_url, test_engine
        test_engine.dispose()
    finally:
        if previous is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = previous
        with engine.begin() as db:
            db.execute(text(f"DROP SCHEMA {schema} CASCADE"))
        engine.dispose()


@pytest.fixture
def factory(database):
    url, engine = database
    with engine.begin() as db:
        db.execute(text("TRUNCATE user_knowledge, messages, conversations, users CASCADE"))
    return sessionmaker(engine, expire_on_commit=False)


@pytest.fixture
def settings(database):
    return Settings(
        _env_file=None, environment="test", database_url=database[0], app_origin="http://testserver"
    )


@pytest.fixture
def agents(monkeypatch):
    calls = {"chat": [], "extraction": []}

    async def reply(settings, payload):
        calls["chat"].append(payload)
        return "Hello. What is on your mind?"

    async def extract(settings, payload):
        calls["extraction"].append(payload)
        return doval.ChangeSet(
            additions=[{"type": "contextual", "content": "Considering a job change."}],
            updates=[],
            deactivate_ids=[],
            summary=["Discussed work."],
        )

    monkeypatch.setattr(saarthi, "reply", reply)
    monkeypatch.setattr(doval, "extract", extract)
    return calls


@pytest.fixture
def client(factory, settings, agents):
    with TestClient(
        create_app(settings, factory), headers={"Origin": settings.app_origin}
    ) as client:
        yield client


def sign_in(client, phone="9876543210", onboard=True):
    response = client.post("/auth/otp/verify", json={"phone": phone, "otp": "anything"})
    assert response.status_code == 200, response.text
    if onboard:
        response = client.patch(
            "/me", json={"name": "Aman", "gender": "Prefer not to say", "age": 16}
        )
        assert response.status_code == 200
    return response.json()


def start(client):
    response = client.post("/conversations", json={"id": str(uuid4())})
    assert response.status_code == 201, response.text
    return response.json()["conversation"]["id"]
