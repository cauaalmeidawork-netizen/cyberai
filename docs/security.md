# Security Architecture

## Threat model assumptions

- Users of this platform include security professionals and researchers.
- Some user requests will be adversarial by design (CTF, lab, authorized tests).
- Output may include code, commands and methodologies.
- A bug in tenant isolation is a critical breach.

## Controls

### Authentication

- The product authenticates users through generic OIDC.
- The browser receives only an opaque application session cookie; OIDC tokens
  and refresh tokens are not exposed to frontend code.
- Session cookies do not contain trusted authorization claims. The database
  stores only a hash of the opaque session token.
- Legacy Bearer authentication is restricted to local development and CI.
- No passwords are stored in the application.

### Authorization

- Multi-tenancy: shared database, shared schema, `org_id` column, PostgreSQL RLS.
- Application code never trusts a client-supplied `org_id`.
- Membership is the authority for the active organization, role and RBAC
  permissions. `User.org_id` is retained only for migration compatibility.
- Row Level Security is enabled and forced on tenant-scoped tables.
- Organization switching is explicit and only allowed for active memberships.

### Input safety

- Untrusted content is isolated from system instructions.
- User messages, files, RAG chunks and tool output are validated and passed
  through a policy engine before prompt assembly.
- Request IDs and trace IDs are validated, not echoed unsanitized.

### Output safety

- Stack traces, driver messages and secrets are never returned to clients.
- Errors are serialised as RFC 9457 problem documents.
- Logs redact credentials and sensitive headers.

### Policy

- The Policy Engine produces structured decisions (`allow`, `restrict`, `refuse`,
  `require_context`) and is versioned.
- Sensitive decisions are auditable.
- Legitimate authorized research is allowed; abuse against third parties is not.

### Secrets

- Secrets come from environment variables; `.env` files are not committed.
- Database and Redis URLs are masked in logs.
- Provider API keys live in backend configuration only.

## Secure defaults

- CORS origins are explicit; wildcard is rejected in deployed environments.
- HSTS headers in production.
- Statement timeout configured on PostgreSQL connections.
- Health probes do not expose dependency connection strings.

## Validation

Security boundaries are tested:

- tenant binding requires a transaction;
- invalid tenant UUIDs are rejected;
- request IDs are sanitised;
- security headers are present;
- logs redact credentials.
