"""Integration coverage for ticket attachment upload, finalize, list, and delete flows."""

from __future__ import annotations

from typing import Any

import httpx
import pytest

pytestmark = pytest.mark.integration


def _upload_payload(
    filename: str = "notes.txt",
    content_type: str = "text/plain",
    size_bytes: int = 5,
) -> dict[str, object]:
    return {
        "filename": filename,
        "content_type": content_type,
        "size_bytes": size_bytes,
    }


async def _request_upload(
    client: httpx.AsyncClient,
    ticket_id: int,
    *,
    filename: str = "notes.txt",
    content_type: str = "text/plain",
    size_bytes: int = 5,
) -> httpx.Response:
    return await client.post(
        f"/tickets/{ticket_id}/attachments/upload-url",
        json=_upload_payload(filename, content_type, size_bytes),
    )


async def _put_bytes(upload_url: str, data: bytes, content_type: str = "text/plain") -> httpx.Response:
    async with httpx.AsyncClient() as client:
        return await client.put(
            upload_url,
            content=data,
            headers={"Content-Type": content_type},
        )


async def test_request_upload_url_creates_pending_row(
    create_ticket,
    pm_client: httpx.AsyncClient,
    db_fetch_one,
) -> None:
    ticket = await create_ticket(owner_agent_id="cortex")

    response = await _request_upload(pm_client, ticket["id"])
    row = await db_fetch_one(
        "SELECT status, uploaded_by FROM ticket_attachments WHERE id = :attachment_id",
        {"attachment_id": response.json()["attachment_id"] if response.status_code == 201 else -1},
    )

    assert response.status_code == 201, response.text
    assert response.json()["upload_url"]
    assert response.json()["expires_in_seconds"] > 0
    assert row == {
        "status": "pending",
        "uploaded_by": "human:00000000-0000-0000-0000-000000000001",
    }


async def test_request_upload_url_disallowed_content_type_returns_415(
    create_ticket,
    pm_client: httpx.AsyncClient,
) -> None:
    ticket = await create_ticket(owner_agent_id="cortex")

    response = await _request_upload(
        pm_client,
        ticket["id"],
        content_type="application/x-msdownload",
    )

    assert response.status_code == 415
    assert response.json()["error"]["code"] == "attachment_content_type_not_allowed"


async def test_request_upload_url_too_large_returns_413(
    create_ticket,
    pm_client: httpx.AsyncClient,
) -> None:
    ticket = await create_ticket(owner_agent_id="cortex")

    response = await _request_upload(pm_client, ticket["id"], size_bytes=25 * 1024 * 1024 + 1)

    assert response.status_code == 413
    assert response.json()["error"]["code"] == "attachment_too_large"


async def test_request_upload_url_for_nonexistent_ticket_returns_404(
    pm_client: httpx.AsyncClient,
) -> None:
    response = await _request_upload(pm_client, 999999)

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "ticket_not_found"


async def test_agent_requests_upload_url_for_own_ticket(
    create_ticket,
    agent_be_client: httpx.AsyncClient,
) -> None:
    ticket = await create_ticket(owner_agent_id="cortex")

    response = await _request_upload(agent_be_client, ticket["id"])

    assert response.status_code == 201, response.text


async def test_agent_requests_upload_url_for_other_ticket_returns_403(
    create_ticket,
    agent_be_client: httpx.AsyncClient,
) -> None:
    ticket = await create_ticket(owner_agent_id="lumen")

    response = await _request_upload(agent_be_client, ticket["id"])

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "actor_not_permitted"


async def test_put_to_upload_url_succeeds(
    create_ticket,
    pm_client: httpx.AsyncClient,
) -> None:
    ticket = await create_ticket(owner_agent_id="cortex")
    upload = await _request_upload(pm_client, ticket["id"], size_bytes=5)

    response = await _put_bytes(upload.json()["upload_url"], b"hello")

    assert upload.status_code == 201, upload.text
    assert response.status_code == 200, response.text


async def test_finalize_after_successful_upload_marks_ready(
    create_ticket,
    pm_client: httpx.AsyncClient,
) -> None:
    ticket = await create_ticket(owner_agent_id="cortex")
    upload = await _request_upload(pm_client, ticket["id"], size_bytes=5)
    await _put_bytes(upload.json()["upload_url"], b"hello")

    response = await pm_client.post(
        f"/tickets/{ticket['id']}/attachments/{upload.json()['attachment_id']}/finalize",
    )

    assert response.status_code == 200, response.text
    assert response.json()["status"] == "ready"
    assert response.json()["finalized_at"] is not None


