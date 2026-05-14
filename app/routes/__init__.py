"""Route registration."""

from fastapi import APIRouter

from app.routes import (
    agents,
    artifacts,
    attachments,
    audit,
    auth,
    github,
    health,
    mailbox,
    metrics,
    runtime_logs,
    ticket_github,
    ticket_messages,
    tickets,
)

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(auth.router)
api_router.include_router(github.router)
api_router.include_router(tickets.router)
api_router.include_router(ticket_github.router)
api_router.include_router(attachments.router)
api_router.include_router(audit.router)
api_router.include_router(artifacts.router)
api_router.include_router(metrics.router)
api_router.include_router(runtime_logs.ticket_router)
api_router.include_router(runtime_logs.router)
api_router.include_router(agents.router)
api_router.include_router(mailbox.router)
api_router.include_router(ticket_messages.router)
