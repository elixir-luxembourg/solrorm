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
"""Tests for SolrORM itself: entity discovery, field collection and the
document encoder."""

from datetime import date, datetime, timedelta, timezone

import pytest

from solrorm.config import Settings
from solrorm.orm import (
    SolrORM,
    SolrQuery,
    _encode_solr_json_value,
    _SOLR_JSON_ENCODER,
)

from .conftest import Gadget, Widget


def test_construction_attaches_a_query_to_every_entity(solr_orm):
    assert isinstance(Widget.query, SolrQuery)
    assert isinstance(Gadget.query, SolrQuery)
    assert Widget.query.class_object is Widget
    assert Widget.query.entity_name == "widget"


def test_construction_attaches_the_orm_to_the_entity_base(solr_orm):
    assert Widget._solr_orm is solr_orm


def test_field_collection_finds_the_declared_fields(solr_orm):
    fields = solr_orm.get_fields_for_class(Widget)
    assert {"title", "tags", "size", "published", "payload", "gadget"} <= set(fields)


def test_field_collection_includes_the_inherited_base_fields(solr_orm):
    """created/modified are declared on SolrEntity, so every entity must carry
    them or the schema will be missing columns the ORM writes."""
    fields = solr_orm.get_fields_for_class(Widget)
    assert {"created", "modified", "former_ids", "connector_name"} <= set(fields)


def test_the_schema_url_is_built_from_endpoint_and_collection(solr_orm):
    assert solr_orm.indexer_schema.url.endswith("/test_collection/schema")


def test_the_orm_keeps_the_settings_it_was_built_with(settings):
    orm = SolrORM(settings)
    assert orm.settings is settings
    assert orm.url == settings.endpoint
    assert orm.collection == settings.collection
    assert orm.indexer_schema.settings is settings


def test_two_orms_serve_two_collections_without_interfering(app_config):
    """The point of T3: no module-level state, so one process can hold two."""
    first = SolrORM(
        Settings.from_mapping(
            {**app_config, "SOLR_COLLECTION": "first", "SOLR_BOOST": {"widget": "a^2"}}
        )
    )
    second = SolrORM(
        Settings.from_mapping(
            {
                **app_config,
                "SOLR_COLLECTION": "second",
                "SOLR_BOOST": {"widget": "b^3"},
                "USE_CURSOR_PAGINATION": True,
            }
        )
    )
    assert first.collection == "first"
    assert second.collection == "second"
    assert first.settings.boost == {"widget": "a^2"}
    assert second.settings.boost == {"widget": "b^3"}
    assert first.indexer.url.endswith("/first")
    assert second.indexer.url.endswith("/second")
    assert first.indexer_schema.url.endswith("/first/schema")
    assert second.indexer_schema.url.endswith("/second/schema")
    # per-instance, so the second construction does not reconfigure the first
    assert SolrQuery(Widget, first).cursor_enabled is False
    assert SolrQuery(Widget, second).cursor_enabled is True


def test_entities_are_read_eagerly(app_config):
    """The behaviour change T3 introduces: an entity registered after
    construction is invisible, where the old reference-holding config saw it."""
    orm = SolrORM(Settings.from_mapping(app_config))
    app_config["entities"]["late"] = Gadget
    assert "late" not in orm.settings.entities


def test_a_naive_datetime_is_encoded_as_utc():
    encoded = _encode_solr_json_value(datetime(2024, 3, 1, 12, 30, 15, 500000))
    assert encoded == "2024-03-01T12:30:15.500Z"


def test_an_aware_datetime_is_shifted_to_utc():
    aware = datetime(2024, 3, 1, 13, 0, tzinfo=timezone(timedelta(hours=-1)))
    assert _encode_solr_json_value(aware) == "2024-03-01T14:00:00.000Z"


def test_a_date_is_encoded_at_midnight():
    assert _encode_solr_json_value(date(2024, 3, 1)) == "2024-03-01T00:00:00Z"


def test_an_unencodable_value_is_rejected():
    with pytest.raises(TypeError, match="not JSON serializable"):
        _encode_solr_json_value(object())


def test_the_encoder_the_orm_hands_pysolr_serialises_datetimes():
    """pysolr serialises documents with this encoder, so a datetime attribute
    must reach Solr as a pdate string rather than raising."""
    encoded = _SOLR_JSON_ENCODER.encode({"widget_published": datetime(2024, 3, 1)})
    assert encoded == '{"widget_published": "2024-03-01T00:00:00.000Z"}'
