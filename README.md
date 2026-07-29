# solrorm

A lightweight Solr ORM over [pysolr](https://github.com/django-haystack/pysolr):
entity mapping, typed fields, faceting and query building. Framework-neutral
and application-agnostic — the host application injects its configuration once
at startup, so the library can be shared by multiple applications as an equal,
unbranded dependency.

## Installation

Not published on PyPI yet — install from the git repository:

```bash
pip install "solrorm @ git+https://github.com/elixir-luxembourg/solrorm.git@v0.1.0"
```

With [uv](https://docs.astral.sh/uv/), declare `solrorm` in your dependencies
and pin the source:

```toml
[project]
dependencies = ["solrorm>=0.1.0"]

[tool.uv.sources]
solrorm = { git = "https://github.com/elixir-luxembourg/solrorm.git", tag = "v0.1.0" }
# for local development against a checkout:
# solrorm = { path = "../solrorm", editable = true }
```

Requires Python ≥ 3.10 and a reachable Solr ≥ 8.2.

## Design

`solrorm` does not own a web application. Every setting the library reads lives
on a `Settings` object handed to `SolrORM` at construction time, so no
module-level state is involved and one process can serve two collections:

```python
from solrorm import Settings, SolrORM

solr_orm = SolrORM(
    Settings(
        endpoint="http://localhost:8983/solr",
        collection="my_collection",
        entities={"dataset": Dataset},  # {name: SolrEntity subclass}
    )
)
```

A host that already keeps its configuration in a mapping (Flask's `app.config`,
say) builds the same object with `Settings.from_mapping`, which reads the
`SOLR_*` keys listed below:

```python
solr_orm = SolrORM(Settings.from_mapping(app.config))
```

Settings are read **eagerly**: `entities` is copied at construction, so the
registry must be complete before `SolrORM(...)` runs.

### Settings

| Setting | `from_mapping` key | Type | Default |
|---|---|---|---|
| `endpoint` | `SOLR_ENDPOINT` | `str` | required |
| `collection` | `SOLR_COLLECTION` | `str` | required |
| `entities` | `entities` | `dict[str, type[SolrEntity]]` | `{}` |
| `fuzzy_search_level` | `FUZZY_SEARCH_LEVEL` | `int` | `4` |
| `use_cursor_pagination` | `USE_CURSOR_PAGINATION` | `bool` | `False` |
| `boost` | `SOLR_BOOST` | `dict[str, str]` — per entity, the `qf` expression | `{}` |
| `default_sort` | `SOLR_DEFAULT_SORT` | `dict[str, str]` — per entity, the field to sort on | `{}` |
| `query_text_field` | `SOLR_QUERY_TEXT_FIELD` | `dict[str, list[str]]` — per entity, the fields copied into `_text_` | `{}` |

`Settings` is a frozen dataclass: build a new one rather than mutating it.

## Usage

Declare entities as `SolrEntity` subclasses with typed field descriptors:

```python
from solrorm import (
    SolrAutomaticQuery,
    SolrDateTimeField,
    SolrEntity,
    SolrField,
    SolrIntField,
)


class Dataset(SolrEntity):
    title = SolrField("title")
    keywords = SolrField("keywords", multivalued=True)
    year = SolrIntField("year")
    published = SolrDateTimeField("published")

    # optional: opt into the automatic query builder instead of plain SolrQuery
    query_class = SolrAutomaticQuery
```

Then wire the ORM and the entity registry, in this order:

```python
from solrorm import Settings, SolrORM

app.config["entities"] = {"dataset": Dataset}
solr_orm = SolrORM(Settings.from_mapping(app.config))
```

Instantiating `SolrORM` walks the `SolrEntity` subclasses and attaches to each
of them a `query` object — an instance of the class named in the entity's
`query_class` attribute, or `SolrQuery` if it has none — plus the ORM itself.
Entity classes must therefore be imported, and `settings.entities` populated,
before `SolrORM(...)` runs; concrete models must subclass `SolrEntity`
*directly* for the discovery to see them.

Manage the schema and index documents:

```python
solr_orm.create_fields()  # create the Solr fields for all entities
solr_orm.update_fields()  # push field changes
Dataset(entity_id="ds-1").save(commit=True)
```

Query, facet and fetch:

```python
results = Dataset.query.search(query="cancer", rows=20, sort="year")
dataset = Dataset.query.get("ds-1")
count = Dataset.query.count()
for dataset in Dataset.query.all():
    ...
```

## Contents

| Module | Purpose |
|---|---|
| `solrorm.orm` | `SolrORM`, `SolrQuery`, `SolrAutomaticQuery` — Solr access + query building |
| `solrorm.entity` | `SolrEntity` — base class for indexed entities |
| `solrorm.fields` | typed field descriptors (`SolrField`, `SolrIntField`, ...) |
| `solrorm.schema` | `SolrSchemaAdmin` — schema management |
| `solrorm.facets` | `Facet`, `FacetRange` |
| `solrorm.exceptions` | `SolrORMError`, `SolrQueryException` |
| `solrorm.config` | `Settings` — the library's whole configuration surface |

Every public name above is re-exported from the `solrorm` package itself, so
`from solrorm import SolrField` works and no code needs to depend on the module
layout.

## Development

```bash
uv sync --all-groups
uv run ruff check .
uv run ruff format .
uv run pytest
uv run ty check
```

The test suite needs no reachable Solr: `tests/conftest.py` fakes the indexer.

## Known tech debt

- `orm.py` still imports `flask.Response` and `werkzeug.exceptions.abort`,
  so `Flask`/`werkzeug` remain runtime dependencies. Removing these would make
  the library fully framework-neutral.

## License

Apache-2.0. See [`LICENSE`](LICENSE).
