"""Shared fixtures for backend integration tests."""

from __future__ import annotations

import os
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from typing import Any

import boto3
import httpx
import pytest
import pytest_asyncio
from botocore.exceptions import BotoCoreError, ClientError
from fastapi import FastAPI
from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import NullPool

from tests.integration.constants import (
    AGENT_KEYS,
    DEFAULT_REPO,
    OTHER_REPO,
    PM_EMAIL,
    PM_PASSWORD,
    RELATED_REPO,
)

os.environ.update(
    {
        "DATABASE_URL": "postgresql+asyncpg://crewline:crewline@localhost:5432/crewline_test",
        "ENVIRONMENT": "test",
        "LOG_LEVEL": "DEBUG",
        "CORS_ALLOWED_ORIGINS": "http://localhost:5173",
        "COOKIE_SECURE": "false",
        "COOKIE_SAMESITE": "lax",
        "SESSION_LIFETIME_HOURS": "24",
        "COOKIE_NAME": "crewline_session",
        "PM_INITIAL_PASSWORD": "test_pm_password",
        "AGENT_BE_INITIAL_KEY": "test_be_key",
        "AGENT_FE_INITIAL_KEY": "test_fe_key",
        "AGENT_ARCHITECT_INITIAL_KEY": "test_architect_key",
        "AGENT_QA_INITIAL_KEY": "test_qa_key",
        "STORAGE_ENDPOINT_URL": "http://localhost:9000",
        "STORAGE_ACCESS_KEY": "minioadmin",
        "STORAGE_SECRET_KEY": "minioadmin",
        "STORAGE_BUCKET": "crewline-test-attachments",
        "STORAGE_REGION": "us-east-1",
        "STORAGE_ADDRESSING_STYLE": "path",
        "ATTACHMENT_MAX_SIZE_BYTES": "26214400",
        "ATTACHMENT_UPLOAD_URL_TTL_SECONDS": "900",
        "ATTACHMENT_DOWNLOAD_URL_TTL_SECONDS": "900",
        "ATTACHMENT_PENDING_CLEANUP_AGE_HOURS": "24",
        "GITHUB_APP_ID": "12345",
        "GITHUB_APP_CLIENT_ID": "github-client-id",
        "GITHUB_APP_CLIENT_SECRET": "github-client-secret",
        "GITHUB_APP_PRIVATE_KEY": "test-private-key",
        "GITHUB_APP_NAME": "Crewline",
        "GITHUB_FRONTEND_REDIRECT_URL": "http://localhost:5173/settings?github=connected",
    }
)

import app.db as app_db  # noqa: E402

TEST_DATABASE_URL = os.environ["DATABASE_URL"]
test_engine = create_async_engine(
    TEST_DATABASE_URL,
    echo=False,
    pool_pre_ping=True,
    poolclass=NullPool,
)
TestSessionFactory = async_sessionmaker(
    test_engine,
    expire_on_commit=False,
    class_=AsyncSession,
)


@asynccontextmanager
async def test_session_scope() -> AsyncIterator[AsyncSession]:
    session = TestSessionFactory()
    try:
        yield session
        await session.commit()
    except Exception:
        await session.rollback()
        raise
    finally:
        await session.close()


async def test_get_session() -> AsyncIterator[AsyncSession]:
    async with test_session_scope() as session:
        yield session


app_db.engine = test_engine
app_db.SessionFactory = TestSessionFactory
app_db.session_scope = test_session_scope
app_db.get_session = test_get_session

from app.main import app as fastapi_app  # noqa: E402

RUNTIME_TABLES = (
    "runtime_logs",
    "mailbox_messages",
    "ticket_attachments",
    "ticket_artifacts",
    "ticket_audit_log",
    "tickets",
    "sessions",
    "github_installation_repos",
    "github_installations",
    "github_install_states",
)


@pytest.fixture(scope="session")
def app() -> FastAPI:
    return fastapi_app


