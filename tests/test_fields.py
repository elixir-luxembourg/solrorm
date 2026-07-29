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
Tests for the field descriptors.

The Solr type each descriptor selects is part of the public contract: changing
one silently invalidates an existing index, so it is pinned here.
"""

import pytest

from solrorm.solr_orm_fields import (
    SolrBinaryField,
    SolrBooleanField,
    SolrCaseInsensitiveStringField,
    SolrDateTimeField,
    SolrField,
    SolrFloatField,
    SolrForeignKeyField,
    SolrIntField,
    SolrJsonField,
    SolrLongField,
    SolrTextField,
)


@pytest.mark.parametrize(
    "field_class, expected_single, expected_multi",
    [
        (SolrIntField, "pint", "pints"),
        (SolrLongField, "plong", "plongs"),
        (SolrFloatField, "pfloat", "pfloats"),
        (SolrDateTimeField, "pdate", "pdates"),
    ],
)
def test_numeric_and_date_types_pluralise_when_multivalued(
    field_class, expected_single, expected_multi
):
    assert field_class("f").type == expected_single
    assert field_class("f", multivalued=True).type == expected_multi


@pytest.mark.parametrize(
    "field_class, expected",
    [
        (SolrField, "string"),
        (SolrTextField, "text_en"),
        (SolrJsonField, "text_en"),
        (SolrBooleanField, "boolean"),
        (SolrBinaryField, "binary"),
        (SolrCaseInsensitiveStringField, "lowercase"),
    ],
)
def test_the_remaining_types_are_unaffected_by_multivalued(field_class, expected):
    assert field_class("f").type == expected
    assert field_class("f", multivalued=True).type == expected


def test_fields_are_indexed_and_stored_by_default():
    field = SolrField("title")
    assert field.indexed is True
    assert field.stored is True
    assert field.multivalued is False


def test_binary_fields_are_not_indexed_by_default():
    """Indexing a base64 blob is never useful, so the default differs."""
    assert SolrBinaryField("payload").indexed is False
    assert SolrBinaryField("payload").stored is True


def test_the_attribute_name_defaults_to_the_field_name():
    assert SolrField("title").attribute_name == "title"
    assert SolrField("title", "heading").attribute_name == "heading"


def test_a_foreign_key_records_its_target_entity():
    field = SolrForeignKeyField("owner", "gadget", reversed_by="widgets")
    assert field.type == "string"
    assert field.linked_entity_name == "gadget"
    assert field.reversed_by == "widgets"
    assert field.reversed_multiple is False


def test_a_json_field_can_carry_a_model():
    marker = object()
    assert SolrJsonField("meta", model=marker).model is marker
    assert SolrJsonField("meta").model is None
