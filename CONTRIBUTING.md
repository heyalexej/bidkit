# Contributing to bidkit

Thanks for helping out! This guide covers the dev setup, the commit conventions, and how the
code generation works.

## Development setup

bidkit uses [uv](https://docs.astral.sh/uv/) exclusively:

```bash
uv sync --extra dev        # create .venv and install everything
uv run pytest              # tests
uv run ruff check .        # lint
uv run ruff format .       # format
uv run ty check src tests  # type check
```

All four must pass before a PR is ready; CI enforces them on Python 3.11–3.14.

Optional but recommended:

```bash
uvx pre-commit install --install-hooks   # lint/format + commit-message checks on commit
```

## Commit messages: Conventional Commits 1.0.0

Every commit message MUST follow [Conventional Commits 1.0.0](https://www.conventionalcommits.org/en/v1.0.0/).
Releases and the changelog are generated from them (release-please), so the format is
load-bearing, not cosmetic. CI also validates PR titles, which become the squash-commit
message.

```
<type>(<optional scope>): <description>

[optional body]

[optional BREAKING CHANGE: footer]
```

| Type | Use for | Release effect |
|------|---------|----------------|
| `feat` | new user-facing capability | minor bump |
| `fix` | bug fixes | patch bump |
| `perf` | performance improvements | patch bump |
| `refactor` | code change with no behavior change | none |
| `docs` | documentation only | none |
| `test` | tests only | none |
| `build` | packaging/build system | none |
| `ci` | CI configuration | none |
| `chore` | everything else | none |

Common scopes: `auth`, `transport`, `retry`, `pagination`, `signing`, `config`, `errors`,
`models`, `generator`, `packaging`, `scripts`, `readme`, `examples`.

Breaking changes: add `!` after the type/scope (`feat(transport)!: ...`) **and** a
`BREAKING CHANGE:` footer describing the migration.

## Code generation

The resource classes and Pydantic models under `src/bidkit/generated/` are **generated —
never edit them by hand** (CI fails on drift). To change them, change the generator or the
specs and regenerate:

```bash
uv run --extra dev scripts/generate_openapi.py
```

Pipeline: raw eBay OpenAPI contracts in `specs/ebay/` → compatibility patches
(`preprocess_spec`) → normalized specs in `specs/normalized/` (git-ignored intermediate) →
`datamodel-code-generator` for models + a local renderer for the resource classes.

To update the specs themselves, download the current contracts from
[developer.ebay.com](https://developer.ebay.com/) and place them via
`scripts/sync_ebay_specs.py`, then regenerate. Note that the spec files are © eBay Inc.
under the eBay API License Agreement (see [NOTICE](NOTICE)).

## Pull requests

- Keep PRs focused; one logical change per PR.
- PR titles must be valid Conventional Commit headers (they become the squash commit).
- Add or update tests for behavior changes; tests are wire-level (`httpx.MockTransport`),
  fast, and offline — no eBay credentials needed.
- Don't commit anything derived from real credentials, tokens, or account data.

## Versioning & releases

bidkit follows [SemVer](https://semver.org/) with 0.x semantics: while the major version
is 0, `feat`/breaking changes bump the **minor** version and fixes bump the **patch**.
Releases are cut by release-please from the commit history; maintainers merge the release
PR and CI publishes to PyPI. 1.0.0 will be tagged once the public surface has settled.
