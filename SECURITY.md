# Security Policy

## Secrets

Never commit `.env`, API keys, SMTP authorization codes, JWT secrets, database files, uploads, screenshots, logs, traces, or local MCP configuration.

An SMTP authorization code appeared in an older private development tree. The owner revoked it before this public-ready directory was created. This directory contains only empty placeholders and comments.

## Production configuration

- Set `ENV=production`.
- Generate unique `JWT_SECRET` and `API_KEY_ENCRYPTION_KEY` values.
- Use explicit HTTPS origins in `CORS_ALLOW_ORIGINS`; wildcard credentials are rejected.
- Do not expose the intentionally vulnerable `target-system` service publicly.
- Rotate credentials immediately if they appear in logs, commits, screenshots, or issue attachments.

## Reporting

For a public repository, enable GitHub private vulnerability reporting. Do not publish proof-of-concept payloads containing real credentials or user data in issues.
