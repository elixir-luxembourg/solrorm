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

from solrorm.entity import SolrEntity
from solrorm.fields import SolrField

from .conftest import Gadget, Part, Widget, solr_response


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
    """A field read on an instance is a value, never the field object."""
    assert Widget().title is None


def test_a_field_read_on_the_class_is_still_the_field(solr_orm):
    """Field collection reads the class attributes, so the descriptor must hand
    itself back when there is no instance to read a value from."""
    assert isinstance(Widget.title, SolrField)
    assert Widget.title.name == "title"


def test_two_instances_do_not_share_a_field_value(solr_orm):
    first, second = Widget(), Widget()
    first.title = "the first"
    assert second.title is None


def test_each_entity_class_gets_its_own_reverse_field_registry():
    """reversed_field used to be one dict on the base class, shared by every
    subclass and working only because SolrORM reset it during discovery."""
    assert Gadget.reversed_field is not SolrEntity.reversed_field
    assert Gadget.reversed_field is not Widget.reversed_field


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
        _ = Widget().nonexistent


def test_from_json_round_trips_a_datetime(solr_orm):
    widget = Widget(entity_id="w-1")
    widget.published = datetime(2021, 3, 4, 5, 6, 7, 89000)
    parsed = Widget.from_json(widget.to_dict())
    assert parsed.published == widget.published


def test_from_json_parses_a_datetime_without_microseconds(solr_orm):
    parsed = Widget.from_json({"widget_published": "2021-03-04T05:06:07Z"})
    assert parsed.published == datetime(2021, 3, 4, 5, 6, 7)


def test_from_json_round_trips_a_binary_blob(solr_orm):
    """to_dict encodes with base64, so from_json must decode with base64."""
    widget = Widget(entity_id="w-1")
    widget.payload = b"\x00\x01binary"
    assert Widget.from_json(widget.to_dict()).payload == b"\x00\x01binary"


def test_from_json_round_trips_an_int(solr_orm):
    widget = Widget(entity_id="w-1")
    widget.size = 42
    assert Widget.from_json(widget.to_dict()).size == 42


def test_from_json_round_trips_a_json_field(solr_orm):
    """from_json used to hand back the raw json string where _build_instance
    decoded it; both now go through the same helper."""
    widget = Widget(entity_id="w-1")
    widget.notes = {"colour": "red", "sizes": [1, 2]}
    assert Widget.from_json(widget.to_dict()).notes == {
        "colour": "red",
        "sizes": [1, 2],
    }


def test_from_json_round_trips_a_json_field_with_a_model(solr_orm):
    widget = Widget(entity_id="w-1")
    widget.parts = [Part("bolt"), Part("nut")]

    parsed = Widget.from_json(widget.to_dict())

    assert parsed.parts == [Part("bolt"), Part("nut")]


def test_to_dict_leaves_the_models_it_serialised_in_place(solr_orm):
    """Serializing used to overwrite the entity's own list with the json it
    produced, so the second call had nothing left to serialize."""
    widget = Widget(entity_id="w-1")
    widget.parts = [Part("bolt")]

    widget.to_dict()

    assert widget.parts == [Part("bolt")]


def test_the_search_and_json_paths_decode_a_model_alike(solr_orm):
    """_build_instance and from_json must agree; they used to drift."""
    widget = Widget(entity_id="w-1")
    widget.parts = [Part("bolt")]
    document = widget.to_dict()
    document["id"] = "widget_w-1"

    built = Widget.query._build_instance(document)

    assert built.parts == Widget.from_json(widget.to_dict()).parts


def test_from_json_keeps_the_id(solr_orm):
    assert Widget.from_json(Widget(entity_id="w-1").to_dict()).id == "w-1"


def test_a_reverse_reference_with_an_underscore_resolves(solr_orm, indexer):
    """Doodad.gadget is reversed_by='data_use', so the prefix of
    'data_use_entities' must keep its underscore to be found in
    reversed_field."""
    indexer.queue(solr_response([{"id": "doodad_d-1", "doodad_title": "a doodad"}]))
    holding = Gadget(entity_id="g-1").data_use_entities
    (_query, params) = indexer.last_search
    assert params["fq"] == ['type:"doodad"', 'doodad_gadget:"g\\-1"']
    assert [doodad.title for doodad in holding] == ["a doodad"]
