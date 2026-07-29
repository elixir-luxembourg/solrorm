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
"""Tests for the Settings object."""

import dataclasses

import pytest

from solrorm.config import Settings

from .conftest import SOLR_COLLECTION, SOLR_ENDPOINT, Widget


def test_the_defaults_cover_every_optional_setting():
    settings = Settings(endpoint=SOLR_ENDPOINT, collection=SOLR_COLLECTION)
    assert settings.entities == {}
    assert settings.fuzzy_search_level == 4
    assert settings.use_cursor_pagination is False
    assert settings.boost == {}
    assert settings.default_sort == {}
    assert settings.query_text_field == {}


def test_settings_are_frozen():
    settings = Settings(endpoint=SOLR_ENDPOINT, collection=SOLR_COLLECTION)
    with pytest.raises(dataclasses.FrozenInstanceError):
        setattr(settings, "collection", "other")


def test_each_instance_gets_its_own_mutable_defaults():
    """A shared default dict would leak one host's entities into another's."""
    first = Settings(endpoint=SOLR_ENDPOINT, collection="a")
    second = Settings(endpoint=SOLR_ENDPOINT, collection="b")
    first.entities["widget"] = Widget
    assert second.entities == {}


def test_from_mapping_round_trips_every_key():
    entities = {"widget": object()}
    mapping = {
        "SOLR_ENDPOINT": SOLR_ENDPOINT,
        "SOLR_COLLECTION": SOLR_COLLECTION,
        "entities": entities,
        "FUZZY_SEARCH_LEVEL": 2,
        "USE_CURSOR_PAGINATION": True,
        "SOLR_BOOST": {"widget": "widget_title^5"},
        "SOLR_DEFAULT_SORT": {"widget": "size"},
        "SOLR_QUERY_TEXT_FIELD": {"widget": ["title", "tags"]},
    }
    settings = Settings.from_mapping(mapping)
    assert settings.endpoint == SOLR_ENDPOINT
    assert settings.collection == SOLR_COLLECTION
    assert settings.entities == entities
    assert settings.fuzzy_search_level == 2
    assert settings.use_cursor_pagination is True
    assert settings.boost == {"widget": "widget_title^5"}
    assert settings.default_sort == {"widget": "size"}
    assert settings.query_text_field == {"widget": ["title", "tags"]}


def test_the_query_field_table_is_copied_not_aliased(app_config):
    """The library must neither mutate the host's mapping nor be steered by a
    later edit to it -- the lists inside it are copied as well as the dict."""
    table = {"widget": ["title"]}
    app_config["SOLR_QUERY_TEXT_FIELD"] = table
    settings = Settings.from_mapping(app_config)

    settings.query_text_field["widget"].append("tags")
    settings.query_text_field["gadget"] = ["title"]
    assert table == {"widget": ["title"]}

    table["widget"].append("note")
    assert settings.query_text_field["widget"] == ["title", "tags"]


def test_from_mapping_leaves_absent_keys_at_their_default(app_config):
    settings = Settings.from_mapping(app_config)
    assert settings.fuzzy_search_level == 4
    assert settings.boost == {}


def test_from_mapping_requires_the_endpoint_and_the_collection():
    with pytest.raises(KeyError):
        Settings.from_mapping({"SOLR_COLLECTION": SOLR_COLLECTION})
    with pytest.raises(KeyError):
        Settings.from_mapping({"SOLR_ENDPOINT": SOLR_ENDPOINT})


def test_from_mapping_ignores_keys_it_does_not_know(app_config):
    app_config["SOMETHING_ELSE"] = "ignored"
    assert Settings.from_mapping(app_config).collection == SOLR_COLLECTION
