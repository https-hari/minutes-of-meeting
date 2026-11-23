# CLAUDE.md

The project instructions for all coding agents are in AGENTS.md. Read and follow them:

@AGENTS.md

## Notes for Claude Code

- Start by running the backend tests (`cd backend && TEST_DATABASE_URL=... python -m pytest -q`).
- Use plan mode for anything that touches the schema, auth, or more than one of backend / web / extension.
- You can't test the Chrome extension or a real Google Meet call from the terminal; tell the user exactly what to click.
- Prefer small diffs. Show the diff and wait for approval before committing; don't add co-author lines.
