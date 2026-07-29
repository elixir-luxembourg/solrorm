# Contributing to solrorm

Thanks for helping out. This is a small library, so the process is short.

## Setting up

[uv](https://docs.astral.sh/uv/) manages the environment and the lock file:

```bash
uv sync --all-groups
```

That installs the runtime dependencies plus the `dev` group (`ruff`, `ty`) and
the `testing` group (`pytest`). Python ≥ 3.10 is required.

## The gate

Four commands, all of them gates in CI. Run them before every commit:

```bash
uv run ruff format .
uv run ruff check .
uv run pytest
uv run ty check
```

- **`ruff format`** — formatting, 88 columns.
- **`ruff check`** — lint: `E`, `F`, `W`, `I` (import order), `B` (bugbear) and
  `UP`. `UP` means annotations are written in the modern form (`str | None`,
  `list[str]`) even though the package supports Python 3.10.
- **`pytest`** — the suite needs **no reachable Solr**: `tests/conftest.py`
  provides a `fake_indexer` fixture standing in for `SolrORM.indexer` and a
  `fake_schema` fixture (an in-memory Solr schema) for anything schema-shaped.
  Use those rather than reaching for a live server.
- **`ty check`** — the codebase type-checks clean at **0 diagnostics**. This is
  not informational: a new diagnostic fails the build.

CI (`.github/workflows/ci.yml`) runs the same four on every push and pull
request, across Python 3.10, 3.11, 3.12 and 3.13.

## Writing changes

- **Every behaviour change gets a test in the same commit.** No test-later.
- **Every change that touches the API, an example, a setting or a dependency
  updates `README.md` in the same commit.**
- One logical change per commit; never mix a rename with a behaviour change.
- Record anything a consumer must change in `CHANGELOG.md`, under the
  unreleased version.
- Test entities must subclass `SolrEntity` **directly** — discovery walks
  `SolrEntity.__subclasses__()` — and must be listed in `ENTITIES` in
  `tests/conftest.py` to be visible to the ORM.
- Adding a public name means exporting it from `solrorm/__init__.py` and adding
  it to `__all__`; `tests/test_package.py` pins that surface and will fail
  otherwise.

## Releasing

The version lives in exactly one place, `solrorm.__version__`
(`solrorm/__init__.py`); `pyproject.toml` reads it via
`[tool.setuptools.dynamic]`. To release:

1. Bump `__version__`.
2. Retitle the unreleased section in `CHANGELOG.md` with the version and date.
3. Run the gate, then `uv build` and check the artefacts:

   ```bash
   uv build
   python -c "import solrorm; print(solrorm.__version__)"
   ```

4. Commit and tag `vX.Y.Z`.
