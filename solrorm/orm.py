#  Copyright 2020 University of Luxembourg
#
#  Licensed under the Apache License, Version 2.0 (the "License");
#  you may not use this file except in compliance with the License.
#  You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
#  Unless required by applicable law or agreed to in writing, software
#  distributed under the License is distributed on an "AS IS" BASIS,
#  WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#  See the License for the specific language governing permissions and
#  limitations under the License.

"""
 solrorm.orm
 -----------

Module containing the following classes:
  - SolrORM: update and create solr fields using the solr api
  - SolrQuery: base class to query solr

"""

import base64
import json
import logging
import re
from collections.abc import Iterator
from datetime import date, datetime, timezone
from typing import (
    Any,
    Generic,
    TypeVar,
    cast,
)

import pysolr
import requests
from pysolr import Solr
from pysolr import SolrError as PysolrError
from requests import HTTPError

from .config import Settings
from .entity import SolrEntity, _parse_solr_datetime, _parse_solr_json
from .exceptions import SolrQueryException
from .facets import Facet, FacetRange
from .fields import (
    SolrBinaryField,
    SolrDateTimeField,
    SolrField,
    SolrForeignKeyField,
    SolrJsonField,
)
from .schema import SolrSchemaAdmin


def fuzzy_search_suffix(settings: Settings) -> str:
    """Suffix appended to a query term to enable fuzzy search.

    @param settings: the configuration of the ORM issuing the query
    @return: the solr fuzziness suffix, e.g. C{~4}
    """
    return f"~{settings.fuzzy_search_level}"


# The Lucene query-syntax special characters, plus whitespace: any of these in a
# caller-supplied value would otherwise change the meaning of the query it is
# interpolated into (or make it unparseable).
_SOLR_SPECIAL_CHARACTERS = re.compile(r'([+\-&|!(){}\[\]^"~*?:\\/\s])')


def escape_solr_value(value: Any) -> str:
    """Backslash-escape a value so that solr reads it as a literal.

    Use this for every caller-supplied value interpolated into solr query
    syntax -- identifiers, ids, slugs and facet values. It must I{not} be
    applied to a whole query string: that is solr syntax by contract and
    escaping it would neutralise the operators the caller wrote.

    @param value: the value to escape, coerced to a string
    @return: the escaped value
    """
    return _SOLR_SPECIAL_CHARACTERS.sub(r"\\\1", str(value))


BATCH_SIZE = 500

logger = logging.getLogger(__name__)

__author__ = "Valentin Grouès"

E = TypeVar("E", bound=SolrEntity)


class SolrResults(pysolr.Results):
    """
    The results of a solr search, plus what solrorm attaches to them.

    pysolr returns a plain C{Results}; L{SolrQuery.search} adds the entities it
    built from the documents and whether another page is expected. This subclass
    exists so that both are part of the declared return type -- solrorm never
    instantiates it.

    @ivar entities: the SolrEntity instances built from the returned documents
    @ivar has_more: whether solr reported at least a full page of results
    """

    entities: list[Any]
    has_more: bool


