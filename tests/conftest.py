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
 tests.conftest
 --------------

Shared fixtures. The unit tests must never need a reachable Solr: the ORM's
``indexer`` is replaced by L{FakeIndexer}, which records the calls it receives
and replays canned responses.
"""

from collections import deque

import pysolr
import pytest
import requests

from solrorm.config import Settings
from solrorm.entity import SolrEntity
from solrorm.fields import (
    SolrBinaryField,
    SolrDateTimeField,
    SolrField,
    SolrForeignKeyField,
    SolrIntField,
    SolrJsonField,
)
from solrorm.orm import SolrORM

# deliberately unroutable: a test that slips past the fake must fail, not hang
SOLR_ENDPOINT = "http://solr.invalid:8983/solr"
SOLR_COLLECTION = "test_collection"


def solr_response(docs=(), num_found=None, facets=None, next_cursor=None):
    """
    Build the decoded payload that pysolr.Results expects.

    @param docs: the documents the response carries
    @param num_found: reported hit count, defaults to the number of documents
    @param facets: value of the solr facet_counts section
    @param next_cursor: value of nextCursorMark, for cursor pagination
    @return: a dict shaped like a decoded solr response
    """
    decoded = {
        "response": {
            "docs": list(docs),
            "numFound": len(docs) if num_found is None else num_found,
        }
    }
    if facets is not None:
        decoded["facet_counts"] = facets
    if next_cursor is not None:
        decoded["nextCursorMark"] = next_cursor
    return decoded


class FakeIndexer:
    """
    Stand-in for the pysolr.Solr instance held by SolrORM.indexer.

    Records every call so tests can assert on the query solrorm built, and
    replays responses queued with L{queue} (an empty result set once the queue
    runs dry).
    """

    def __init__(self) -> None:
        self.searches = []
        self.added = []
        self.deleted = []
        self.commits = []
        self._responses = deque()

    def queue(self, *decoded):
        """Queue decoded responses, returned by successive searches."""
        self._responses.extend(decoded)
        return self

    @property
    def last_search(self):
        """The most recent search as a (q, params) tuple."""
        assert self.searches, "no search was issued"
        return self.searches[-1]

    def search(self, q="*:*", **params):
        self.searches.append((q, params))
        decoded = self._responses.popleft() if self._responses else solr_response()
        return pysolr.Results(decoded)

    def add(self, docs, **kwargs):
        self.added.append((docs, kwargs))
        return "{}"

    def delete(self, **kwargs):
        self.deleted.append(kwargs)
        return "{}"

    def commit(self, **kwargs):
        self.commits.append(kwargs)
        return "{}"


class FakeSchemaResponse:
    """The parts of a requests.Response the schema admin touches."""

    def __init__(self, status_code=200, payload=None, text=""):
        self.status_code = status_code
        self.ok = status_code < 400
        self.text = text
        self._payload = payload

    def json(self):
        if self._payload is None:
            raise ValueError("no json body")
        return self._payload

    def raise_for_status(self):
        if not self.ok:
            raise requests.HTTPError(str(self.status_code), response=self)


class FakeSchemaApi:
    """
    Stand-in for the solr schema api, backed by an in-memory schema.

    It answers the reads L{solrorm.schema.SolrSchemaAdmin} issues and applies the
    directives it posts, so a test can describe a schema that is empty, already
    complete, or partly there, and then assert on what solrorm did about it.
    Every posted directive is recorded in C{directives}.
    """

    def __init__(self, fields=None, field_types=(), copy_fields=()):
        # field name -> field type
        self.fields = dict(fields or {})
        self.field_types = set(field_types)
        self.copy_fields = [dict(directive) for directive in copy_fields]
        self.directives = []
        # field names solr should refuse to add, mapped to the reason it gives
        self.refuse = {}

    def install(self, monkeypatch):
        """Route requests' get and post through this fake."""
        monkeypatch.setattr(requests, "get", self.get)
        monkeypatch.setattr(requests, "post", self.post)
        return self

    def get(self, url, params=None, **kwargs):
        path = url.split("/schema", 1)[1]
        if path == "/copyfields":
            return FakeSchemaResponse(payload={"copyFields": self.copy_fields})
        if path == "/fields":
            return FakeSchemaResponse(
                payload={
                    "fields": [
                        {"name": name, "type": type_}
                        for name, type_ in self.fields.items()
                    ]
                }
            )
        for prefix, known in (
            ("/fields/", self.fields),
            ("/fieldtypes/", self.field_types),
        ):
            if path.startswith(prefix):
                name = path[len(prefix) :]
                if name not in known:
                    return FakeSchemaResponse(404, text=f"{name} not found")
                if prefix == "/fields/":
                    return FakeSchemaResponse(
                        payload={"field": {"name": name, "type": self.fields[name]}}
                    )
                return FakeSchemaResponse(payload={"fieldType": {"name": name}})
        raise AssertionError(f"unexpected schema read: {url}")

    def post(self, url, json=None, **kwargs):
        assert json is not None, "the schema api is driven with a json body"
        self.directives.append(json)
        for directive, body in json.items():
            handler = getattr(self, f"_{directive.replace('-', '_')}")
            error = handler(body)
            if error:
                return FakeSchemaResponse(
                    400, payload={"error": {"msg": error}}, text=error
                )
        return FakeSchemaResponse()

    def _add_field(self, body):
        name = body["name"]
        if name in self.refuse:
            return self.refuse[name]
        if name in self.fields:
            return f"field '{name}' already exists"
        self.fields[name] = body["type"]
        return None

    def _replace_field(self, body):
        if body["name"] not in self.fields:
            return f"field '{body['name']}' not found"
        self.fields[body["name"]] = body["type"]
        return None

    def _delete_field(self, body):
        for entry in body if isinstance(body, list) else [body]:
            self.fields.pop(entry["name"], None)
        return None

    def _add_field_type(self, body):
        self.field_types.add(body["name"])
        return None

    def _add_copy_field(self, body):
        directive = {"source": body["source"], "dest": body["dest"]}
        if directive in self.copy_fields:
            return "copyField source/dest already exists"
        self.copy_fields.append(directive)
        return None

    def _delete_copy_field(self, body):
        for entry in body if isinstance(body, list) else [body]:
            directive = {"source": entry["source"], "dest": entry["dest"]}
            if directive in self.copy_fields:
                self.copy_fields.remove(directive)
        return None

    def added_fields(self):
        """The names of the fields that were added, in order."""
        return [
            directive["add-field"]["name"]
            for directive in self.directives
            if "add-field" in directive
        ]

    def deleted_fields(self):
        """The names of the fields whose deletion was requested, in order."""
        names = []
        for directive in self.directives:
            body = directive.get("delete-field")
            if body is None:
                continue
            names.extend(
                entry["name"] for entry in (body if isinstance(body, list) else [body])
            )
        return names

    def copy_field_sources(self, dest):
        """The sources copy fields were added for C{dest}, in order."""
        return [
            directive["add-copy-field"]["source"]
            for directive in self.directives
            if "add-copy-field" in directive
            and directive["add-copy-field"]["dest"] == dest
        ]


