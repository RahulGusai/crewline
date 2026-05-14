# Crewline Integration Test Report

## Environment
- Postgres: localhost:5432, database `crewline_test`
- MinIO: localhost:9000, bucket `crewline-test-attachments`
- Backend: ASGI test client
- Test runtime: `<duration>`

## Summary
- Total tests: `<N>`
- Passed: `<N>`
- Failed: `<N>`
- Skipped: `<N>`

## Coverage by area

### Authentication
- Login flows
- Session management
- CSRF
- Agent API keys
- Public paths

### Tickets, State Machine, Audit
- CRUD
- Authorization
- Transitions
- Audit row assertions

### Layer 2 Mailbox
- Basic send/poll/ack/reject
- RPC request/response
- Auto-fired ticket messages
- Authorization gaps and skipped endpoint tests

### Attachments
- Presigned upload/download URLs
- MinIO object round trips
- Lifecycle and access control

### End-to-End
- Happy path
- Blocked flow
- QA failure/rework
- Cancellation
- Reassignment
- Attachment flow

## Failures

Document failing tests using:

```text
<test node id>
Expected:
Got:
Root cause:
Server log excerpt:
```

## Issues Found

- `<issue 1>`