class SolrQuery(Generic[E]):
    """
    Class to handle search and retrieval of entities from Solr

    Parameterized by the entity class it queries, so that C{get}, C{all} and
    friends are typed with the entity a host declared rather than with the base
    class.
    """

    # The sort options that will be offered on the search page
    SORT_OPTIONS: list[str] = []
    # The sort options labels that will be offered on the search page
    SORT_LABELS: list[str] = []
    # default sort option
    DEFAULT_SORT = ""
    # default sort order
    DEFAULT_SORT_ORDER = "asc"
    # allows giving more weight to some fields than others for default search
    BOOST: str | None = None

    def __init__(self, class_object: type[E], solr_orm: "SolrORM") -> None:
        """
        Initialize a SolrQuery instance setting the SolrEntity class and the SolrORM instance
        @param class_object: SolrEntity class indicating which entity we are searching or retrieving
        @param solr_orm: SolrORM instance holding the solr connection
        """
        self.class_object = class_object
        self.entity_name = class_object.__name__.lower()
        self.solr_orm = solr_orm
        self.cursor_enabled = solr_orm.settings.use_cursor_pagination

    def query_has_solr_query_field(self, query: str) -> bool:
        """
        Check if the given query has a valid Solr query field preceding the ':'

        @param query: the query string to check
        @return: True if the query has a valid Solr query field, False otherwise
        """
        parts = query.split("_")

        # Check if there are at least two parts after splitting
        if len(parts) >= 2:
            # Check if the first part before "_" is equal to entity_name
            if parts[0] == self.entity_name:
                second_part = parts[1].split(":")
                solr_query_fields_all = self.class_object._solr_fields
                solr_query_fields = [
                    key for key, value in solr_query_fields_all.items() if value.indexed
                ]
                if not solr_query_fields:
                    solr_query_fields = self.solr_orm.DEFAULT_QUERY_FIELDS
                # Check if the second part (after "_") is in solr_query_fields
                if len(second_part) >= 2 and second_part[0] in solr_query_fields:
                    return True
        return False

    def search_holding_entities(
        self, target_entity_id: str, field_name: str, source_entity_type: str
    ) -> SolrResults:
        """
        The entities of another type whose foreign key points at this entity.

        @param target_entity_id: id of the entity being pointed at
        @param field_name: name of the foreign key field
        @param source_entity_type: lowercase name of the entity holding the key
        @return: the results, with the built entities attached
        """
        params = {
            "fq": [
                f'type:"{escape_solr_value(source_entity_type)}"',
                f'{escape_solr_value(source_entity_type)}_{escape_solr_value(field_name)}:"{escape_solr_value(target_entity_id)}"',
            ]
        }
        results = cast(SolrResults, self.solr_orm.indexer.search("*:*", **params))
        entities = []
        for doc in results.docs:
            entity = self._build_instance(doc)
            entities.append(entity)
        results.entities = entities
        return results

    def format_field_name_with_order(self, field_name: str) -> str:
        """
        Prefix a sort clause with the entity name, unless it is collection-wide.

        @param field_name: a sort clause, e.g. C{title asc}
        @return: the clause with the entity prefix added, C{id} and C{score}
            left as they are
        """
        if field_name.split(" ")[0] in ["id", "score"]:
            return field_name
        else:
            return f"{self.entity_name}_{field_name}"

    def search(
        self,
        query: str,
        rows: int | None = 50,
        start: int = 0,
        sort: str | None = DEFAULT_SORT,
        sort_order: str = "desc",
        fq: list[str] | None = None,
        facets: list[Facet] | None = None,
        fuzzy: bool = False,
        edismax: bool = False,
        bq: str | None = None,
        sorts: list[str] | None = None,
        cursor: str | None = None,
    ) -> SolrResults:
        """
        Execute a solr search
        @param query: solr query string. It is passed through B{unescaped} -- it
        is solr syntax by contract, so operators the caller writes keep working
        and untrusted input must not be interpolated into it. Everything else
        interpolated around it (field prefixes, facet values) I{is} escaped with
        L{escape_solr_value}.
        @param rows: maximum number of results to return, default to 50
        @param start: used for pagination of the results, default to 0
        @param sort: field to sort on, default to DEFAULT_SORT class attribute
        @param sort_order: sort order, desc or asc, default to desc
        @param fq: list of specific filters to apply.
        See https://lucene.apache.org/solr/guide/8_4/common-query-parameters.html#fq-filter-query-parameter
        @param facets: list of facets to retrieve
        @param fuzzy: boolean triggering fuzzy search to be active or not
        @param edismax: use solr's extended dismax query parser
        @param bq: boost query applied on top of the entity's boost expression
        @param sorts: list of field names to sort on, in order, taking
        precedence over C{sort}
        @param cursor: cursor mark for deep pagination
        @return: the search results, carrying the built C{entities} and the
        C{has_more} flag
        """
        if sort_order or sort:  # string to sort using sort_order
            order = sort_order or "desc"
            if sort:
                sort_with_order = sort + " " + order
            else:
                sort_with_order = "score " + order
        else:
            sort_with_order = ""
        if sorts:  # list of fields to sort in order
            sort_with_order = ", ".join(
                [self.format_field_name_with_order(sort) for sort in sorts]
            )

        cursor_mark = None
        if self.cursor_enabled:
            cursor_mark = cursor or "*"
            if sort_with_order:
                if not re.search(r"\bid (asc|desc)", sort_with_order):
                    sort_with_order += ", id asc"
            else:
                sort_with_order = "id asc"

        if fq is None:
            fq = []
        params: dict[str, Any] = {
            "sort": sort_with_order,
            "defType": "edismax",
            "qf": self.BOOST,
            "fq": fq,
            "bq": bq,
        }

        query = query.strip()
        q = "*:*"
        if query and not query == "*:*":
            if ":" in query and self.query_has_solr_query_field(
                query
            ):  # for queries like "dataset_disease:*corona*"
                fq.append(query)
            else:
                entity_name = escape_solr_value(self.entity_name)
                if fuzzy:
                    fuzzy_terms = f"OR {entity_name}_textfuzzy_:{query}{fuzzy_search_suffix(self.solr_orm.settings)}"
                    query = f"({entity_name}_text_:'{query}' {fuzzy_terms})"
                else:
                    if edismax:
                        pattern = query
                    else:
                        pattern = "{}_text_:'{}'"
                    query = pattern.format(entity_name, query)

                if (
                    "score" in sort_with_order
                ):  # If sort has 'score' add to “scoring” query 'q'
                    q = query
                else:
                    fq.append(query)
        if rows:
            params["rows"] = rows
        if self.cursor_enabled:
            params["cursorMark"] = cursor_mark
        elif start:
            params["start"] = start

        if facets:
            params["facet"] = "on"
            params["facet.field"] = []
            params["facet.range"] = []
            for facet in facets:
                if isinstance(facet, FacetRange):
                    params[
                        f"f.{self.entity_name}_{facet.field_name}.facet.range.start"
                    ] = facet.range.start
                    params[
                        f"f.{self.entity_name}_{facet.field_name}.facet.range.end"
                    ] = facet.range.end
                    params[
                        f"f.{self.entity_name}_{facet.field_name}.facet.range.gap"
                    ] = facet.range.gap
                    params[
                        f"f.{self.entity_name}_{facet.field_name}.facet.range.other"
                    ] = facet.range.other
                    params["facet.range"].append(
                        f"{self.entity_name}_{facet.field_name}"
                    )
                else:
                    params["facet.field"].append(
                        f"{self.entity_name}_{facet.field_name}"
                    )
                # the selected values are caller data, so they are escaped and
                # quoted the same way for both facet kinds
                for value in facet.values:
                    fq.append(
                        f'{escape_solr_value(self.entity_name)}_{escape_solr_value(facet.field_name)}:"{escape_solr_value(value)}"'
                    )
        try:
            results = cast(SolrResults, self.solr_orm.indexer.search(q, **params))
            entities = []
            for doc in results.docs:
                entity = self._build_instance(doc)
                entities.append(entity)
            results.entities = entities
            # no row limit means solr returned everything it had, so there is
            # nothing further to page to
            results.has_more = bool(rows) and len(results.docs) >= rows

            # replace facets fields name to remove prefix
            facet_fields = results.facets.get("facet_fields")
            new_facets_fields = {}
            if facet_fields:
                for field_name, facet_value in facet_fields.items():
                    start_index = len(self.entity_name + "_")
                    new_facets_fields[field_name[start_index:]] = facet_value
                results.facets["facet_fields"] = new_facets_fields
        except PysolrError as e:
            raise SolrQueryException(e) from e
        return results

    def get_default_sort(self, query: str) -> tuple[str | None, str | None]:
        """
        For a given query, return the default
        sort attribute and order as a tuple.
        If query is not empty, we want to sort by sort by relevance
         of the search results, descending order.
        If query is empty, sort by default sort attribute (self.DEFAULT_SORT)
        @param query: query string
        @return: sort attribute and order
        """
        if query:
            return "", "desc"
        elif isinstance(self.DEFAULT_SORT, str):
            return self.entity_name + "_" + self.DEFAULT_SORT, self.DEFAULT_SORT_ORDER
        else:
            return None, None

    def get_facets(self, facet_list: list[tuple[str, str]]) -> dict[str, Facet]:
        """
        Build Facet instances from a list of attributes and facet labels
        @param facet_list: a list containing tuples with field name and facet label
        @return: the Facet instances, by attribute name
        """
        facets = {}
        for attribute_name, label in facet_list:
            solr_field = self.class_object._solr_fields.get(attribute_name, None)
            if solr_field is not None:
                if attribute_name == "deprecated":
                    facets[attribute_name] = Facet(solr_field.name, label, ["Active"])
                else:
                    facets[attribute_name] = Facet(solr_field.name, label)
        return facets

    def get_sort_options(self) -> tuple[list[str], list[str]]:
        """
        Returns a tuple where the first element is the list of sorting options and the second element
        is a list of the corresponding labels
        @return: tuple
        """
        options = self.SORT_OPTIONS
        prefix = self.class_object.__name__.lower()
        options_with_prefix = [
            prefix + "_" + option if option != "id" else "id" for option in options
        ]
        return options_with_prefix, getattr(self, "SORT_LABELS", [])

    def get(self, entity_id: str) -> E | None:
        """
        Retrieve from solr and build a SolrEntity instance for a given entity id
        @param entity_id: id of the entity to retrieve from solr
        @return: a self.class_object instance or None if not found
        """
        if getattr(self.class_object, "ADD_PREFIX_ID", True):
            entity_id_query = f"{self.entity_name}_{entity_id}"
        else:
            entity_id_query = entity_id
        results = self.solr_orm.indexer.search(
            q=f'id:"{escape_solr_value(entity_id_query)}"', rows=1
        )
        if results.hits == 0:
            return None
        doc = results.docs[0]
        new_instance = self._build_instance(doc)
        return new_instance

    def get_by_slug(self, slug: str) -> E | None:
        """
        Retrieve from solr and build a SolrEntity instance for a given entity slug
        @param slug: slug of the entity to retrieve from solr
        @return: a self.class_object instance or None if not found
        """

        results = self.solr_orm.indexer.search(
            q=f'{escape_solr_value(self.entity_name)}_slugs:"{escape_solr_value(slug)}"',
            rows=1,
        )
        if results.hits == 0:
            return None
        doc = results.docs[0]
        new_instance = self._build_instance(doc)
        return new_instance

    def _build_instance(self, doc: dict[str, Any]) -> E:
        """
        Build an entity instance from a solr document.

        Decodes what solr does not return as a Python value -- datetimes, JSON
        fields and binary blobs -- with the same helpers
        L{SolrEntity.from_json} uses, and strips the entity prefix off the id.

        @param doc: one document as returned by solr, keys prefixed
        @return: an instance of the entity class this query is bound to
        """
        new_instance = self.class_object()
        for attribute_name, field in self.class_object._solr_fields.items():
            solr_value = doc.get(self.entity_name + "_" + field.name, None)
            if solr_value is not None and isinstance(field, SolrDateTimeField):
                solr_value = _parse_solr_datetime(solr_value)
            elif solr_value is not None and isinstance(field, SolrJsonField):
                solr_value = _parse_solr_json(solr_value, field.model)
            elif solr_value is not None and isinstance(field, SolrBinaryField):
                solr_value = base64.b64decode(solr_value)
            setattr(new_instance, attribute_name, solr_value)
        doc_id = doc.get("id", None)
        # remove prefix from id (entity_name_)
        if doc_id and new_instance.ADD_PREFIX_ID:
            start_index = len(self.entity_name) + 1
            doc_id = doc_id[start_index:]
        new_instance.id = doc_id
        return new_instance

    def count(self) -> int:
        """
        Total number of entities from solr
        @return: total count of entities as an integer
        """
        results = self.solr_orm.indexer.search(
            q="type:" + self.entity_name, fl="numFound"
        )
        return results.hits

    def delete(self, query: str, commit: bool = False) -> None:
        """
        Delete entities from solr
        @param query: solr query syntax selecting the entities to delete. It is
        passed through B{unescaped} -- it is a query, not a value -- so never
        build it by interpolating untrusted input.
        @param commit: trigger a solr commit once the deletion is issued
        """
        self.solr_orm.indexer.delete(
            q=f"{query} AND type:{escape_solr_value(self.entity_name)}"
        )
        if commit:
            self.solr_orm.indexer.commit()

    def _iter_pages(self, **params: Any) -> Iterator[pysolr.Results]:
        """
        Page through every entity of this type with a solr cursor.

        @param params: extra search parameters, e.g. C{fl}
        @return: a generator yielding one pysolr.Results per page
        """
        next_cursor = "*"
        cursor = None
        while next_cursor != cursor:
            cursor = next_cursor
            results = self.solr_orm.indexer.search(
                q="type:" + self.entity_name,
                cursorMark=cursor,
                rows=BATCH_SIZE,
                sort="id asc",
                **params,
            )
            next_cursor = results.nextCursorMark
            yield results

    def all(self) -> Iterator[E]:
        """
        Retrieve from solr all the entities of the underlying SolrEntity as defined by self.class_object
        @return: a generator with solr entities
        """
        for results in self._iter_pages():
            for result in results:
                yield self._build_instance(result)

    def all_ids(self) -> list[str]:
        """
        Retrieve from solr all the entity ids of the underlying SolrEntity as defined by self.class_object

        Pages with a cursor like L{all} rather than asking solr for one
        enormous page.
        @return: a list of entity ids, with the entity prefix stripped off
        """
        if self.class_object.ADD_PREFIX_ID:
            start_index = len(self.entity_name) + 1
        else:
            start_index = 0
        return [
            doc["id"][start_index:]
            for results in self._iter_pages(fl="id")
            for doc in results.docs
        ]


