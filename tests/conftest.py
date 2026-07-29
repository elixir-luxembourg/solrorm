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

from solrorm.config import Settings
from solrorm.orm import SolrORM
from solrorm.entity import SolrEntity
from solrorm.fields import (
    SolrBinaryField,
    SolrDateTimeField,
    SolrField,
    SolrForeignKeyField,
    SolrIntField,
)

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


class Trinket(SolrEntity):
    """An entity with no *indexed* field, so query field resolution has to fall
    back on SolrORM.DEFAULT_QUERY_FIELDS."""

    title = SolrField("title", indexed=False)
    note = SolrField("note", indexed=False)


ENTITIES = {"widget": Widget, "gadget": Gadget, "trinket": Trinket}


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
