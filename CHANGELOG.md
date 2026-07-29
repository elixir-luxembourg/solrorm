# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project
adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.0] — unreleased

First release.

### Added

- `SolrEntity` — declare an indexed entity as a subclass with typed field
  descriptors (`SolrField`, `SolrIntField`, `SolrDateTimeField`,
  `SolrJsonField`, `SolrForeignKeyField`, …), which describe the Solr schema on
  the class and carry values on an instance.
- `Settings` — a frozen dataclass naming every option the library reads, handed
  to `SolrORM` at construction, plus `Settings.from_mapping(mapping)` for hosts
  that keep their configuration in a mapping such as Flask's `app.config`. No
  module-level state, so one process can serve two collections.
- `SolrORM` — schema management (`create_fields`, `update_fields`,
  `delete_fields`, `check_schema`, `missing_fields`, `mismatched_fields`) and
  indexing (`add`, `delete`, `commit`). Field creation is idempotent: it adds
  only what the schema lacks, so running it against a populated collection
  neither drops the catch-all fields nor forces a reindex, and Solr's refusals
  are logged rather than swallowed.
- `SolrQuery` and `SolrAutomaticQuery` — search, faceting, `get`, `get_by_slug`,
  `count`, cursor-paginated `all()` / `all_ids()`, and reverse foreign-key
  lookups. `SolrAutomaticQuery` resolves boost and default sort per entity from
  the settings.
- `Facet`, `FacetRange` and `Range` for value and interval faceting.
- `escape_solr_value(value)` — backslash-escapes the Lucene special set, applied
  internally to every caller value the library interpolates into query syntax.
  The `query` argument of `search()` and `delete()` is Solr syntax by contract
  and stays raw, as are the interval clauses a selected `FacetRange` filters on,
  which are built from the bounds the library supplied.
- `SolrResults` — the `pysolr.Results` subclass returned by `search()` and
  `search_holding_entities()`, declaring the `entities` and `has_more`
  attributes those methods attach.
- `SolrSchemaAdmin` — a typed wrapper over Solr's schema API, used for every
  schema request the ORM makes.
- `SolrORMError`, `SolrQueryException` and `SolrEntityNotFound` in
  `solrorm.exceptions`. The library is framework-neutral: a lookup that finds
  nothing returns `None` and the host decides how to signal it.
- `py.typed`: the package ships its annotations, and every public name is
  re-exported from the `solrorm` package root.
- A test suite requiring no reachable Solr, and CI over Python 3.10–3.13
  running `ruff format`, `ruff check`, `pytest` and `ty` as gates.