class SolrAutomaticQuery(SolrQuery[E]):
    """
    A SolrQuery resolving its sort and boost settings from the configuration.

    Everything the class attributes of L{SolrQuery} declare as a default is
    resolved per entity when the query object is built -- from
    C{Settings.boost} and C{Settings.default_sort} -- and stored on the
    instance, so two entities never see each other's values.
    """

    def __init__(self, class_object: type[E], solr_orm: "SolrORM") -> None:
        """
        Initialize a SolrQuery instance setting the SolrEntity class and the SolrORM instance
        @param class_object: SolrEntity class indicating which entity we are searching or retrieving
        @param solr_orm: SolrORM instance holding the solr connection
        """
        super().__init__(class_object, solr_orm)
        self.entity_name = class_object.__name__.lower()
        # the class attributes are the declared defaults; everything resolved here
        # is per-instance, so two entities never share each other's settings
        if not self.SORT_OPTIONS:
            self.SORT_OPTIONS = ["title", "id"]
        # labels of the sort options that will be offered on the search page
        if not self.SORT_LABELS:
            self.SORT_LABELS = ["title", "id"]
        # allows giving more weight to some fields than others for default search
        if not self.BOOST:
            boost = solr_orm.settings.boost.get(self.entity_name)
            self.BOOST = (
                boost or f"{self.entity_name}_title^5 {self.entity_name}_text_^1"
            )
        # default sort option
        if not self.DEFAULT_SORT:
            default_sort = solr_orm.settings.default_sort.get(self.entity_name)
            self.DEFAULT_SORT = default_sort or "title"


