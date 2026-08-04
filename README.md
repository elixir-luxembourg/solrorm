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
`entities` and `query_text_field` are copied out of the mapping, so the library
never mutates your configuration and never sees a later edit to it.

### The query text field table

`query_text_field` maps an entity name to the fields whose contents
`create_fields()` copies into that entity's `_text_`, `_textfuzzy_` and
`_autocomplete_text_` catch-alls — the fields a free-text `search()` matches
against. It is plain, explicit configuration: an entity missing from the table
falls back to `SolrORM.DEFAULT_QUERY_FIELDS`, i.e. `["title"]`, and each entity
is resolved on its own, so naming one entity does not affect the others.

```python
Settings(
    endpoint="http://localhost:8983/solr",
    collection="mycollection",
    entities={"dataset": Dataset, "project": Project},
    query_text_field={
        # searching a dataset also matches its keywords and its abstract
        "dataset": ["title", "keywords", "abstract"],
        # "project" is absent: it keeps ["title"]
    },
)
```

Field names are relative to the entity and get its prefix (`dataset_keywords`);
the one exception is `"id"`, which is the collection-wide field and is copied
unprefixed. To make a free-text search match a *related* entity's content,
denormalise that content into a field of your own and list it here — the library
has no notion of which of your entities are related for search purposes, and no
opinion on what your entities are called.

Adding a field to the table is picked up by the next `create_fields()` run,
which adds the missing copy field directives and leaves the existing ones alone.
Removing one is not: Solr keeps copying the field until the directive is dropped,
which `delete_fields()` does for the whole entity.

## Usage

Declare entities as `SolrEntity` subclasses with typed field descriptors. A
field declared on the class describes the schema; read on an instance it yields
that instance's value, and a subclass may redeclare an inherited field —
`created` with `indexed=False`, say — to override it:

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

`SolrAutomaticQuery` resolves `boost` and `default_sort` per entity when its
`query` object is built, and stores the result on that object — its
`SORT_OPTIONS`, `SORT_LABELS`, `BOOST` and `DEFAULT_SORT` class attributes are
only the declared defaults, so a subclass may override them and entities never
see each other's values. Configuring `SOLR_BOOST` for one entity leaves the
others on their own default, `"<entity>_title^5 <entity>_text_^1"`.

Manage the schema and index documents:

```python
solr_orm.create_fields()  # create the Solr fields for all entities
solr_orm.update_fields()  # push field changes
solr_orm.delete_fields()  # drop them again
Dataset(entity_id="ds-1").save(commit=True)
```

### Managing the schema

`create_fields()` is **idempotent**: it asks Solr what the schema already holds
and adds only what is missing — the entity fields, the `type` discriminator, the
collection-global `autocomplete_text` field type, the three catch-all fields per
entity and their copy field directives. Running it against a populated
collection therefore changes nothing and never forces a reindex. Repairing a
schema is the same call: whatever was deleted comes back, the rest is left
alone.

`update_fields()` replaces the definition of each entity's own fields — use it
after changing a field's type or flags. Solr rewrites the field, so the affected
documents need reindexing. The catch-all fields and copy fields are treated as
in `create_fields()`: added when absent, never replaced.

Neither call aborts on a refusal. If Solr rejects one field — an unknown field
type, a change it will not make in place — the reason is logged at `WARNING` on
the `solrorm.schema` and `solrorm.orm` loggers and the remaining fields are
still written. Configure logging if you run either of these, or the refusals go
unseen:

```python
import logging

logging.getLogger("solrorm").setLevel(logging.INFO)
```

Both calls, and `delete_fields()`, iterate `settings.entities` — the registry is
the contract, so an entity class that is imported but not registered is left out
of the schema entirely.

Query, facet and fetch:

```python
results = Dataset.query.search(query="cancer", rows=20, sort="year")
dataset = Dataset.query.get("ds-1")
count = Dataset.query.count()
for dataset in Dataset.query.all():
    ...
ids = Dataset.query.all_ids()
```

`results.has_more` says whether Solr returned a full page, so there may be
another one; a search with no row limit (`rows=0` or `rows=None`) reports
`False`. `all()` and `all_ids()` page through the collection with a Solr cursor
rather than asking for everything at once.

Deleting takes either an id or a query, and exactly one of the two:

```python
solr_orm.delete(entity_id="dataset_ds-1")
solr_orm.delete(query="type:dataset AND dataset_year:1999")
Dataset.query.delete("dataset_year:1999")  # scoped to the entity type for you
```

Facet on individual values with `Facet`, or on intervals with `FacetRange`:

```python
from solrorm import Facet, FacetRange, Range

results = Dataset.query.search(
    query="",
    facets=[
        Facet("keywords", "Keywords"),
        FacetRange("year", "Year", Range(2000, 2025, 5)),
    ],
)
```

The returned `results.facets` keys have the entity prefix stripped, so they match
the field names given to the facet.

