# solrorm

A lightweight Solr ORM over [pysolr](https://github.com/django-haystack/pysolr):
entity mapping, typed fields, faceting and query building. Framework-neutral
and application-agnostic — the host application injects its configuration once
at startup, so the library can be shared by multiple applications as an equal,
unbranded dependency.

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

## Contents

| Module | Purpose |
|---|---|
| `solrorm.solr_orm` | `SolrORM`, `SolrAutomaticQuery` — Solr access + query building |
| `solrorm.solr_orm_entity` | `SolrEntity` — base class for indexed entities |
| `solrorm.solr_orm_fields` | typed field descriptors (`SolrField`, `SolrIntField`, ...) |
| `solrorm.solr_orm_schema` | `SolrSchemaAdmin` — schema management |
| `solrorm.facets` | `Facet`, `FacetRange` |
| `solrorm.exceptions` | `SolrError`, `SolrQueryException` |
| `solrorm.config` | `configure()` + the config accessor |

## Known tech debt

- `solr_orm.py` still imports `flask.Response` and `werkzeug.exceptions.abort`,
  so `Flask`/`werkzeug` remain runtime dependencies. Removing these would make
  the library fully framework-neutral.

## License

Apache-2.0. See [`LICENSE`](LICENSE).
