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

import logging
from datetime import date, datetime, timedelta, timezone

import pytest

from solrorm.config import Settings
from solrorm.entity import SolrEntity
from solrorm.fields import SolrDateTimeField
from solrorm.orm import (
    SolrORM,
    SolrQuery,
    _encode_solr_json_value,
    _SOLR_JSON_ENCODER,
    escape_solr_value,
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


def test_a_subclass_can_override_an_inherited_field(solr_orm):
    """The bases used to be walked after the class's own attributes, so
    SolrEntity's indexed 'created' silently won over a subclass's redefinition
    of it."""

    class Gizmo(SolrEntity):
        created = SolrDateTimeField("created", indexed=False)

    fields = solr_orm.get_fields_for_class(Gizmo)

    assert fields["created"].indexed is False


def test_delete_wants_exactly_one_of_an_id_and_a_query(solr_orm, indexer):
    """It used to null the query when both were given and pass None for both
    when neither was, deleting nothing without saying so."""
    with pytest.raises(ValueError):
        solr_orm.delete()
    with pytest.raises(ValueError):
        solr_orm.delete("w-1", "widget_title:obsolete")

    solr_orm.delete(query="widget_title:obsolete")

    assert indexer.deleted[-1] == {"id": None, "q": "widget_title:obsolete"}


def test_the_schema_url_is_built_from_endpoint_and_collection(solr_orm):
    assert solr_orm.indexer_schema.url.endswith("/test_collection/schema")


def test_the_orm_keeps_the_settings_it_was_built_with(settings):
    orm = SolrORM(settings)
    assert orm.settings is settings
    assert orm.url == settings.endpoint
    assert orm.collection == settings.collection
    assert orm.indexer_schema.url.endswith(f"/{settings.collection}/schema")


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


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("plain", "plain"),
        ('a "quote"', 'a\\ \\"quote\\"'),
        ("field:value", "field\\:value"),
        ("(paren)", "\\(paren\\)"),
        ("a && b || c", "a\\ \\&\\&\\ b\\ \\|\\|\\ c"),
        ("back\\slash", "back\\\\slash"),
        ("wild*card?", "wild\\*card\\?"),
        ("[0 TO 25]", "\\[0\\ TO\\ 25\\]"),
        (42, "42"),
    ],
)
def test_escaping_neutralises_every_lucene_special_character(value, expected):
    assert escape_solr_value(value) == expected


def test_the_host_query_field_table_is_honoured_verbatim(app_config, fake_schema):
    """No entity name and no field name is baked into the library: whatever the
    host lists for an entity is what gets copied into its _text_ catch-all."""
    app_config["SOLR_QUERY_TEXT_FIELD"] = {"widget": ["title", "tags", "id"]}
    solr_orm = SolrORM(Settings.from_mapping(app_config))

    solr_orm._create_or_update_fields_for_class(Widget, update=False)

    # "id" is the one source not prefixed with the entity name
    assert fake_schema.copy_field_sources("widget_text_") == [
        "widget_title",
        "widget_tags",
        "id",
    ]


def test_an_entity_absent_from_the_table_falls_back_to_title(app_config, fake_schema):
    """Per entity, not per table: a table naming only *some* entities leaves the
    others on SolrORM.DEFAULT_QUERY_FIELDS rather than crashing or copying
    another entity's fields."""
    app_config["SOLR_QUERY_TEXT_FIELD"] = {"widget": ["title", "tags"]}
    solr_orm = SolrORM(Settings.from_mapping(app_config))

    solr_orm._create_or_update_fields_for_class(Gadget, update=False)

    assert fake_schema.copy_field_sources("gadget_text_") == ["gadget_title"]


def test_the_query_field_table_is_not_mutated_by_field_creation(
    app_config, fake_schema
):
    """The old extended-search block worked by appending to the lists inside the
    host's own config. Nothing in the library writes to the table any more."""
    app_config["SOLR_QUERY_TEXT_FIELD"] = {"widget": ["title"]}
    settings = Settings.from_mapping(app_config)
    solr_orm = SolrORM(settings)

    solr_orm._create_or_update_fields_for_class(Widget, update=False)

    assert settings.query_text_field == {"widget": ["title"]}
    assert app_config["SOLR_QUERY_TEXT_FIELD"] == {"widget": ["title"]}