`query.get_facets([...])` builds the same objects from `(attribute, label)`
tuples, skipping any attribute the entity does not declare. Add a third element
to select values by default — the library has no opinion about which of your
fields deserve one:

```python
facets = Dataset.query.get_facets(
    [("keywords", "Keywords"), ("status", "Status", ["Active"])]
)
```

### Missing entities

`get()` and `get_by_slug()` return `None` when nothing matches. solrorm is
framework-neutral — it never aborts your request — so the web-framework
response stays in the host:

```python
from flask import abort

dataset = Dataset.query.get(dataset_id)
if dataset is None:
    abort(404)
```

Where an absent entity means inconsistent data rather than an expected outcome —
resolving a foreign key, say — use `get_or_raise()`, which raises
`SolrEntityNotFound` (a `SolrORMError` subclass) naming the entity and the id:

```python
from solrorm import SolrEntityNotFound

try:
    dataset = Dataset.query.get_or_raise(dataset_id)
except SolrEntityNotFound:
    logger.warning("dataset %s is referenced but not indexed", dataset_id)
```

### Escaping: what is a value and what is a query

Ids, slugs and selected facet values are treated as **values**: they are
backslash-escaped with `escape_solr_value` before being interpolated into Lucene
syntax, so a quote, a colon or a paren in user input cannot break the query or
change its meaning. This includes a `FacetRange`'s selected values, which are
literal values too — to filter on an interval, pass the range yourself in `fq`:

```python
Dataset.query.search(query="", fq=["dataset_year:[2000 TO 2010]"])
```

The `query` argument of `search()` and the `query` argument of `delete()` are
the deliberate exceptions: they are documented as Solr query syntax and are
passed through **unescaped**, so a user typing `dataset_title:cancer OR
dataset_year:2020` still gets the query they wrote. Never build those two
strings by interpolating untrusted input — escape the values you interpolate:

```python
from solrorm import escape_solr_value

Dataset.query.search(query=f'dataset_title:"{escape_solr_value(user_input)}"')
```

### Relationships

`SolrForeignKeyField` stores the id of the linked entity, and reading the
attribute suffixed with `_entities` resolves it into instances:

```python
class Dataset(SolrEntity):
    project = SolrForeignKeyField("project", "project", reversed_by="data_use")


dataset.project_entities  # the Project instances this dataset points at
project.data_use_entities  # the datasets pointing back at this project
```

`reversed_by` names the reverse accessor on the *target* entity — here
`project.data_use_entities`. The name may contain underscores; only the trailing
`_entity`/`_entities` is stripped. Pass `reversed_multiple=True` for a list, or
leave it `False` to get a single instance.

### Serialisation

`entity.to_dict()` produces the document that goes to Solr — keys prefixed with
the entity name, binary fields base64-encoded, `SolrJsonField` values dumped as
JSON — and `EntityClass.from_json(doc)` reads one back, decoding datetimes,
integers, binary blobs and JSON into Python values. `SolrQuery` uses the very
same helpers when it builds instances from search results, so the two paths
cannot disagree.

A `SolrJsonField` given a `model` serialises each element with the model's
`to_json()` and rebuilds it with its `from_json()` classmethod, in both
directions:

```python
class Contact:
    def to_json(self):
        return {"name": self.name}

    @classmethod
    def from_json(cls, data):
        return cls(data["name"])


class Dataset(SolrEntity):
    contacts = SolrJsonField("contacts", model=Contact, multivalued=True)
```

## Contents

| Module | Purpose |
|---|---|
| `solrorm.orm` | `SolrORM`, `SolrQuery`, `SolrAutomaticQuery`, `SolrResults`, `escape_solr_value` — Solr access + query building |
| `solrorm.entity` | `SolrEntity` — base class for indexed entities |
| `solrorm.fields` | typed field descriptors (`SolrField`, `SolrIntField`, ...) |
| `solrorm.schema` | `SolrSchemaAdmin` — schema management |
| `solrorm.facets` | `Facet`, `FacetRange` |
| `solrorm.exceptions` | `SolrORMError`, `SolrQueryException`, `SolrEntityNotFound` |
| `solrorm.config` | `Settings` — the library's whole configuration surface |

The package ships a `py.typed` marker, so consumers type-check against its
annotations.

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

All four are gates in CI, `ty` included — the codebase type-checks clean. Ruff
runs `E`, `F`, `W`, `I` (import order), `B` (bugbear) and `UP`, so annotations
are written in the modern form (`str | None`, `list[str]`) even though the
package supports Python 3.10.

The test suite needs no reachable Solr: `tests/conftest.py` fakes the indexer.

See [`CONTRIBUTING.md`](CONTRIBUTING.md) for the full workflow and the release
steps, and [`CHANGELOG.md`](CHANGELOG.md) for what each version contains.

The version has a single source, `solrorm.__version__`; `pyproject.toml` reads
it from there.

## License

Apache-2.0. See [`LICENSE`](LICENSE).
