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
"""Tests for SolrEntity construction, serialisation and indexing."""

import base64
from datetime import datetime

import pytest

from .conftest import Widget


def test_plural_name_is_the_lowercased_class_name():
    assert Widget.plural_name() == "widgets"


def test_an_id_is_generated_when_none_is_given(solr_orm):
    widget = Widget()
    assert widget.id
    assert Widget().id != widget.id


def test_the_timestamps_start_equal(solr_orm):
    widget = Widget()
    assert isinstance(widget.created, datetime)
    assert widget.modified == widget.created


def test_unset_fields_are_none_rather_than_the_descriptor(solr_orm):
    """Without the __init__ reset, attribute access would return the
    SolrField instance itself."""
    assert Widget().title is None


def test_to_dict_prefixes_every_key_with_the_entity_name(solr_orm):
    widget = Widget(entity_id="w-1")
    widget.title = "a widget"
    entity_dict = widget.to_dict()
    assert entity_dict["widget_title"] == "a widget"
    assert entity_dict["id"] == "w-1"


def test_to_dict_can_omit_the_prefix(solr_orm):
    widget = Widget(entity_id="w-1")
    widget.title = "a widget"
    assert widget.to_dict(add_prefix=False)["title"] == "a widget"


def test_to_dict_base64_encodes_binary_fields(solr_orm):
    widget = Widget(entity_id="w-1")
    widget.payload = b"\x00\x01binary"
    encoded = widget.to_dict()["widget_payload"]
    assert base64.b64decode(encoded) == b"\x00\x01binary"


def test_to_dict_replaces_spaces_in_the_id(solr_orm):
    """Solr ids are used verbatim in query strings, where a space would split
    the term."""
    assert Widget(entity_id="w 1").to_dict()["id"] == "w_1"


def test_save_prefixes_the_id_and_records_the_type(solr_orm, indexer):
    Widget(entity_id="w-1").save()
    (docs, _kwargs) = indexer.added[-1]
    assert docs[0]["id"] == "widget_w-1"
    assert docs[0]["type"] == "widget"


def test_save_does_not_commit_unless_asked(solr_orm, indexer):
    Widget(entity_id="w-1").save()
    assert indexer.commits == []


def test_save_commits_when_asked(solr_orm, indexer):
    Widget(entity_id="w-1").save(commit=True)
    assert indexer.commits == [{"softCommit": False}]


def test_save_can_soft_commit(solr_orm, indexer):
    Widget(entity_id="w-1").save(soft_commit=True)
    assert indexer.commits == [{"softCommit": True}]


def test_delete_passes_the_unprefixed_id(solr_orm, indexer):
    Widget(entity_id="w-1").delete()
    assert indexer.deleted[-1]["id"] == "w-1"


def test_an_unknown_attribute_still_raises(solr_orm):
    """__getattr__ resolves foreign keys, so it must not swallow typos."""
    with pytest.raises(AttributeError, match="no attribute 'nonexistent'"):
        Widget().nonexistent
