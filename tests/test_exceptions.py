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
"""Tests for the exception hierarchy and how query failures surface."""

import pytest
from pysolr import SolrError as PysolrError

import solrorm
from solrorm.exceptions import SolrEntityNotFound, SolrORMError, SolrQueryException

from .conftest import Widget


def test_every_error_is_catchable_as_one_base_class():
    assert issubclass(SolrQueryException, SolrORMError)
    assert issubclass(SolrEntityNotFound, SolrORMError)
    assert issubclass(SolrORMError, Exception)


def test_the_errors_are_exported_from_the_package_root():
    assert solrorm.SolrORMError is SolrORMError
    assert solrorm.SolrQueryException is SolrQueryException
    assert solrorm.SolrEntityNotFound is SolrEntityNotFound


def test_a_pysolr_failure_during_search_is_rewrapped(solr_orm, indexer, monkeypatch):
    """A caller should not have to import pysolr to handle a failed query."""

    def explode(*_args, **_kwargs):
        raise PysolrError("solr said no")

    monkeypatch.setattr(indexer, "search", explode)
    with pytest.raises(SolrQueryException, match="solr said no"):
        Widget.query.search(query="cancer")


def test_our_error_does_not_share_pysolrs_name(solr_orm):
    """pysolr exports a SolrError of its own, so ours is named SolrORMError."""
    assert SolrORMError is not PysolrError
    assert not hasattr(solrorm, "SolrError")


def test_a_missing_entity_is_the_hosts_to_signal(solr_orm, indexer):
    """The library returns None; SolrEntityNotFound is there for the host."""
    assert Widget.query.get("absent") is None
    with pytest.raises(SolrEntityNotFound):
        raise SolrEntityNotFound("absent")
