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

`solrorm` does not own a web application. The host application injects its
configuration once at startup:

```python
import solrorm
from flask import Flask

app = Flask(__name__)
app.config.update(
    SOLR_ENDPOINT="http://localhost:8983/solr",
    SOLR_COLLECTION="my_collection",
    entities={...},          # {name: SolrEntity subclass}
)
solrorm.configure(app.config)   # store a reference to the config mapping
```

The ORM reads the values it needs (`SOLR_*`, the `entities` registry, ...)
through `solrorm.config`. Because a *reference* is stored, entries added after
`configure()` — such as the `entities` registry and the `_solr_orm` instance —
remain visible.

## Usage

Declare entities as `SolrEntity` subclasses with typed field descriptors:

```python
from solrorm.solr_orm_entity import SolrEntity
from solrorm.solr_orm import SolrAutomaticQuery
from solrorm.solr_orm_fields import SolrField, SolrIntField, SolrDateTimeField


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
from solrorm.solr_orm import SolrORM

app.config["entities"] = {"dataset": Dataset}
app.config["_solr_orm"] = SolrORM(
    app.config["SOLR_ENDPOINT"], app.config["SOLR_COLLECTION"]
)
```

Instantiating `SolrORM` walks the `SolrEntity` subclasses and attaches to each
of them a `query` object — an instance of the class named in the entity's
`query_class` attribute, or `SolrQuery` if it has none — plus the ORM itself.
Entity classes must therefore be imported before `SolrORM(...)` runs, and
concrete models must subclass `SolrEntity` *directly* for the discovery to see
them.

Manage the schema and index documents:

```python
solr_orm = app.config["_solr_orm"]
solr_orm.create_fields()          # create the Solr fields for all entities
solr_orm.update_fields()          # push field changes
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
| `solrorm.solr_orm` | `SolrORM`, `SolrQuery`, `SolrAutomaticQuery` — Solr access + query building |
| `solrorm.solr_orm_entity` | `SolrEntity` — base class for indexed entities |
| `solrorm.solr_orm_fields` | typed field descriptors (`SolrField`, `SolrIntField`, ...) |
| `solrorm.solr_orm_schema` | `SolrSchemaAdmin` — schema management |
| `solrorm.facets` | `Facet`, `FacetRange` |
| `solrorm.exceptions` | `SolrError`, `SolrQueryException` |
| `solrorm.config` | `configure()` + the config accessor |

## Development

```bash
uv sync --all-groups
uv run ruff check .
uv run ruff format .
uv run ty check
```

## Known tech debt

- `solr_orm.py` still imports `flask.Response` and `werkzeug.exceptions.abort`,
  so `Flask`/`werkzeug` remain runtime dependencies. Removing these would make
  the library fully framework-neutral.
- The library has no test suite of its own yet; the ORM is currently covered by
  the tests of the consuming applications.

## License

Apache-2.0. See [`LICENSE`](LICENSE).