def test_field_creation_builds_the_whole_schema_from_scratch(settings, fake_schema):
    """The shape of a first run: the type discriminator, the autocomplete field
    type, every entity field and the three catch-alls with their copy fields."""
    SolrORM(settings).create_fields()

    assert "type" in fake_schema.fields
    assert "autocomplete_text" in fake_schema.field_types
    assert fake_schema.fields["widget_size"] == "pint"
    for suffix, field_type, _stored in SolrORM.CATCH_ALL_FIELDS:
        assert fake_schema.fields[f"widget{suffix}"] == field_type
        assert fake_schema.copy_field_sources(f"widget{suffix}") == ["widget_title"]


def test_field_creation_is_idempotent(settings, fake_schema):
    """T10's headline fix: the catch-all fields used to be deleted and recreated
    on every run, discarding everything indexed into them. A second run must
    touch nothing -- no add, no delete, no duplicate copy field."""
    SolrORM(settings).create_fields()
    schema_after_first_run = dict(fake_schema.fields)
    copy_fields_after_first_run = list(fake_schema.copy_fields)
    fake_schema.directives.clear()

    SolrORM(settings).create_fields()

    assert fake_schema.directives == []
    assert fake_schema.fields == schema_after_first_run
    assert fake_schema.copy_fields == copy_fields_after_first_run


def test_a_refused_field_is_logged_and_the_rest_still_created(
    settings, fake_schema, caplog
):
    """One field solr will not have must not abandon the entity's other fields,
    and the reason has to reach the log rather than stdout."""
    fake_schema.refuse["widget_size"] = "unknown field type 'pint'"

    with caplog.at_level(logging.WARNING, logger="solrorm.orm"):
        SolrORM(settings).create_fields()

    assert "widget_size" in caplog.text
    assert "unknown field type 'pint'" in caplog.text
    assert "widget_size" not in fake_schema.fields
    assert "widget_title" in fake_schema.fields
    assert "widget_text_" in fake_schema.fields


def test_a_missing_catch_all_field_is_added_without_recreating_the_others(
    settings, fake_schema
):
    """A schema repair: only what is absent is written."""
    solr_orm = SolrORM(settings)
    solr_orm.create_fields()
    fake_schema.fields.pop("widget_textfuzzy_")
    fake_schema.copy_fields = [
        directive
        for directive in fake_schema.copy_fields
        if directive["dest"] != "widget_textfuzzy_"
    ]
    fake_schema.directives.clear()

    solr_orm.create_fields()

    assert fake_schema.added_fields() == ["widget_textfuzzy_"]
    assert fake_schema.copy_field_sources("widget_textfuzzy_") == ["widget_title"]
    assert fake_schema.deleted_fields() == []


def test_update_fields_replaces_the_entity_fields_only(settings, fake_schema):
    """update_fields is about field definitions; the catch-alls and their copy
    fields are still only ever added when absent."""
    solr_orm = SolrORM(settings)
    solr_orm.create_fields()
    fake_schema.fields["widget_title"] = "text_en"
    fake_schema.directives.clear()

    solr_orm.update_fields()

    assert any("replace-field" in directive for directive in fake_schema.directives)
    assert fake_schema.added_fields() == []
    assert fake_schema.deleted_fields() == []
    assert fake_schema.fields["widget_title"] == "string"


def test_the_autocomplete_field_type_is_created_once_for_the_collection(
    settings, fake_schema
):
    """It is collection-global, so it belongs outside the per-entity loop."""
    SolrORM(settings).create_fields()

    assert [
        directive
        for directive in fake_schema.directives
        if "add-field-type" in directive
    ] == [{"add-field-type": SolrORM.AUTOCOMPLETE_FIELD_TYPE}]


def test_deletion_covers_every_registered_entity(settings, fake_schema):
    """delete_fields used to walk __subclasses__() while creation walked the
    entities registry; the registry is the documented contract."""
    solr_orm = SolrORM(settings)
    solr_orm.create_fields()

    solr_orm.delete_fields()

    assert fake_schema.fields == {}
    assert fake_schema.copy_fields == []


def test_field_existence_is_reported_from_the_live_schema(settings, fake_schema):
    solr_orm = SolrORM(settings)
    assert not solr_orm.check_fields_existence()

    solr_orm.create_fields()

    assert solr_orm.check_fields_existence() is True


def test_missing_and_mismatched_fields_read_the_live_schema(settings, fake_schema):
    solr_orm = SolrORM(settings)
    solr_orm.create_fields()
    assert solr_orm.missing_fields("widget") == []
    assert solr_orm.mismatched_fields("widget") == []

    fake_schema.fields.pop("widget_tags")
    fake_schema.fields["widget_title"] = "text_en"

    assert solr_orm.missing_fields("widget") == ["widget_tags"]
    assert solr_orm.mismatched_fields("widget") == [
        ("widget_title", "string", "text_en")
    ]
