# Changelog

## 0.1.0 -- 2026-09-10

Initial public release.

### Added

- stdio MCP server exposing Claude subagent orchestration tools
- `spawn_claude_agent` for launching independent background agents with optional workspace access
- `get_claude_agent` for polling agent status and results
- `wait_claude_agents` for waiting on up to four agents with cursor-based once-only result delivery
- `send_claude_message` for follow-up messages to running or idle agents
- `cancel_claude_agent` for local task cancellation
- `list_claude_agents` for recovery listing of recent agents
- `list_claude_models` for querying available models and effort support
- `ask_claude` for lightweight consultations returning an agent ID
- Configurable model and reasoning effort per agent, with automatic adaptation for models that lack effort support
- Workspace file tools: `list_directory`, `read_file`, `read_files` (batch of 16), `write_file`
- Durable task state persisted to disk across client restarts
- Request ID-based deduplication and task recovery
- Cross-process file locking for concurrent state access
- HTTPS enforcement for non-loopback API endpoints
- Background worker processes with heartbeat monitoring and deadline enforcement
- Truncation handling with automatic continuation for cut-off responses
- Unit test suite with no live API dependencies