class Part:
    """
    The kind of model a SolrJsonField can carry.

    Not a SolrEntity: a json field's model is anything providing C{to_json} to
    serialize an element with and a C{from_json} classmethod to rebuild it.
    """

    def __init__(self, name: str) -> None:
        self.name = name

    def to_json(self):
        return {"name": self.name}

    @classmethod
    def from_json(cls, data):
        return cls(data["name"])

    def __eq__(self, other):
        return isinstance(other, Part) and other.name == self.name

    def __repr__(self):
        return f"Part({self.name!r})"


class Gadget(SolrEntity):
    """Target of Widget's foreign key."""

    title = SolrField("title")


class Widget(SolrEntity):
    """One field of every kind the tests need. Subclasses SolrEntity
    *directly*, which SolrORM's __subclasses__() discovery requires."""

    title = SolrField("title")
    tags = SolrField("tags", multivalued=True)
    size = SolrIntField("size")
    published = SolrDateTimeField("published")
    payload = SolrBinaryField("payload")
    gadget = SolrForeignKeyField("gadget", "gadget", multivalued=True)
    notes = SolrJsonField("notes")
    parts = SolrJsonField("parts", model=Part, multivalued=True)


class Trinket(SolrEntity):
    """An entity with no *indexed* field, so query field resolution has to fall
    back on SolrORM.DEFAULT_QUERY_FIELDS."""

    title = SolrField("title", indexed=False)
    note = SolrField("note", indexed=False)


class Doodad(SolrEntity):
    """Points at a Gadget through a reverse name that contains an underscore, so
    C{gadget.data_use_entities} exercises the prefix splitting in
    C{SolrEntity.__getattr__}."""

    title = SolrField("title")
    gadget = SolrForeignKeyField(
        "gadget", "gadget", reversed_by="data_use", reversed_multiple=True
    )


ENTITIES = {
    "widget": Widget,
    "gadget": Gadget,
    "trinket": Trinket,
    "doodad": Doodad,
}


@pytest.fixture
def app_config():
    """The mapping a host application would hand to Settings.from_mapping."""
    return {
        "SOLR_ENDPOINT": SOLR_ENDPOINT,
        "SOLR_COLLECTION": SOLR_COLLECTION,
        "entities": dict(ENTITIES),
    }


@pytest.fixture
def settings(app_config):
    """Settings for the test entities. No global state is involved, so nothing
    needs resetting between tests."""
    return Settings.from_mapping(app_config)


@pytest.fixture
def indexer():
    return FakeIndexer()


@pytest.fixture
def fake_schema(monkeypatch):
    """An empty in-memory solr schema, with requests routed through it."""
    return FakeSchemaApi().install(monkeypatch)


@pytest.fixture
def solr_orm(settings, indexer):
    """
    A SolrORM whose indexer is faked.

    Constructing SolrORM performs no I/O, but it does attach ``query`` and
    ``_solr_fields`` to every SolrEntity subclass -- so entity-level tests need
    this fixture even when they never touch the indexer.
    """
    orm = SolrORM(settings)
    orm.indexer = indexer
    return orm
