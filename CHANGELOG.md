# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project
adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.0] — unreleased

First packaged release. `solrorm` was extracted from the Data Catalogue, and
this entry is written for the two applications adopting it — the Data Catalogue
and PubChemLite. Everything below is a change against that extracted code, so
**every consumer needs the migration steps in "Breaking changes"**.

### Added

- `Settings` — a frozen dataclass in `solrorm.config` naming every option the
  library reads, with `Settings.from_mapping(mapping)` to build one from a
  host mapping using the old `SOLR_*` keys.
- `SolrEntityNotFound`, for hosts that want an exception rather than `None`
  from `SolrQuery.get()` / `get_by_slug()`.
- `escape_solr_value(value)` — backslash-escapes the Lucene special set;
  applied internally to every caller value the library interpolates.
- `SolrResults` — the `pysolr.Results` subclass returned by `search()` and
  `search_holding_entities()`, declaring the `entities` and `has_more`
  attributes those methods attach.
- `SolrSchemaAdmin` gained `fields`, `field_exists`, `field_type`,
  `field_type_exists`, `create_field_type`, `copy_fields`, `add_copy_field`,
  `delete_copy_fields` and `delete_fields`, so the ORM issues no schema
  request of its own.
- `SolrField` is a typed descriptor and `SolrQuery` is generic over its entity
  class, so `Widget.query.get(id)` is `Widget | None` to a type checker.
- `py.typed`: the package ships its annotations.
- A test suite (no reachable Solr required) and CI over Python 3.10–3.13
  running `ruff format`, `ruff check`, `pytest` and `ty` as gates.

### Breaking changes

- **Modules renamed** — drop the redundant `solr_orm_` prefix. No compatibility
  shims are provided.

  | Old | New |
  |---|---|
  | `solrorm.solr_orm` | `solrorm.orm` |
  | `solrorm.solr_orm_entity` | `solrorm.entity` |
  | `solrorm.solr_orm_fields` | `solrorm.fields` |
  | `solrorm.solr_orm_schema` | `solrorm.schema` |

  Every public name is re-exported from the package root, so prefer
  `from solrorm import SolrEntity, SolrField` and stop importing modules.

- **`solrorm.exceptions.SolrError` is renamed `SolrORMError`** (it collided
  with `pysolr.SolrError`). No alias is kept.

- **The global config singleton is gone.** `solrorm.config.config` and
  `solrorm.configure()` no longer exist. `SolrORM(settings)` is now the
  **only** constructor — the positional `SolrORM(url, collection)` form was
  removed. Hosts that were calling `configure(app.config)` now write:

  ```python
  from solrorm import Settings, SolrORM

  solr_orm = SolrORM(Settings.from_mapping(app.config))
  # or, with no host mapping:
  solr_orm = SolrORM(Settings(endpoint=..., collection=...))
  ```

- **`entities` is read eagerly.** The old `configure()` stored a *reference* to
  the host mapping, so an `entities` registry populated *after* `SolrORM(...)`
  was still seen. `Settings` copies it at construction, so the registry must be
  complete before the ORM is built. The same applies to `query_text_field`,
  which is deep-copied: mutating your own mapping afterwards no longer affects
  the library (and the library can no longer mutate yours).

- **`SolrSchemaAdmin(url, settings)` → `SolrSchemaAdmin(url)`.** The schema
  admin holds no configuration.

- **`SolrQuery.get_or_404` and `get_by_slug_or_404` are removed**, along with
  the `Flask` and `werkzeug` dependencies — a library must not be able to
  `abort()` its caller's request. In a request context, use:

  ```python
  entity = Dataset.query.get(entity_id)
  if entity is None:
      abort(404)
  ```

  Outside a request context, raise `SolrEntityNotFound` instead.

  Call sites to update — Data Catalogue:
  `datacatalog/controllers/api_entities.py:51,65`,
  `datacatalog/controllers/web_controllers.py:496` (`get_or_404`) and `:478`
  (`get_by_slug_or_404`), `datacatalog/exporter/dats_exporter.py:278,285,834`
  (not a request context — raise), plus 9 uses in
  `tests/exporter/test_dats_exporter.py`. PubChemLite:
  `pubchemlite/controllers.py:921`. (`imi-data-catalogue` vendors its own
  `solr_orm.py` and is unaffected.)

