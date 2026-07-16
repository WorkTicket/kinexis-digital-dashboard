"""Pagination and datasource response shape tests."""

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.main import app
from app.models import Client, Insight, Task


def _client_with_memory_db():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSession = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)

    def override_get_db():
        db = TestingSession()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    return TestClient(app), TestingSession


def test_insights_and_tasks_are_paginated():
    client, Session = _client_with_memory_db()
    db = Session()
    c = Client(name="Acme", industry="SEO")
    db.add(c)
    db.commit()
    db.refresh(c)
    cid = c.id
    for i in range(5):
        db.add(
            Insight(
                client_id=cid,
                type="test",
                message=f"m{i}",
                severity="low",
                kind="opportunity",
            )
        )
        db.add(Task(client_id=cid, status="open", assigned_to="Self"))
    db.commit()
    db.close()

    r = client.get(f"/insights/?client_id={cid}&limit=2")
    assert r.status_code == 200
    assert len(r.json()) == 2

    r2 = client.get(f"/tasks/?client_id={cid}&limit=3")
    assert r2.status_code == 200
    assert len(r2.json()) == 3

    app.dependency_overrides.clear()


def test_datasource_response_omits_ciphertext():
    client, _ = _client_with_memory_db()
    r = client.post("/clients/", json={"name": "Beta", "industry": "CRO"})
    assert r.status_code == 200
    cid = r.json()["id"]

    r2 = client.post(
        f"/clients/{cid}/datasources",
        json={"type": "bing", "credentials": {"api_key": "tok-secret", "site_url": "https://example.com"}},
    )
    assert r2.status_code == 200
    body = r2.json()
    assert "credentials_encrypted" not in body
    assert body.get("has_credentials") is True

    r3 = client.get(f"/clients/{cid}/datasources")
    assert r3.status_code == 200
    assert all("credentials_encrypted" not in row for row in r3.json())

    app.dependency_overrides.clear()


def test_settings_masks_secrets():
    client, _ = _client_with_memory_db()
    r = client.put(
        "/settings/",
        json={"pagespeed_api_key": "ps-key-abcdef1234"},
    )
    assert r.status_code == 200
    data = r.json()
    assert data["pagespeed_api_key_configured"] is True
    assert data["pagespeed_api_key"].startswith("••••")
    assert "ps-key-abcdef1234" not in data["pagespeed_api_key"]

    app.dependency_overrides.clear()
