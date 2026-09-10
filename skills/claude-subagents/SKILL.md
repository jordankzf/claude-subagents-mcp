---
name: claude-subagents
description: Delegate independent tasks to parallel Claude subagents with optional workspace file access
---

# Skill: Claude Subagents

## Overview

Delegate independent tasks to Claude subagents running in parallel. Each agent can read or write files within a scoped workspace and returns a structured report when finished.

## When to Use

- Reviewing multiple files or modules in parallel
- Running independent analyses that do not depend on each other's output
- Delegating focused subtasks while continuing your own work
- Getting a second opinion on a specific question without blocking

## Workflow

1. **Spawn** one or more agents with `spawn_claude_agent`, providing a clear task description. Save the returned `agent_id`.
2. **Continue your own work** while agents run in the background.
3. **Wait** with `wait_claude_agents`, passing all agent IDs you are tracking. The call returns when the first agent finishes.
4. **Pass cursors back** on subsequent waits to avoid receiving the same result twice.
5. **Send follow-ups** with `send_claude_message` if you need to refine an agent's task or add new instructions.

## Chosen Overrides

When using this skill, apply these defaults unless the user specifies otherwise:

- Use `spawn_claude_agent` for any task that involves file access. Use `ask_claude` only for reasoning without workspace needs.
- Set `task_name` to a short descriptive label so results are easy to identify.
- Prefer `wait_claude_agents` over polling with `get_claude_agent`. Only use `get_claude_agent` for quick status checks.
- Do not call `list_claude_agents` before waiting. Use the agent ID returned by spawn directly.
- Grant `allow_writes: true` only when the task explicitly requires creating or modifying files.
- Set `workspace` to the narrowest relevant directory, not the entire filesystem root.
- When spawning multiple agents, spawn all of them before calling wait. Do not spawn and wait one at a time sequentially.
- After `ask_claude`, prefer collecting the answer with `wait_claude_agents` rather than polling with `get_claude_agent`.

## Example

```
# Spawn two parallel reviews
spawn_claude_agent(
  task="Review error handling in src/api.py and report any unhandled exceptions",
  workspace="/project",
  task_name="api-error-review"
)
spawn_claude_agent(
  task="Check database queries in src/db.py for SQL injection vulnerabilities",
  workspace="/project",
  task_name="db-security-review"
)

# Wait for results
wait_claude_agents(agent_ids=["id1", "id2"], timeout_seconds=45)
# Pass cursors on the next wait to get only new results
wait_claude_agents(agent_ids=["id1", "id2"], timeout_seconds=45, cursors={"id1": 3})
```

## Limitations

- Maximum four concurrent agents
- Agents have file tools only (list, read, batch read, write). No shell, browser, or network access.
- Workspace path scoping is application-level, not an OS sandbox
- Model effort support varies; inherited defaults adapt automatically with a reported adjustment, but explicit unsupported effort choices fail clearly