@pytest.fixture(scope="session")
def db_engine() -> AsyncEngine:
    return test_engine


@pytest_asyncio.fixture(autouse=True)
async def db_clean(db_engine: AsyncEngine) -> AsyncIterator[None]:
    await _reset_database(db_engine)
    await _seed_github_installation(db_engine)
    yield
    await _reset_database(db_engine)


async def _reset_database(db_engine: AsyncEngine) -> None:
    async with db_engine.begin() as conn:
        await conn.execute(text(f"TRUNCATE TABLE {', '.join(RUNTIME_TABLES)} RESTART IDENTITY CASCADE"))
        await conn.execute(text("UPDATE agent_credentials SET revoked_at = NULL, last_used_at = NULL"))
        await conn.execute(text("UPDATE user_credentials SET last_used_at = NULL"))


async def _seed_github_installation(db_engine: AsyncEngine) -> None:
    async with db_engine.begin() as conn:
        await conn.execute(
            text(
                """
                INSERT INTO github_installations
                  (pm_user_id, installation_id, account_login, account_type, status)
                VALUES
                  ('00000000-0000-0000-0000-000000000001', 98765, 'acme', 'Organization', 'active')
                """
            )
        )
        for repo_id, full_name in (
            (111, DEFAULT_REPO),
            (222, RELATED_REPO),
            (333, OTHER_REPO),
        ):
            await conn.execute(
                text(
                    """
                    INSERT INTO github_installation_repos
                      (installation_id, github_repo_id, repo_full_name, default_branch)
                    VALUES
                      (98765, :repo_id, :full_name, 'main')
                    """
                ),
                {"repo_id": repo_id, "full_name": full_name},
            )


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest_asyncio.fixture
async def anonymous_client(app: FastAPI) -> AsyncIterator[httpx.AsyncClient]:
    async with _client(app) as client:
        yield client


@pytest_asyncio.fixture
async def pm_client(app: FastAPI) -> AsyncIterator[httpx.AsyncClient]:
    async with _client(app) as client:
        response = await client.post(
            "/auth/login",
            json={"email": PM_EMAIL, "password": PM_PASSWORD},
        )
        assert response.status_code == 204, response.text
        me = await client.get("/auth/me")
        assert me.status_code == 200, me.text
        client.headers["X-CSRF-Token"] = me.json()["csrf_token"]
        yield client


@pytest_asyncio.fixture
async def pm_client_no_csrf(app: FastAPI) -> AsyncIterator[httpx.AsyncClient]:
    async with _client(app) as client:
        response = await client.post(
            "/auth/login",
            json={"email": PM_EMAIL, "password": PM_PASSWORD},
        )
        assert response.status_code == 204, response.text
        yield client


@pytest_asyncio.fixture
async def agent_be_client(app: FastAPI) -> AsyncIterator[httpx.AsyncClient]:
    async with _agent_client(app, "cortex") as client:
        yield client


@pytest_asyncio.fixture
async def agent_fe_client(app: FastAPI) -> AsyncIterator[httpx.AsyncClient]:
    async with _agent_client(app, "lumen") as client:
        yield client


@pytest_asyncio.fixture
async def agent_architect_client(app: FastAPI) -> AsyncIterator[httpx.AsyncClient]:
    async with _agent_client(app, "architect") as client:
        yield client


@pytest_asyncio.fixture
async def agent_qa_client(app: FastAPI) -> AsyncIterator[httpx.AsyncClient]:
    async with _agent_client(app, "sentinel") as client:
        yield client


def _client(app: FastAPI, headers: dict[str, str] | None = None) -> httpx.AsyncClient:
    transport = httpx.ASGITransport(app=app)
    return httpx.AsyncClient(
        transport=transport,
        base_url="http://test",
        headers=headers,
    )