async def test_finalize_without_upload_returns_409(
    create_ticket,
    pm_client: httpx.AsyncClient,
) -> None:
    ticket = await create_ticket(owner_agent_id="cortex")
    upload = await _request_upload(pm_client, ticket["id"], size_bytes=5)

    response = await pm_client.post(
        f"/tickets/{ticket['id']}/attachments/{upload.json()['attachment_id']}/finalize",
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "attachment_upload_verification_failed"


async def test_finalize_with_size_mismatch_sets_failed(
    create_ticket,
    pm_client: httpx.AsyncClient,
    storage_client: Any,
    storage_bucket: str,
    db_fetch_one,
) -> None:
    ticket = await create_ticket(owner_agent_id="cortex")
    upload = await _request_upload(pm_client, ticket["id"], size_bytes=5)
    attachment = await db_fetch_one(
        "SELECT s3_key FROM ticket_attachments WHERE id = :attachment_id",
        {"attachment_id": upload.json()["attachment_id"]},
    )
    storage_client.put_object(
        Bucket=storage_bucket,
        Key=attachment["s3_key"],
        Body=b"abc",
        ContentType="text/plain",
    )

    response = await pm_client.post(
        f"/tickets/{ticket['id']}/attachments/{upload.json()['attachment_id']}/finalize",
    )
    row = await db_fetch_one(
        "SELECT status FROM ticket_attachments WHERE id = :attachment_id",
        {"attachment_id": upload.json()["attachment_id"]},
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "attachment_upload_verification_failed"
    assert row["status"] == "failed"


async def test_finalize_same_attachment_twice_returns_409(
    create_ticket,
    pm_client: httpx.AsyncClient,
) -> None:
    ticket = await create_ticket(owner_agent_id="cortex")
    upload = await _request_upload(pm_client, ticket["id"], size_bytes=5)
    await _put_bytes(upload.json()["upload_url"], b"hello")
    first = await pm_client.post(
        f"/tickets/{ticket['id']}/attachments/{upload.json()['attachment_id']}/finalize",
    )

    second = await pm_client.post(
        f"/tickets/{ticket['id']}/attachments/{upload.json()['attachment_id']}/finalize",
    )

    assert first.status_code == 200, first.text
    assert second.status_code == 409
    assert second.json()["error"]["code"] == "attachment_not_ready"


async def test_list_attachments_returns_ready_only(
    create_ticket,
    pm_client: httpx.AsyncClient,
) -> None:
    ticket = await create_ticket(owner_agent_id="cortex")
    pending = await _request_upload(pm_client, ticket["id"], filename="pending.txt")
    ready = await _request_upload(pm_client, ticket["id"], filename="ready.txt")
    await _put_bytes(ready.json()["upload_url"], b"hello")
    finalized = await pm_client.post(
        f"/tickets/{ticket['id']}/attachments/{ready.json()['attachment_id']}/finalize",
    )

    response = await pm_client.get(f"/tickets/{ticket['id']}/attachments")

    assert pending.status_code == 201, pending.text
    assert finalized.status_code == 200, finalized.text
    assert [item["id"] for item in response.json()] == [ready.json()["attachment_id"]]


async def test_qa_agent_lists_attachments_for_other_agent_ticket(
    create_ticket,
    pm_client: httpx.AsyncClient,
    agent_qa_client: httpx.AsyncClient,
) -> None:
    ticket = await create_ticket(owner_agent_id="cortex")
    ready = await _request_upload(pm_client, ticket["id"], filename="review.txt")
    await _put_bytes(ready.json()["upload_url"], b"hello")
    finalized = await pm_client.post(
        f"/tickets/{ticket['id']}/attachments/{ready.json()['attachment_id']}/finalize",
    )

    response = await agent_qa_client.get(f"/tickets/{ticket['id']}/attachments")

    assert finalized.status_code == 200, finalized.text
    assert response.status_code == 200, response.text
    assert [item["id"] for item in response.json()] == [ready.json()["attachment_id"]]


async def test_list_excludes_pending_and_deleted(
    create_ticket,
    pm_client: httpx.AsyncClient,
) -> None:
    ticket = await create_ticket(owner_agent_id="cortex")
    pending = await _request_upload(pm_client, ticket["id"], filename="pending.txt")
    ready = await _request_upload(pm_client, ticket["id"], filename="ready.txt")
    await _put_bytes(ready.json()["upload_url"], b"hello")
    await pm_client.post(
        f"/tickets/{ticket['id']}/attachments/{ready.json()['attachment_id']}/finalize",
    )
    delete = await pm_client.delete(
        f"/tickets/{ticket['id']}/attachments/{ready.json()['attachment_id']}",
    )

    response = await pm_client.get(f"/tickets/{ticket['id']}/attachments")

    assert pending.status_code == 201, pending.text
    assert delete.status_code == 204, delete.text
    assert response.json() == []


async def test_get_download_url_for_ready_attachment(
    create_ticket,
    pm_client: httpx.AsyncClient,
) -> None:
    ticket = await create_ticket(owner_agent_id="cortex")
    upload = await _request_upload(pm_client, ticket["id"], filename="download.txt", size_bytes=5)
    await _put_bytes(upload.json()["upload_url"], b"hello")
    await pm_client.post(
        f"/tickets/{ticket['id']}/attachments/{upload.json()['attachment_id']}/finalize",
    )

    response = await pm_client.get(
        f"/tickets/{ticket['id']}/attachments/{upload.json()['attachment_id']}/download-url",
    )

    assert response.status_code == 200, response.text
    assert response.json()["download_url"]
    assert response.json()["filename"] == "download.txt"


async def test_qa_agent_gets_download_url_for_other_agent_ticket(
    create_ticket,
    pm_client: httpx.AsyncClient,
    agent_qa_client: httpx.AsyncClient,
) -> None:
    ticket = await create_ticket(owner_agent_id="cortex")
    upload = await _request_upload(pm_client, ticket["id"], filename="qa-download.txt", size_bytes=5)
    await _put_bytes(upload.json()["upload_url"], b"hello")
    await pm_client.post(
        f"/tickets/{ticket['id']}/attachments/{upload.json()['attachment_id']}/finalize",
    )

    response = await agent_qa_client.get(
        f"/tickets/{ticket['id']}/attachments/{upload.json()['attachment_id']}/download-url",
    )

    assert response.status_code == 200, response.text
    assert response.json()["download_url"]
    assert response.json()["filename"] == "qa-download.txt"


async def test_download_url_fetches_uploaded_bytes(
    create_ticket,
    pm_client: httpx.AsyncClient,
) -> None:
    ticket = await create_ticket(owner_agent_id="cortex")
    upload = await _request_upload(pm_client, ticket["id"], filename="download.txt", size_bytes=5)
    await _put_bytes(upload.json()["upload_url"], b"hello")
    await pm_client.post(
        f"/tickets/{ticket['id']}/attachments/{upload.json()['attachment_id']}/finalize",
    )
    download = await pm_client.get(
        f"/tickets/{ticket['id']}/attachments/{upload.json()['attachment_id']}/download-url",
    )

    async with httpx.AsyncClient() as client:
        response = await client.get(download.json()["download_url"])

    assert response.status_code == 200, response.text
    assert response.content == b"hello"


async def test_download_url_for_pending_attachment_returns_409(
    create_ticket,
    pm_client: httpx.AsyncClient,
) -> None:
    ticket = await create_ticket(owner_agent_id="cortex")
    upload = await _request_upload(pm_client, ticket["id"], size_bytes=5)

    response = await pm_client.get(
        f"/tickets/{ticket['id']}/attachments/{upload.json()['attachment_id']}/download-url",
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "attachment_not_ready"


async def test_soft_delete_by_pm_sets_deleted_at(
    create_ticket,
    pm_client: httpx.AsyncClient,
    db_fetch_one,
) -> None:
    ticket = await create_ticket(owner_agent_id="cortex")
    upload = await _request_upload(pm_client, ticket["id"], size_bytes=5)
    await _put_bytes(upload.json()["upload_url"], b"hello")
    await pm_client.post(
        f"/tickets/{ticket['id']}/attachments/{upload.json()['attachment_id']}/finalize",
    )

    response = await pm_client.delete(
        f"/tickets/{ticket['id']}/attachments/{upload.json()['attachment_id']}",
    )
    row = await db_fetch_one(
        "SELECT status, deleted_at FROM ticket_attachments WHERE id = :attachment_id",
        {"attachment_id": upload.json()["attachment_id"]},
    )

    assert response.status_code == 204, response.text
    assert row["status"] == "deleted"
    assert row["deleted_at"] is not None


async def test_soft_delete_by_agent_returns_403(
    create_ticket,
    agent_be_client: httpx.AsyncClient,
    pm_client: httpx.AsyncClient,
) -> None:
    ticket = await create_ticket(owner_agent_id="cortex")
    upload = await _request_upload(pm_client, ticket["id"], size_bytes=5)

    response = await agent_be_client.delete(
        f"/tickets/{ticket['id']}/attachments/{upload.json()['attachment_id']}",
    )

    assert response.status_code == 403


async def test_list_after_delete_excludes_deleted(
    create_ticket,
    pm_client: httpx.AsyncClient,
) -> None:
    ticket = await create_ticket(owner_agent_id="cortex")
    upload = await _request_upload(pm_client, ticket["id"], size_bytes=5)
    await _put_bytes(upload.json()["upload_url"], b"hello")
    await pm_client.post(
        f"/tickets/{ticket['id']}/attachments/{upload.json()['attachment_id']}/finalize",
    )
    await pm_client.delete(
        f"/tickets/{ticket['id']}/attachments/{upload.json()['attachment_id']}",
    )

    response = await pm_client.get(f"/tickets/{ticket['id']}/attachments")

    assert response.status_code == 200, response.text
    assert response.json() == []


async def test_cross_ticket_attachment_id_returns_404(
    create_ticket,
    pm_client: httpx.AsyncClient,
) -> None:
    first = await create_ticket(title="first", owner_agent_id="cortex")
    second = await create_ticket(title="second", owner_agent_id="cortex")
    upload = await _request_upload(pm_client, first["id"], size_bytes=5)

    response = await pm_client.get(
        f"/tickets/{second['id']}/attachments/{upload.json()['attachment_id']}/download-url",
    )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "attachment_not_found"
