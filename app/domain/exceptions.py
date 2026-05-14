"""Domain-layer exception hierarchy."""

from __future__ import annotations

from typing import Any


class DomainError(Exception):
    """Base for all domain-layer errors."""

    code: str = "domain_error"

    def __init__(self, message: str = "") -> None:
        self.message = message or self.__class__.__name__
        super().__init__(self.message)

    def to_details(self) -> dict[str, object]:
        """Subclasses override to expose structured fields."""
        return {}


class TicketNotFoundError(DomainError):
    code = "ticket_not_found"

    def __init__(self, ticket_id: int) -> None:
        self.ticket_id = ticket_id
        super().__init__(f"Ticket {ticket_id} not found")

    def to_details(self) -> dict[str, object]:
        return {"ticket_id": self.ticket_id}


class AgentNotFoundError(DomainError):
    code = "agent_not_found"

    def __init__(self, agent_id: str) -> None:
        self.agent_id = agent_id
        super().__init__(f"Agent {agent_id!r} not found")

    def to_details(self) -> dict[str, object]:
        return {"agent_id": self.agent_id}


class ArtifactNotFoundError(DomainError):
    code = "artifact_not_found"

    def __init__(self, artifact_id: int) -> None:
        self.artifact_id = artifact_id
        super().__init__(f"Artifact {artifact_id} not found")

    def to_details(self) -> dict[str, object]:
        return {"artifact_id": self.artifact_id}


class InvalidActorError(DomainError):
    code = "invalid_actor"

    def __init__(self, actor: str, reason: str) -> None:
        self.actor = actor
        self.reason_text = reason
        super().__init__(f"Invalid actor {actor!r}: {reason}")

    def to_details(self) -> dict[str, object]:
        return {"actor": self.actor, "reason": self.reason_text}


class InvalidTransitionError(DomainError):
    code = "invalid_transition"

    def __init__(self, from_status: str | None, to_status: str) -> None:
        self.from_status = from_status
        self.to_status = to_status
        super().__init__(f"Cannot transition from {from_status} to {to_status}")

    def to_details(self) -> dict[str, object]:
        return {"from_status": self.from_status, "to_status": self.to_status}


class ActorNotPermittedError(DomainError):
    code = "actor_not_permitted"

    def __init__(self, actor: str, action: str) -> None:
        self.actor = actor
        self.action = action
        super().__init__(f"Actor {actor!r} is not permitted to {action}")

    def to_details(self) -> dict[str, object]:
        return {"actor": self.actor, "action": self.action}


class ReasonRequiredError(DomainError):
    code = "reason_required"

    def __init__(self, transition: str) -> None:
        self.transition = transition
        super().__init__(f"Reason is required for transition: {transition}")

    def to_details(self) -> dict[str, object]:
        return {"transition": self.transition}


class OverrideNotPermittedError(DomainError):
    code = "override_not_permitted"

    def __init__(self, actor: str) -> None:
        self.actor = actor
        super().__init__(f"Actor {actor!r} is not permitted to use pm_override (only PM)")

    def to_details(self) -> dict[str, object]:
        return {"actor": self.actor}


class InvalidTicketStateError(DomainError):
    code = "invalid_ticket_state"

    def __init__(self, ticket_id: int, current_status: str, action: str) -> None:
        self.ticket_id = ticket_id
        self.current_status = current_status
        self.action = action
        super().__init__(f"Ticket {ticket_id} in status {current_status} cannot {action}")

    def to_details(self) -> dict[str, object]:
        return {
            "ticket_id": self.ticket_id,
            "current_status": self.current_status,
            "action": self.action,
        }


class MailboxMessageNotFoundError(DomainError):
    code = "mailbox_message_not_found"

    def __init__(self, message_id: int) -> None:
        self.message_id = message_id
        super().__init__(f"Mailbox message {message_id} not found")

    def to_details(self) -> dict[str, Any]:
        return {"message_id": self.message_id}


