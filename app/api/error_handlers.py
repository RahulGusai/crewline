"""Global exception handlers mapping domain errors to HTTP responses."""

from __future__ import annotations

from typing import cast

import structlog
from fastapi import FastAPI, Request, status
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import HTTPException as FastAPIHTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.types import ExceptionHandler

from app.domain.exceptions import DomainError

logger = structlog.get_logger(__name__)

STATUS_BY_CODE: dict[str, int] = {
    "ticket_not_found": status.HTTP_404_NOT_FOUND,
    "agent_not_found": status.HTTP_404_NOT_FOUND,
    "artifact_not_found": status.HTTP_404_NOT_FOUND,
    "invalid_actor": status.HTTP_422_UNPROCESSABLE_ENTITY,
    "invalid_transition": status.HTTP_409_CONFLICT,
    "actor_not_permitted": status.HTTP_403_FORBIDDEN,
    "reason_required": status.HTTP_422_UNPROCESSABLE_ENTITY,
    "override_not_permitted": status.HTTP_403_FORBIDDEN,
    "invalid_ticket_state": status.HTTP_409_CONFLICT,
    "mailbox_message_not_found": status.HTTP_404_NOT_FOUND,
    "message_state_conflict": status.HTTP_409_CONFLICT,
    "invalid_message_type": status.HTTP_422_UNPROCESSABLE_ENTITY,
    "correlation_id_mismatch": status.HTTP_422_UNPROCESSABLE_ENTITY,
    "attachment_not_found": status.HTTP_404_NOT_FOUND,
    "attachment_too_large": status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
    "attachment_content_type_not_allowed": status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
    "attachment_not_ready": status.HTTP_409_CONFLICT,
    "attachment_upload_verification_failed": status.HTTP_409_CONFLICT,
    "attachment_storage_unavailable": status.HTTP_502_BAD_GATEWAY,
    "github_not_connected": status.HTTP_400_BAD_REQUEST,
    "github_installation_inactive": status.HTTP_400_BAD_REQUEST,
    "repo_not_accessible": status.HTTP_400_BAD_REQUEST,
    "related_repo_invalid": status.HTTP_400_BAD_REQUEST,
    "github_api_error": status.HTTP_502_BAD_GATEWAY,
    "github_token_mint_failed": status.HTTP_502_BAD_GATEWAY,
    "pr_url_already_set": status.HTTP_409_CONFLICT,
    "invalid_pr_url_format": status.HTTP_422_UNPROCESSABLE_ENTITY,
    "pr_url_repo_mismatch": status.HTTP_422_UNPROCESSABLE_ENTITY,
    "no_pr_url": status.HTTP_400_BAD_REQUEST,
    "ticket_not_done": status.HTTP_409_CONFLICT,
    "merge_not_allowed": status.HTTP_409_CONFLICT,
    "merge_conflict": status.HTTP_409_CONFLICT,
    "pr_not_found": status.HTTP_404_NOT_FOUND,
    "runtime_log_not_found": status.HTTP_404_NOT_FOUND,
    "runtime_log_ticket_mismatch": status.HTTP_422_UNPROCESSABLE_ENTITY,
}

DEFAULT_DOMAIN_ERROR_STATUS = status.HTTP_500_INTERNAL_SERVER_ERROR


async def handle_domain_error(request: Request, exc: DomainError) -> JSONResponse:
    """Single handler for the entire DomainError hierarchy."""
    http_status = STATUS_BY_CODE.get(exc.code, DEFAULT_DOMAIN_ERROR_STATUS)
    return JSONResponse(
        status_code=http_status,
        content={
            "error": {
                "code": exc.code,
                "message": exc.message,
                "details": exc.to_details(),
            }
        },
    )


async def handle_validation_error(
    request: Request,
    exc: RequestValidationError,
) -> JSONResponse:
    """Return validation errors using the API error envelope."""
    logger.debug(
        "request.validation_error",
        method=request.method,
        path=request.url.path,
        payload=exc.body,
        errors=exc.errors(),
    )
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={
            "error": {
                "code": "validation_error",
                "message": "Request validation failed",
                # value_error entries carry the raw exception in ctx; encode for JSON
                "details": {"errors": jsonable_encoder(exc.errors())},
            }
        },
    )


async def handle_http_error(
    request: Request,
    exc: FastAPIHTTPException,
) -> JSONResponse:
    """Return FastAPI HTTP errors using the API error envelope."""
    code = "http_error"
    if exc.status_code == status.HTTP_401_UNAUTHORIZED:
        code = "not_authenticated"
    elif exc.status_code == status.HTTP_403_FORBIDDEN:
        code = "forbidden"
    return JSONResponse(
        status_code=exc.status_code,
        headers=getattr(exc, "headers", None),
        content={
            "error": {
                "code": code,
                "message": str(exc.detail),
                "details": {},
            }
        },
    )


def register_error_handlers(app: FastAPI) -> None:
    """Wire all error handlers onto the FastAPI app."""
    app.add_exception_handler(DomainError, cast(ExceptionHandler, handle_domain_error))
    app.add_exception_handler(
        FastAPIHTTPException,
        cast(ExceptionHandler, handle_http_error),
    )
    app.add_exception_handler(
        RequestValidationError,
        cast(ExceptionHandler, handle_validation_error),
    )
