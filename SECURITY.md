# Security

## Architecture

Claude Subagents MCP is a local, single-user bridge between an MCP client (such as Codex) and an Anthropic-compatible API endpoint. It runs as a stdio process on the same machine as the client.

## What is sent to the endpoint

Task prompts, follow-up messages, and the contents of any files read by subagents are included in API requests to the configured `ANTHROPIC_BASE_URL`. If you grant workspace access, file contents within that directory may be transmitted. Choose the smallest workspace that covers the relevant files.

## Local state and history

Task state, including conversation histories, is persisted to the local state directory (`CLAUDE_AGENT_STATE_DIR` or the platform default). These files may contain sensitive material from prompts and workspace content. Protect the state directory with appropriate file permissions.

## Network security

The server rejects plain HTTP connections to non-loopback endpoints. Only `http://localhost`, `http://127.0.0.1`, and `http://[::1]` are accepted over HTTP. All other remote endpoints require HTTPS, ensuring API credentials are not sent in cleartext over the network.

URLs with embedded credentials, query strings, or fragments in `ANTHROPIC_BASE_URL` are rejected.

## Workspace path restrictions

Subagent file access is scoped to the workspace directory provided at spawn time through application-level path validation. The `.git`, `.codex`, and `.agents` directories are excluded. Symlinks in directory listings are skipped.

These restrictions are not an operating system sandbox. A determined or buggy subagent prompt could potentially reference paths outside the workspace if a path traversal bypass existed. Treat workspace scoping as defense in depth, not as a security boundary equivalent to OS-level isolation.

## Credential handling

- Set `ANTHROPIC_API_KEY` in your environment. The server reads it at runtime.
- Never include API keys in issue reports, configuration files committed to version control, or task prompts.
- The legacy `ANTHROPIC_PROXY_API_KEY` environment variable is supported as a fallback but `ANTHROPIC_API_KEY` is preferred.

## Reporting a vulnerability

If you discover a security issue, please report it privately through the repository's GitHub Security Advisories tab rather than opening a public issue. Private vulnerability reporting is enabled on this repository. Include a description of the vulnerability and steps to reproduce it. You can expect an initial response within a reasonable timeframe.

This is an early 0.1.0 release maintained by an individual developer. Response times may vary, but all reports will be reviewed.