class MessageStateConflictError(DomainError):
    code = "message_state_conflict"

    def __init__(self, message_id: int, current_state: str, attempted: str) -> None:
        self.message_id = message_id
        self.current_state = current_state
        self.attempted = attempted
        super().__init__(f"Cannot {attempted} message {message_id}: already {current_state}")

    def to_details(self) -> dict[str, Any]:
        return {
            "message_id": self.message_id,
            "current_state": self.current_state,
            "attempted": self.attempted,
        }


class InvalidMessageTypeError(DomainError):
    code = "invalid_message_type"

    def __init__(self, message_type: str) -> None:
        self.message_type = message_type
        super().__init__(f"Message type {message_type!r} cannot be sent directly")

    def to_details(self) -> dict[str, Any]:
        return {"message_type": self.message_type}


class CorrelationIdMismatchError(DomainError):
    code = "correlation_id_mismatch"

    def __init__(self, correlation_id: int, reason: str) -> None:
        self.correlation_id = correlation_id
        self.reason = reason
        super().__init__(f"Invalid correlation_id {correlation_id}: {reason}")

    def to_details(self) -> dict[str, Any]:
        return {"correlation_id": self.correlation_id, "reason": self.reason}


class AttachmentNotFoundError(DomainError):
    code = "attachment_not_found"

    def __init__(self, attachment_id: int) -> None:
        self.attachment_id = attachment_id
        super().__init__(f"Attachment {attachment_id} not found")

    def to_details(self) -> dict[str, Any]:
        return {"attachment_id": self.attachment_id}


class AttachmentTooLargeError(DomainError):
    code = "attachment_too_large"

    def __init__(self, size_bytes: int, max_bytes: int) -> None:
        self.size_bytes = size_bytes
        self.max_bytes = max_bytes
        super().__init__(f"Attachment size {size_bytes} exceeds maximum {max_bytes}")

    def to_details(self) -> dict[str, Any]:
        return {"size_bytes": self.size_bytes, "max_bytes": self.max_bytes}


class AttachmentContentTypeNotAllowedError(DomainError):
    code = "attachment_content_type_not_allowed"

    def __init__(self, content_type: str) -> None:
        self.content_type = content_type
        super().__init__(f"Content type {content_type!r} is not allowed")

    def to_details(self) -> dict[str, Any]:
        return {"content_type": self.content_type}


class AttachmentNotReadyError(DomainError):
    code = "attachment_not_ready"

    def __init__(self, attachment_id: int, current_status: str) -> None:
        self.attachment_id = attachment_id
        self.current_status = current_status
        super().__init__(f"Attachment {attachment_id} is in status {current_status!r}, not ready")

    def to_details(self) -> dict[str, Any]:
        return {
            "attachment_id": self.attachment_id,
            "current_status": self.current_status,
        }


class AttachmentUploadVerificationFailedError(DomainError):
    code = "attachment_upload_verification_failed"

    def __init__(self, attachment_id: int, reason: str) -> None:
        self.attachment_id = attachment_id
        self.reason = reason
        super().__init__(f"Cannot finalize attachment {attachment_id}: {reason}")

    def to_details(self) -> dict[str, Any]:
        return {"attachment_id": self.attachment_id, "reason": self.reason}


class GitHubNotConnectedError(DomainError):
    code = "github_not_connected"

    def __init__(self) -> None:
        super().__init__("GitHub is not connected")


class GitHubInstallationInactiveError(DomainError):
    code = "github_installation_inactive"

    def __init__(self, installation_id: int | None = None) -> None:
        self.installation_id = installation_id
        super().__init__("GitHub installation is inactive")

    def to_details(self) -> dict[str, Any]:
        return {"installation_id": self.installation_id}


class RepoNotAccessibleError(DomainError):
    code = "repo_not_accessible"

    def __init__(self, repo_full_name: str) -> None:
        self.repo_full_name = repo_full_name
        super().__init__(f"Repository {repo_full_name!r} is not accessible")

    def to_details(self) -> dict[str, Any]:
        return {"repo_full_name": self.repo_full_name}


class RelatedRepoInvalidError(DomainError):
    code = "related_repo_invalid"

    def __init__(self, repo_full_name: str, reason: str) -> None:
        self.repo_full_name = repo_full_name
        self.reason = reason
        super().__init__(f"Related repository {repo_full_name!r} is invalid: {reason}")

    def to_details(self) -> dict[str, Any]:
        return {"repo_full_name": self.repo_full_name, "reason": self.reason}