- **`SOLR_QUERY_SEARCH_EXTENDED` and `SOLR_QUERY_SEARCH_EXTENDED_2_WAY_INDEX`
  are removed.** The library no longer knows about `dataset`/`project`/`study`
  and ships no default query-field table; `Settings.query_text_field` is a
  plain `{entity_name: [field, ...]}` mapping, and an entity absent from it
  falls back to `SolrORM.DEFAULT_QUERY_FIELDS` (`["title"]`). The capability is
  unchanged — the host now lists the fields it wants copied into `_text_`.
  Translate as follows:

  | Old config | Equivalent explicit `query_text_field` |
  |---|---|
  | flags unset | `{"dataset": ["title"], "project": ["title"], "study": ["title"]}` |
  | `SEARCH_EXTENDED=True` | `{"dataset": ["title"], "project": ["title", "datasets_metadata", "studies_metadata"], "study": ["title", "datasets_metadata"]}` |
  | `SEARCH_EXTENDED=True` + `2_WAY_INDEX=True` | `{"dataset": ["title", "studies_metadata", "projects_metadata"], "project": ["title", "datasets_metadata", "studies_metadata"], "study": ["title", "datasets_metadata", "projects_metadata"]}` |

  Data Catalogue sets the flags in `datacatalog/settings.py.template:64,66` and
  `plugins/datacatalog-elixir-plugin/datacatalogelixir/settings.py:86,87`,
  alongside its own `SOLR_QUERY_TEXT_FIELD_EXTENDED` table. Its
  `connector/extend_entity_index.py` reads the flags *itself* to populate the
  `*_metadata` fields, so they stay meaningful in the host — what changes is
  only that the host must merge those field names into `SOLR_QUERY_TEXT_FIELD`.
  PubChemLite sets neither flag and is unaffected.

- **A selected facet range is a literal value, not a range expression.** The
  `FacetRange` `fq` branch is now quoted and escaped like the `Facet` one, so a
  host that passed `"[0 TO 25]"` as a facet value must pass the whole clause
  itself: `fq=["<entity>_<field>:[0 TO 25]"]`.

- **`SolrORM.delete` requires exactly one of `entity_id` or `query`** and
  raises `ValueError` otherwise; it previously nulled `query` silently. Its
  `query` parameter is a Solr query *string*, which is what it always passed to
  pysolr.

- **`create_fields()` is idempotent** and no longer deletes and recreates the
  `_text_`, `_textfuzzy_` and `_autocomplete_text_` catch-all fields on every
  run, so indexed content survives a re-run. `update_fields()` still replaces
  an entity's own fields and still requires a reindex.

- `SolrORM.BATCH_SIZE` is an `int` (was the string `"500"`).

### Fixed

- Every `FacetRange` query raised `TypeError` (`list.append` called with two
  arguments).
- `query_has_solr_query_field` raised `AttributeError` for an entity with no
  indexed fields (`DEFAULT_QUERY_FIELDS` is defined on `SolrORM`, not
  `SolrQuery`).
- `SolrAutomaticQuery` assigned its sort/boost settings to `self.__class__`, so
  the first entity constructed poisoned every other one; `search` also read the
  class-level `BOOST`. Both are per-instance now.
- `SolrEntity.from_json` never parsed datetimes (it matched `"date"`, while
  `SolrDateTimeField.type` is `"pdate"`), decoded binary fields with
  `b16decode` against `to_dict`'s `b64encode`, and dropped the underscores from
  reverse-relation attribute names (`data_use_entities` looked up `datause`).
  Datetime and JSON parsing are now shared with `_build_instance`, so
  `to_dict` → `from_json` round-trips datetimes, binary blobs and
  `SolrJsonField` values (with or without a `model`).
- Caller values interpolated into Lucene syntax are escaped (`get`,
  `get_by_slug`, facet `fq`, `search_holding_entities`, entity-name prefixes).
  The `query` argument of `search()` and `delete()` is documented as Solr query
  syntax and stays raw.
- Schema requests are checked: refusals are reported through `logger.warning`
  or raised as an `HTTPError` carrying Solr's own message, instead of being
  discarded or `print`ed. One refused field no longer abandons the rest.
- A subclass can override an inherited field — `_find_fields` walked the base
  classes *after* the class's own `__dict__`, so `SolrEntity.created` /
  `modified` won whatever a subclass declared.
- `all_ids()` pages with a cursor instead of asking for a million rows, and is
  annotated `list[str]`.
- `search()` no longer raises `TypeError` when `rows` is `0` or `None`.
- `check_fields_existence` returns a `bool`.
- Each `SolrEntity` subclass gets its own `reversed_field` mapping via
  `__init_subclass__`, rather than sharing (and relying on `SolrORM.__init__`
  resetting) one mutable class attribute.
- `Range.__init__` no longer shadows the `range` builtin with a dead
  assignment.
