# Security Policy

## Secrets

Never commit `.env`, API keys, SMTP authorization codes, JWT secrets, database files, uploads, raw screenshots, logs, traces, or local MCP configuration.

Reviewed showcase images in `docs/images` are the explicit exception. They use synthetic local data; raw browser captures and portfolio handoff archives remain excluded. Configuration examples contain placeholders, never deployment credentials.

## Production configuration

- Set `ENV=production`.
- Generate unique `JWT_SECRET` (at least 32 characters) and `API_KEY_ENCRYPTION_KEY` (32-byte hex) values. Production rejects known example/development values and validates encryption configuration at startup.
- Never run E2E bootstrap against business data. Production mode rejects it; test runs require an explicit isolated database.
- Use explicit HTTPS origins in `CORS_ALLOW_ORIGINS`; wildcard credentials are rejected.
- Do not expose the intentionally vulnerable `target-system` service publicly.
- Rotate credentials immediately if they appear in logs, commits, screenshots, or issue attachments.

## Reporting

For a public repository, enable GitHub private vulnerability reporting. Do not publish proof-of-concept payloads containing real credentials or user data in issues.

## Publication review

See [the 2026-09-13 publication audit](docs/PUBLICATION-AUDIT-2026-09-13.md) for checked scope, exclusions, historical privacy metadata and deployment limitations. Local portfolio handoff files are excluded by default; publish selected evidence only after reviewing its contents.
