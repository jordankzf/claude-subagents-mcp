# Contributing

Thank you for your interest in contributing to Claude Subagents MCP.

## Reporting Issues

Open a GitHub issue with a clear description of the problem, including:

- What you expected to happen
- What actually happened
- Steps to reproduce
- Your Python version and operating system

Do not include API keys, credentials, or sensitive workspace content in issue reports.

## Suggesting Features

Feature suggestions are welcome as GitHub issues. Describe the use case and how the feature would fit into the existing tool set.

## Pull Requests

1. Fork the repository and create a branch for your change.
2. Keep changes focused. One pull request per logical change.
3. Run the test suite before submitting:

   ```bash
   python -m unittest discover -s tests
   ```

   Tests do not require a live API endpoint.

4. The implementation uses only the Python standard library (3.11+). Avoid adding external dependencies.
5. Update documentation if your change affects user-facing behavior.

## Code Style

- Follow existing patterns in the codebase.
- Keep functions focused and well-named.
- Error messages should be clear and actionable.

## Scope

This project is an MCP server for delegating Claude subagents. Changes that stay within that scope are most likely to be accepted. Major architectural changes should be discussed in an issue first.

## License

By submitting a pull request, you agree that your contribution is licensed under the MIT License.