class GitHubApiError(DomainError):
    code = "github_api_error"

    def __init__(self, status_code: int, body: str) -> None:
        self.status_code = status_code
        self.body = body
        super().__init__(f"GitHub API error {status_code}")

    def to_details(self) -> dict[str, Any]:
        return {"status_code": self.status_code}


class GitHubTokenMintFailedError(DomainError):
    code = "github_token_mint_failed"

    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(f"Could not mint GitHub token: {reason}")

    def to_details(self) -> dict[str, Any]:
        return {"reason": self.reason}


class PrUrlAlreadySetError(DomainError):
    code = "pr_url_already_set"

    def __init__(self, ticket_id: int) -> None:
        self.ticket_id = ticket_id
        super().__init__(f"Ticket {ticket_id} already has a PR URL")

    def to_details(self) -> dict[str, Any]:
        return {"ticket_id": self.ticket_id}


class InvalidPrUrlFormatError(DomainError):
    code = "invalid_pr_url_format"

    def __init__(self, pr_url: str) -> None:
        self.pr_url = pr_url
        super().__init__("PR URL must match https://github.com/<owner>/<repo>/pull/<number>")

    def to_details(self) -> dict[str, Any]:
        return {"pr_url": self.pr_url}


class PrUrlRepoMismatchError(DomainError):
    code = "pr_url_repo_mismatch"

    def __init__(self, pr_repo: str, ticket_repo: str) -> None:
        self.pr_repo = pr_repo
        self.ticket_repo = ticket_repo
        super().__init__(f"PR repo {pr_repo!r} does not match ticket repo {ticket_repo!r}")

    def to_details(self) -> dict[str, Any]:
        return {"pr_repo": self.pr_repo, "ticket_repo": self.ticket_repo}


class NoPrUrlError(DomainError):
    code = "no_pr_url"

    def __init__(self, ticket_id: int) -> None:
        self.ticket_id = ticket_id
        super().__init__(f"Ticket {ticket_id} has no PR URL")

    def to_details(self) -> dict[str, Any]:
        return {"ticket_id": self.ticket_id}


class TicketNotDoneError(DomainError):
    code = "ticket_not_done"

    def __init__(self, ticket_id: int, status: str) -> None:
        self.ticket_id = ticket_id
        self.status = status
        super().__init__(f"Ticket {ticket_id} is not DONE")

    def to_details(self) -> dict[str, Any]:
        return {"ticket_id": self.ticket_id, "status": self.status}


class MergeNotAllowedError(DomainError):
    code = "merge_not_allowed"

    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(f"GitHub did not allow merge: {reason}")

    def to_details(self) -> dict[str, Any]:
        return {"reason": self.reason}


class MergeConflictError(DomainError):
    code = "merge_conflict"

    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(f"GitHub merge conflict: {reason}")

    def to_details(self) -> dict[str, Any]:
        return {"reason": self.reason}


class PrNotFoundError(DomainError):
    code = "pr_not_found"

    def __init__(self, pr_url: str) -> None:
        self.pr_url = pr_url
        super().__init__(f"Pull request not found: {pr_url}")

    def to_details(self) -> dict[str, Any]:
        return {"pr_url": self.pr_url}


class RuntimeLogNotFoundError(DomainError):
    code = "runtime_log_not_found"

    def __init__(self, log_id: int) -> None:
        self.log_id = log_id
        super().__init__(f"Runtime log {log_id} not found")

    def to_details(self) -> dict[str, Any]:
        return {"log_id": self.log_id}


class RuntimeLogTicketMismatchError(DomainError):
    code = "runtime_log_ticket_mismatch"

    def __init__(self, path_ticket_id: int, body_ticket_id: int) -> None:
        self.path_ticket_id = path_ticket_id
        self.body_ticket_id = body_ticket_id
        super().__init__("Runtime log ticket_id does not match path ticket_id")

    def to_details(self) -> dict[str, Any]:
        return {
            "path_ticket_id": self.path_ticket_id,
            "body_ticket_id": self.body_ticket_id,
        }
