## What & why

<!-- What does this change, and what problem does it solve? -->

## Checklist

- [ ] PR title is a valid [Conventional Commit](https://www.conventionalcommits.org/en/v1.0.0/) header (it becomes the squash commit)
- [ ] `uv run pytest`, `uv run ruff check .`, `uv run ruff format --check .`, and `uv run ty check src tests` pass
- [ ] Tests added/updated for behavior changes
- [ ] No hand edits to `src/bidkit/generated/` (change the generator/specs and regenerate instead)
- [ ] No credentials, tokens, or real account data in code, tests, or fixtures