def _agent_client(app: FastAPI, agent_id: str) -> httpx.AsyncClient:
    return _client(app, headers={"Authorization": f"Bearer {AGENT_KEYS[agent_id]}"})


@pytest_asyncio.fixture
async def db_fetch_one(db_engine: AsyncEngine) -> Callable[[str, dict[str, Any] | None], Any]:
    async def _fetch_one(sql: str, params: dict[str, Any] | None = None) -> Any:
        async with db_engine.begin() as conn:
            result = await conn.execute(text(sql), params or {})
            row = result.mappings().first()
            return dict(row) if row is not None else None

    return _fetch_one


@pytest_asyncio.fixture
async def db_fetch_all(db_engine: AsyncEngine) -> Callable[[str, dict[str, Any] | None], Any]:
    async def _fetch_all(sql: str, params: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        async with db_engine.begin() as conn:
            result = await conn.execute(text(sql), params or {})
            return [dict(row) for row in result.mappings().all()]

    return _fetch_all


@pytest_asyncio.fixture
async def db_execute(db_engine: AsyncEngine) -> Callable[[str, dict[str, Any] | None], Any]:
    async def _execute(sql: str, params: dict[str, Any] | None = None) -> None:
        async with db_engine.begin() as conn:
            await conn.execute(text(sql), params or {})

    return _execute


@pytest.fixture
def storage_client() -> Any:
    return boto3.client(
        "s3",
        endpoint_url=os.environ["STORAGE_ENDPOINT_URL"],
        aws_access_key_id=os.environ["STORAGE_ACCESS_KEY"],
        aws_secret_access_key=os.environ["STORAGE_SECRET_KEY"],
        region_name=os.environ["STORAGE_REGION"],
    )


@pytest.fixture
def storage_bucket() -> str:
    return os.environ["STORAGE_BUCKET"]


@pytest_asyncio.fixture(autouse=True)
async def storage_clean(storage_client: Any, storage_bucket: str) -> AsyncIterator[None]:
    _empty_bucket(storage_client, storage_bucket)
    yield
    _empty_bucket(storage_client, storage_bucket)


def _empty_bucket(storage_client: Any, bucket: str) -> None:
    try:
        response = storage_client.list_objects_v2(Bucket=bucket)
        keys = [{"Key": obj["Key"]} for obj in response.get("Contents", [])]
        if keys:
            storage_client.delete_objects(Bucket=bucket, Delete={"Objects": keys})
    except (BotoCoreError, ClientError):
        # If MinIO is not running, the actual integration run will fail on tests
        # that need storage. Collection and non-storage tests should remain importable.
        return


@pytest_asyncio.fixture
async def create_ticket(pm_client: httpx.AsyncClient) -> Callable[..., Any]:
    async def _create_ticket(
        title: str = "ticket",
        owner_agent_id: str | None = "cortex",
        repo_full_name: str = DEFAULT_REPO,
        related_repo_full_names: list[str] | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {"title": title, "repo_full_name": repo_full_name}
        if owner_agent_id is not None:
            payload["owner_agent_id"] = owner_agent_id
        if related_repo_full_names is not None:
            payload["related_repo_full_names"] = related_repo_full_names
        response = await pm_client.post("/tickets", json=payload)
        assert response.status_code == 201, response.text
        return response.json()

    return _create_ticket


@pytest_asyncio.fixture
async def move_ticket() -> Callable[[httpx.AsyncClient, int, str, str | None, bool], Any]:
    async def _move_ticket(
        client: httpx.AsyncClient,
        ticket_id: int,
        to_status: str,
        reason: str | None = None,
        pm_override: bool = False,
    ) -> httpx.Response:
        payload: dict[str, Any] = {"to_status": to_status}
        if reason is not None:
            payload["reason"] = reason
        if pm_override:
            payload["pm_override"] = True
        return await client.post(f"/tickets/{ticket_id}/transitions", json=payload)

    return _move_ticket