def _encode_solr_json_value(value):
    """Serialize date/datetime to Solr ``pdate`` (UTC, ``Z``-suffixed)."""
    if isinstance(value, datetime):
        if value.utcoffset() is not None:
            value = value.astimezone(timezone.utc).replace(tzinfo=None)
        return value.isoformat(timespec="milliseconds") + "Z"
    if isinstance(value, date):
        return f"{value.isoformat()}T00:00:00Z"
    raise TypeError(f"{type(value).__name__} is not JSON serializable")


_SOLR_JSON_ENCODER = json.JSONEncoder(default=_encode_solr_json_value)


class SolrORM:
    """
    Class abstracting access to solr api to create, update and delete solr fields
    """

    # default field to use for default search
    DEFAULT_QUERY_FIELDS = ["title"]

    # The three per-entity catch-all fields every entity gets, as
    # (suffix, field type, stored). The query fields of the entity are copied
    # into each of them at index time.
    CATCH_ALL_FIELDS = (
        ("_text_", "text_en", False),
        ("_textfuzzy_", "text_en_splitting_tight", False),
        ("_autocomplete_text_", "autocomplete_text", True),
    )

    # Collection-global field type backing the _autocomplete_text_ fields: a
    # whole-value tokenizer, so that a prefix query matches from the start of the
    # field rather than from the start of any of its words.
    AUTOCOMPLETE_FIELD_TYPE_NAME = "autocomplete_text"
    AUTOCOMPLETE_FIELD_TYPE = {
        "name": AUTOCOMPLETE_FIELD_TYPE_NAME,
        "class": "solr.TextField",
        "positionIncrementGap": "100",
        "analyzer": {
            "tokenizer": {"class": "solr.KeywordTokenizerFactory"},
            "filters": [{"class": "solr.LowerCaseFilterFactory"}],
        },
    }

    def __init__(self, settings: Settings) -> None:
        """
        Initialize a SolrORM instance from a Settings object.

        The settings are read eagerly, so ``settings.entities`` must already
        list every entity the ORM should know about.

        @param settings: the configuration to serve this collection with
        """
        self.settings = settings
        url = settings.endpoint
        collection = settings.collection
        self.url = url
        self.collection = collection
        self.indexer = Solr(f"{url}/{collection}", encoder=_SOLR_JSON_ENCODER)
        self.indexer_schema = SolrSchemaAdmin(f"{self.url}/{collection}/schema")
        logger.info(
            "Initializing SolrORM with solr url %s and collection %s", url, collection
        )

        SolrEntity._solr_orm = self

        # we loop over solr entity subclasses to set some internal variables
        # for each solrEntity subclass, _solr_fields will contain a list of solr fields
        # query will contain a SolrQuery instance or one of its subclasses instance as defined in the  query_class
        # attribute of each solrEntity subclass
        for entity_class in SolrEntity.__subclasses__():
            entity_class.reversed_field = {}
        for entity_class in SolrEntity.__subclasses__():
            if not hasattr(entity_class, "_solr_fields"):
                entity_class._solr_fields = self.get_fields_for_class(entity_class)
            for field in entity_class._solr_fields.values():
                # we record of solrforeignkeyfield having reversed_by attributes in the target entity
                if isinstance(field, SolrForeignKeyField) and field.reversed_by:
                    reversed_attributes = field.reversed_by
                    target_entity_class = self.settings.entities.get(
                        field.linked_entity_name
                    )
                    if target_entity_class:
                        source_entity_class_name = entity_class.__name__.lower()
                        target_entity_class.reversed_field[reversed_attributes] = (
                            source_entity_class_name,
                            field.name,
                            field.reversed_multiple,
                        )

            if hasattr(entity_class, "query_class"):
                entity_class.query = entity_class.query_class(entity_class, self)
            else:
                entity_class.query = SolrQuery(entity_class, self)

    def missing_fields(self, entity_name: str) -> list[str]:
        """
        Solr fields required by an entity but absent from the schema.

        Reports the state of the schema without prescribing a remedy: it is up
        to the calling application to decide what to do (and to name whichever
        of its own commands recreates the schema).

        @param entity_name: name of the entity to check, e.g. dataset
        @return: the names of the missing Solr fields, empty if the schema is
            complete. Raises KeyError if entity_name is not a known entity.
        """
        entity_class = self.settings.entities[entity_name.lower()]
        if entity_class.__name__.lower() != entity_name.lower() or not hasattr(
            entity_class, "_solr_fields"
        ):
            logger.warning(
                "Cannot check the schema of '%s': it is registered under a "
                "different name or its fields were never collected.",
                entity_name,
            )
            return []
        missing = []
        for field in entity_class._solr_fields.values():
            solr_field_name = f"{entity_name.lower()}_{field.name}"
            if not self.indexer_schema.field_exists(solr_field_name):
                missing.append(solr_field_name)
        if missing:
            logger.debug(
                "Entity '%s': %d field(s) missing from the Solr schema: %s",
                entity_name,
                len(missing),
                ", ".join(missing),
            )
        return missing

    def check_schema(self, entity_name: str) -> bool:
        """
        Check for missing fields for each entity

        @param entity_name: name of the entity to check, e.g. dataset
        @return: True if the schema holds every field the entity declares.
            Prefer L{missing_fields} when the caller wants to report *which*
            fields are missing.
        """
        try:
            return not self.missing_fields(entity_name)
        except KeyError as e:
            logger.error("Unknown entity %s", e)
            return False

    def check_fields_existence(self) -> bool:
        """
        Whether the schema already holds a field of any registered entity.

        Hosts use it before creating the schema, to decide whether the existing
        fields should be deleted first.
        @return: True if at least one field is named after a registered entity
        """
        prefixes = tuple(self.settings.entities)
        if not prefixes:
            return False
        return any(
            field_name.startswith(prefixes)
            for field_name in self.indexer_schema.fields()
        )

    def mismatched_fields(self, entity_name: str) -> list[tuple[str, str, str]]:
        """
        Fields whose type in the solr schema differs from the entity's.

        Like L{missing_fields}, this reports the state of the schema without
        prescribing a remedy: the calling application decides what to do about
        it. Fields absent from the schema are skipped -- use L{missing_fields}
        to detect those.

        @param entity_name: name of the entity to check, e.g. dataset
        @return: one (solr_field_name, expected_type, actual_type) tuple per
            mismatching field, empty if every field type matches.
            Raises KeyError if entity_name is not a known entity.
        """
        entity_class = self.settings.entities[entity_name]
        mismatches = []
        for field in entity_class._solr_fields.values():
            solr_field_name = f"{entity_name.lower()}_{field.name}"
            actual_type = self.indexer_schema.field_type(solr_field_name)
            if actual_type is None:
                # not in the schema at all; missing_fields() reports on it
                continue
            if actual_type != field.type:
                mismatches.append((solr_field_name, field.type, actual_type))
        if mismatches:
            logger.debug(
                "Entity '%s': %d field(s) with a type mismatch in the solr schema: %s",
                entity_name,
                len(mismatches),
                ", ".join(
                    f"{name} (expected {expected}, got {actual})"
                    for name, expected, actual in mismatches
                ),
            )
        return mismatches

    def field_type_mismatch(self, entity_name: str) -> bool:
        """
        Check whether any field type differs between the schema and the entity

        @param entity_name: name of the entity to check, e.g. dataset
        @return: True if at least one field type differs. Prefer
            L{mismatched_fields} when the caller wants to report *which* fields
            mismatch.
        """
        try:
            return bool(self.mismatched_fields(entity_name))
        except KeyError as e:
            logger.error("Unknown entity %s", e)
            return False

    def create_fields(self) -> None:
        """
        Create the solr fields of every registered entity.

        Idempotent: a field, field type or copy field directive that is already
        in the schema is left as it is, so running this against a populated
        collection neither drops the catch-all fields nor forces a reindex.
        Whatever solr refuses is logged and the remaining fields are still
        attempted.
        """
        logger.info("Creating solr fields")
        self._create_or_update_fields(update=False)

    def update_fields(self) -> None:
        """
        Replace the definition of the solr fields of every registered entity.

        The catch-all fields and copy field directives are treated as in
        L{create_fields}: added when absent, left alone otherwise.
        """
        logger.info("Updating solr fields")
        self._create_or_update_fields(update=True)

    def delete_fields(self) -> None:
        """
        Delete the solr fields of every registered entity.
        """
        logger.info("Deleting solr fields")
        for solr_entity_class in self.settings.entities.values():
            self._collect_fields(solr_entity_class)
            self._delete_fields_for_class(solr_entity_class)
        try:
            self.indexer_schema.delete_field("type")
        except HTTPError as e:
            logger.debug(e)

    def _collect_fields(self, solr_entity_class: type[SolrEntity]) -> None:
        """
        Make sure an entity class carries its collected solr fields.

        @param solr_entity_class: SolrEntity subclass
        """
        if not hasattr(solr_entity_class, "_solr_fields"):
            solr_entity_class._solr_fields = self.get_fields_for_class(
                solr_entity_class
            )

    def _create_or_update_fields(self, update: bool = False) -> None:
        """
        Build the schema of every registered entity.

        Creates what the whole collection shares -- the C{type} discriminator
        and the C{autocomplete_text} field type -- then delegates each entity to
        L{_create_or_update_fields_for_class}, handing it the copy field
        directives already in the schema so they are read only once.

        @param update: replace each entity's own fields rather than adding them
        """
        if not self.indexer_schema.field_exists("type"):
            try:
                self.indexer_schema.create_field(
                    "type", "string", index=True, store=True, multivalued=False
                )
            except HTTPError as e:
                logger.warning("could not create the type field: %s", e)
        # the field type backing every entity's autocomplete field is
        # collection-global, so it is created once and not per entity
        if not self.indexer_schema.field_type_exists(self.AUTOCOMPLETE_FIELD_TYPE_NAME):
            self.indexer_schema.create_field_type(self.AUTOCOMPLETE_FIELD_TYPE)
        existing_copy_fields = {
            (directive["source"], directive["dest"])
            for directive in self.indexer_schema.copy_fields()
        }
        for solr_entity_class in self.settings.entities.values():
            logger.debug(solr_entity_class)
            self._collect_fields(solr_entity_class)
            self._create_or_update_fields_for_class(
                solr_entity_class, update, existing_copy_fields
            )
        logger.debug("done")

    def get_fields_for_class(
        self, solr_entity_class: type[SolrEntity]
    ) -> dict[str, SolrField]:
        """
        For a specific SolrEntity subclass, returns a dict where keys are
        the attributes names and values are the SolrField instances
        @param solr_entity_class: SolrEntity subclass
        @return: the dict with attributes and corresponding solr fields
        """
        attributes = dict()
        self._find_fields(solr_entity_class, attributes)
        return attributes

    def _find_fields(
        self, solr_entity_class: type, attributes: dict[str, SolrField]
    ) -> None:
        """
        Collect the solr fields a class declares, inherited ones included.

        The bases are walked I{first} so that a subclass redeclaring an
        inherited field -- C{created} with C{indexed=False}, say -- overrides it
        rather than being silently overridden by it.

        @param solr_entity_class: the class to collect the fields of
        @param attributes: the mapping to collect into, attribute name -> field
        """
        for superclass in solr_entity_class.__bases__:
            if superclass is not object:
                self._find_fields(superclass, attributes)
        for name, value in solr_entity_class.__dict__.items():
            if isinstance(value, SolrField):
                attributes[name] = value

    def query_fields_for_entity(self, entity_name: str) -> list[str]:
        """
        The solr fields copied into an entity's catch-all search fields.

        @param entity_name: lowercase name of the entity, e.g. dataset
        @return: the field names the host listed for this entity in
            C{Settings.query_text_field}, or L{DEFAULT_QUERY_FIELDS} if it
            listed none
        """
        return self.settings.query_text_field.get(entity_name) or list(
            self.DEFAULT_QUERY_FIELDS
        )

    def _create_or_update_fields_for_class(
        self,
        solr_entity_class: type[SolrEntity],
        update: bool,
        existing_copy_fields: set[tuple[str, str]] | None = None,
    ) -> None:
        """
        Create or update the solr fields of one entity.

        Adding is idempotent: the catch-all fields and their copy field
        directives are created only when the schema does not already hold them,
        so indexed content is never discarded. Solr's refusals are logged and
        the remaining fields are still attempted.

        @param solr_entity_class: the SolrEntity subclass to build the schema of
        @param update: replace the definition of the entity's own fields rather
            than adding them
        @param existing_copy_fields: the C{(source, dest)} pairs already in the
            schema, so that a run over several entities lists them once. Read
            from solr when not given.
        """
        fields = solr_entity_class._solr_fields
        entity_name = solr_entity_class.__name__.lower()
        if existing_copy_fields is None:
            existing_copy_fields = {
                (directive["source"], directive["dest"])
                for directive in self.indexer_schema.copy_fields()
            }
        # "id" is the one source shared by every entity, so it is not prefixed
        sources = [
            source if source == "id" else f"{entity_name}_{source}"
            for source in self.query_fields_for_entity(entity_name)
        ]

        for field in fields.values():
            solr_field_name = f"{entity_name}_{field.name}"
            try:
                if update:
                    self.indexer_schema.update_field(
                        solr_field_name,
                        field.type,
                        field.indexed,
                        field.stored,
                        field.multivalued,
                    )
                elif not self.indexer_schema.field_exists(solr_field_name):
                    self.indexer_schema.create_field(
                        solr_field_name,
                        field.type,
                        field.indexed,
                        field.stored,
                        field.multivalued,
                    )
            except HTTPError as e:
                # one field solr will not have is no reason to abandon the rest
                logger.warning("could not write field %s: %s", solr_field_name, e)

        for suffix, field_type, stored in self.CATCH_ALL_FIELDS:
            catch_all_name = f"{entity_name}{suffix}"
            if not self.indexer_schema.field_exists(catch_all_name):
                try:
                    self.indexer_schema.create_field(
                        catch_all_name,
                        field_type,
                        index=True,
                        store=stored,
                        multivalued=True,
                    )
                except HTTPError as e:
                    logger.warning("could not create field %s: %s", catch_all_name, e)
                    continue
            for source in sources:
                if (source, catch_all_name) in existing_copy_fields:
                    continue
                if self.indexer_schema.add_copy_field(source, catch_all_name):
                    existing_copy_fields.add((source, catch_all_name))

    def add(self, entity_dict: dict) -> str:
        """
        Add an entity to the solr index
        Beware that this method doesn't trigger a commit
        @param entity_dict: a representation of a SolrEntity as a dict
        @return: a string containing the response body from solr
        """
        return self.indexer.add([entity_dict])

    def delete(self, entity_id: str | None = None, query: str | None = None) -> str:
        """
        Delete entities from the solr index
        Beware that this method doesn't trigger a commit
        @param entity_id: id of the SolrEntity to delete
        @param query: solr query syntax selecting the entities to delete. It is
            passed through B{unescaped} -- it is a query, not a value -- so never
            build it by interpolating untrusted input.
        @return: a string containing the response body from solr
        @raise ValueError: unless exactly one of entity_id and query is given
        """
        if (entity_id is None) == (query is None):
            raise ValueError("pass exactly one of entity_id and query")
        return self.indexer.delete(id=entity_id, q=query)

    def commit(self, soft_commit: bool = False) -> str:
        """
        Triggers a solr commit
        @param soft_commit: if true, only a soft commit will be triggered
        @return: a string containing the response body from solr
        """
        logger.debug("Solr %scommit", "soft " if soft_commit else "")

        return self.indexer.commit(softCommit=soft_commit)

    def _delete_copy_fields_for_class(self, entity_name: str) -> None:
        """
        Delete every copy field directive targeting this entity's text fields.

        The directives are read back from the live schema rather than derived
        from the configuration: applications may add copy fields of their own
        (from an extended list of query fields, for instance), and a directive
        left behind makes its source field undeletable.

        @param entity_name: lowercase name of the entity, e.g. dataset
        """
        directives = [
            directive
            for directive in self.indexer_schema.copy_fields()
            if directive["dest"].startswith(f"{entity_name}_")
        ]
        self.indexer_schema.delete_copy_fields(directives)

    def _delete_fields_for_class(self, entity_class: type[SolrEntity]) -> None:
        """
        Delete one entity's copy field directives, catch-all fields and fields.

        In that order: solr refuses to delete a field a directive still copies
        from. Fields it will not delete are logged and the rest are still
        attempted.

        @param entity_class: the SolrEntity subclass to remove from the schema
        """
        fields = entity_class._solr_fields
        entity_name = entity_class.__name__.lower()
        self._delete_copy_fields_for_class(entity_name)
        self.indexer_schema.delete_fields(
            [
                f"{entity_name}{suffix}"
                for suffix, _type, _stored in self.CATCH_ALL_FIELDS
            ]
        )

        for field in fields.values():
            try:
                self.indexer_schema.delete_field(entity_name + "_" + field.name)
            except HTTPError as e:
                # the message carries solr's own explanation; a full traceback
                # per undeletable field would only bury it
                logger.warning("%s", e)

    def solr_config_update(self) -> None:
        """
        Register a suggester and a C{/suggest} request handler per entity.

        This is the only call that talks to solr's I{config} api rather than to
        the schema api, so it posts directly instead of going through
        L{SolrSchemaAdmin}.
        """
        headers = {"Content-type": "application/json"}
        params = {"commit": "true", "indent": "true"}

        suggesters = []
        for entity_name in self.settings.entities.keys():
            suggesters.append(
                {
                    "name": f"suggest_{entity_name}",
                    "lookupImpl": "AnalyzingInfixLookupFactory",
                    "field": f"{entity_name}_autocomplete_text_",
                    "suggestAnalyzerFieldType": "autocomplete_text",
                    "buildOnStartup": "false",
                    "highlight": "false",
                }
            )
        search_component = {
            "name": "suggest",
            "class": "solr.SuggestComponent",
            "suggester": suggesters,
        }

        request_handler = {
            "name": "/suggest",
            "class": "solr.SearchHandler",
            "startup": "lazy",
            "defaults": {"suggest": "true", "suggest.count": 10},
            "components": ["suggest"],
        }

        data_add_searchcomponent = {"add-searchcomponent": search_component}

        data_add_requesthandler = {"add-requesthandler": request_handler}
        response_add_search_component = requests.post(
            self.url + "/" + self.collection + "/config",
            headers=headers,
            params=params,
            data=json.dumps(data_add_searchcomponent),
        )
        response_add_request_handler = requests.post(
            self.url + "/" + self.collection + "/config",
            headers=headers,
            params=params,
            data=json.dumps(data_add_requesthandler),
        )

        # if the component already exists do an update
        if not response_add_search_component.status_code == 200:
            data_update_search_component = {"update-searchcomponent": search_component}
            requests.post(
                self.url + "/" + self.collection + "/config",
                headers=headers,
                params=params,
                data=json.dumps(data_update_search_component),
            )

        if not response_add_request_handler.status_code == 200:
            data_update_request_handler = {"update-requesthandler": request_handler}
            requests.post(
                self.url + "/" + self.collection + "/config",
                headers=headers,
                params=params,
                data=json.dumps(data_update_request_handler),
            )
