# Use Claude subagents in Codex

A Python stdlib MCP server that delegates tasks to up to four parallel Claude subagents, with optional workspace file access and per-agent model and reasoning effort configuration. Other stdio MCP clients are also supported.

![A tasteful diagram of a central controller node linked to four modular agents, each representing an independent Claude subagent working in parallel](assets/claude-subagents-banner.png)

## Features

- **Parallel agent orchestration** -- spawn up to four concurrent Claude subagents, each with its own task, model, and reasoning effort
- **Async spawn/wait pattern** -- agents run in background worker processes; your main session continues working while they do
- **Cursor-based result delivery** -- wait on multiple agents at once, receive each result exactly once, and track delivery with cursors
- **Workspace file access** -- optionally grant agents scoped read or read/write access to a directory, with path restrictions that exclude `.git`, `.codex`, and `.agents`
- **Follow-up messages** -- send corrections or additional instructions to running or idle agents without restarting their context
- **Model and effort selection** -- choose any model advertised by your proxy, with configurable reasoning effort that adapts automatically for models that lack effort support
- **Durable task state** -- agent progress persists to disk across MCP client restarts; recover tasks by ID or optional request key
- **Deduplication** -- identical in-flight tasks are detected and reused, preventing accidental double-spawns after transport failures
- **No external dependencies** -- runs on Python 3.11+ using only the standard library
- **Batch file reads** -- agents can read up to 16 files in a single tool call, reducing round trips during source review

## Requirements

- Python 3.11 or later
- An Anthropic-compatible API endpoint (local proxy or `https://api.anthropic.com`)

## Installation

Clone the repository and install:

```bash
git clone https://github.com/jordankzf/claude-subagents-mcp.git
cd claude-subagents-mcp
python -m pip install .
```

You can also install directly from GitHub:

```bash
pip install git+https://github.com/jordankzf/claude-subagents-mcp.git
```

This project is not published to PyPI.

## Quickstart

After installation, the server is available as a console command:

```bash
claude-subagents-mcp
```

Or run it directly:

```bash
python claude_subagents_mcp.py
```

The server communicates over stdio using the MCP JSON-RPC protocol. Configure your MCP client to launch the command and connect over stdin/stdout.

### Codex Configuration

Create or edit your Codex MCP configuration to include the server. See `examples/codex-config.toml` for a working template:

```toml
[mcp_servers.claude-subagents]
command = "claude-subagents-mcp"
tool_timeout_sec = 65
env_vars = ["ANTHROPIC_API_KEY"]

[mcp_servers.claude-subagents.env]
ANTHROPIC_BASE_URL = "https://api.anthropic.com"
CLAUDE_DEFAULT_MODEL = "claude-fable-5-1"
CLAUDE_DEFAULT_REASONING_EFFORT = "medium"
```

The `env_vars` array forwards `ANTHROPIC_API_KEY` from your shell environment into the Codex process, which passes it through to the MCP server. The `env` table sets additional configuration directly. Never commit secrets to the repository or to this file; set `ANTHROPIC_API_KEY` in your environment instead.

You can also configure all settings through environment variables in your shell before launching Codex:

```bash
export ANTHROPIC_API_KEY="your-api-key"
export ANTHROPIC_BASE_URL="https://api.anthropic.com"
export CLAUDE_DEFAULT_MODEL="claude-fable-5-1"
export CLAUDE_DEFAULT_REASONING_EFFORT="medium"
```

## Environment Variables

| Variable | Default | Description |
|---|---|---|
| `ANTHROPIC_API_KEY` | *(none, recommended)* | API key for the configured Anthropic-compatible endpoint |
| `ANTHROPIC_PROXY_API_KEY` | *(none)* | Legacy alias for `ANTHROPIC_API_KEY` |
| `ANTHROPIC_BASE_URL` | `http://localhost:8317` | Base URL of the API endpoint. Configurable to any Anthropic-compatible service including `https://api.anthropic.com`. Remote HTTP is rejected; only HTTPS is accepted outside loopback addresses |
| `CLAUDE_DEFAULT_MODEL` | `claude-fable-5-1` | Default model ID passed to the endpoint |
| `CLAUDE_DEFAULT_REASONING_EFFORT` | `medium` | Default reasoning effort: `default`, `low`, `medium`, `high`, `xhigh`, or `max` |
| `CLAUDE_AGENT_STATE_DIR` | *(platform default)* | Directory for persisted task state. On Windows: `%LOCALAPPDATA%\claude-subagents-mcp\tasks`. On Linux/macOS: `~/.local/share/claude-subagents-mcp/tasks` |

## Tools

| Tool | Description |
|---|---|
| `spawn_claude_agent` | Spawn an independent subagent with a task, optional workspace, model, and effort. Returns an agent ID immediately |
| `get_claude_agent` | Read agent status, activity, changed files, and result. Optionally wait up to 10 seconds |
| `wait_claude_agents` | Wait for the first of up to four agents to finish (max 50 seconds). Returns full result with cursors for once-only delivery |
| `send_claude_message` | Send a follow-up to a running or idle agent. Running agents receive it at the next response boundary; idle agents resume |
| `cancel_claude_agent` | Cancel an active task. Prevents further file operations; already-pending API requests may complete in the background |
| `list_claude_agents` | Recovery only: compact summaries of recent agents. Normally use the ID from spawn directly with `wait_claude_agents` |
| `list_claude_models` | List models advertised by the proxy and current bridge defaults. Use when choosing a model, not before every spawn |
| `ask_claude` | Start a consultation and return an agent ID immediately. Collect the answer with `wait_claude_agents` or `get_claude_agent`. For workspace tasks use `spawn_claude_agent` |

## Model and Effort Selection

Each agent can target a specific model and reasoning effort level. The defaults are `claude-fable-5-1` and `medium`, configurable through environment variables.

Available effort levels: `default`, `low`, `medium`, `high`, `xhigh`, `max`.

Setting effort to `default` omits the effort parameter from the API request entirely, letting the provider decide.

**Automatic adaptation with reported adjustment:** When a model is known not to support effort control (or when the proxy explicitly rejects it), inherited effort settings are automatically omitted. The server remembers which models lack effort support and omits the parameter on future requests. The adjustment is not silent: the `configuration_note` field in the response explains what was changed and why.

**Explicit choices are honored or rejected clearly.** If you explicitly set `reasoning_effort` on a spawn call and the model does not support it, the request fails with a clear error rather than changing your intent. This distinction between inherited defaults and explicit choices prevents surprising behavior.

Unknown model capabilities are not guaranteed. A model not yet tested for effort support will attempt the request as configured; if the provider rejects it and the effort was inherited, it retries once without effort and reports the adjustment. If the effort was explicit, the failure is reported.

## Reliability and Limitations

- **Up to four concurrent agents.** Additional spawns are rejected until an active agent completes or is cancelled.
- **Spawn and wait timeouts.** `wait_claude_agents` accepts up to 50 seconds. Individual tasks default to 300 seconds (configurable 10 to 900).
- **Cursor-based delivery.** Each terminal result is delivered exactly once per wait call. Pass the returned `cursors` object back on subsequent waits to avoid re-receiving completed results.
- **No shell, browser, or native panel access.** Subagents can only use the file tools provided by the server (list, read, batch read, write). They cannot execute commands, open browsers, or display UI.
- **Workspace path restrictions are not an OS sandbox.** File access is scoped to the provided workspace directory through path validation, but this is application-level enforcement, not kernel-level isolation.
- **Prompts and file contents are sent to the configured endpoint.** Be mindful of what you include in tasks and workspaces.
- **Task histories are stored locally** and may contain sensitive material. The state directory should be treated accordingly.
- **CI covers Windows, Linux, and macOS** with Python 3.11 through 3.13. Windows has additional live testing.
- **This is an initial 0.1.0 release**, not a production guarantee. Expect rough edges.

## Examples

### Spawn and wait for a single agent

```
spawn_claude_agent(task="Analyze the error handling in src/api.py", workspace="/path/to/project")
  -> { agent_id: "abc123...", status: "queued" }

wait_claude_agents(agent_ids=["abc123..."])
  -> { results: [{ agent_id: "abc123...", status: "completed", result: "..." }], cursors: {...} }
```

### Parallel agents with cursor tracking

```
spawn_claude_agent(task="Review authentication module", workspace="/project", task_name="auth-review")
spawn_claude_agent(task="Review database layer", workspace="/project", task_name="db-review")

wait_claude_agents(agent_ids=["id1", "id2"], timeout_seconds=45)
  -> { results: [first completed], pending: [still running], cursors: {"id1": 3} }

wait_claude_agents(agent_ids=["id1", "id2"], timeout_seconds=45, cursors={"id1": 3})
  -> { results: [second completed], cursors: {"id1": 3, "id2": 5} }
```

### Ask and wait

```
ask_claude(prompt="Summarize the key differences between these two approaches")
  -> { agent_id: "def456...", status: "queued" }

wait_claude_agents(agent_ids=["def456..."])
  -> { results: [{ agent_id: "def456...", status: "completed", result: "..." }], cursors: {...} }
```

### Follow-up message

```
send_claude_message(agent_id="abc123...", message="Also check for SQL injection risks")
wait_claude_agents(agent_ids=["abc123..."])
```

## Testing

The test suite uses `unittest` and does not make live API calls:

```bash
python -m unittest discover -s tests
```

CI runs this suite on Windows, Linux, and macOS across Python 3.11, 3.12, and 3.13.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines on reporting issues, suggesting features, and submitting pull requests.

## Security

See [SECURITY.md](SECURITY.md) for the security model, known boundaries, and responsible disclosure guidance.

## License

[MIT](LICENSE) -- Copyright 2026 jordankzf
