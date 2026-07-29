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
Tests for the schema admin.

These exercise the schema API payloads, so ``requests`` is faked rather than
the indexer.
"""

import pytest
from requests import HTTPError

from solrorm import schema as schema_module
from solrorm.schema import SolrSchemaAdmin, _solr_error

SCHEMA_URL = "http://solr.invalid:8983/solr/test_collection/schema"


class FakeResponse:
    """The parts of a requests.Response that the schema admin touches."""

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
            raise HTTPError(f"{self.status_code}", response=self)


class Posts:
    """Captured schema posts. Set ``response`` to control what Solr replies."""

    def __init__(self):
        self.calls = []
        self.response = FakeResponse()

    def __getitem__(self, index):
        return self.calls[index]

    def record(self, url, **kwargs):
        self.calls.append((url, kwargs))
        return self.response


@pytest.fixture
def posts(monkeypatch):
    captured = Posts()
    monkeypatch.setattr(schema_module.requests, "post", captured.record)
    return captured


@pytest.fixture
def admin(configured):
    return SolrSchemaAdmin(SCHEMA_URL)


def test_create_field_posts_the_add_field_directive(admin, posts):
    admin.create_field("widget_title", "string", index=True, store=True)
    url, kwargs = posts[-1]
    assert url == SCHEMA_URL
    assert kwargs["json"] == {
        "add-field": {
            "name": "widget_title",
            "type": "string",
            "stored": True,
            "indexed": True,
            "multiValued": False,
        }
    }


def test_update_field_posts_the_replace_field_directive(admin, posts):
    admin.update_field("widget_title", "text_en", multivalued=True)
    _url, kwargs = posts[-1]
    assert kwargs["json"] == {
        "replace-field": {
            "name": "widget_title",
            "type": "text_en",
            "stored": False,
            "indexed": True,
            "multiValued": True,
        }
    }


def test_delete_field_posts_the_delete_field_directive(admin, posts):
    admin.delete_field("widget_title")
    _url, kwargs = posts[-1]
    assert kwargs["json"] == {"delete-field": {"name": "widget_title"}}


def test_create_field_raises_when_solr_refuses(admin, posts):
    posts.response = FakeResponse(400, text="bad request")
    with pytest.raises(HTTPError):
        admin.create_field("widget_title", "string")


def test_delete_field_surfaces_the_reason_solr_gave(admin, posts):
    """A bare raise_for_status would leave only an opaque 400; the copy field
    still referring to the field is the part the operator needs."""
    posts.response = FakeResponse(
        400,
        payload={
            "error": {
                "details": [
                    {
                        "errorMessages": [
                            "Can't delete field 'widget_title' because it's "
                            "referred to by at least one copyField directive\n"
                        ]
                    }
                ]
            }
        },
    )
    with pytest.raises(HTTPError, match="copyField directive"):
        admin.delete_field("widget_title")


def test_the_error_helper_falls_back_to_the_top_level_message():
    response = FakeResponse(400, payload={"error": {"msg": "unknown field type"}})
    assert _solr_error(response) == "unknown field type"


def test_the_error_helper_falls_back_to_the_raw_body():
    assert _solr_error(FakeResponse(500, text="gateway exploded")) == "gateway exploded"


def test_the_query_field_defaults_are_currently_hardcoded(admin):
    """
    Pins the behaviour T9 of RELEASE_PLAN.md removes.

    These three entity names belong to one consuming application, not to the
    library. When T9 lands, this test should be replaced, not repaired.
    """
    assert admin.solr_query_fields == {
        "dataset": ["title"],
        "project": ["title"],
        "study": ["title"],
    }


def test_extended_search_mutates_the_hosts_own_config(configured):
    """
    Pins the side effect T9 removes.

    ``solr_query_fields`` is never read by the library; the extended-search
    feature works only because these appends mutate the list objects inside the
    host's config mapping, which SolrORM later reads back.
    """
    configured["SOLR_QUERY_TEXT_FIELD"] = {
        "dataset": ["title"],
        "project": ["title"],
        "study": ["title"],
    }
    configured["SOLR_QUERY_SEARCH_EXTENDED"] = True
    SolrSchemaAdmin(SCHEMA_URL)
    assert configured["SOLR_QUERY_TEXT_FIELD"]["project"] == [
        "title",
        "datasets_metadata",
        "studies_metadata",
    ]
    assert configured["SOLR_QUERY_TEXT_FIELD"]["study"] == [
        "title",
        "datasets_metadata",
    ]


def test_extended_search_breaks_on_an_unknown_entity_set(configured):
    """
    Pins the crash T9 fixes: a host whose entities are not dataset/project/study
    cannot enable extended search at all.
    """
    configured["SOLR_QUERY_TEXT_FIELD"] = {"widget": ["title"]}
    configured["SOLR_QUERY_SEARCH_EXTENDED"] = True
    with pytest.raises(TypeError):
        SolrSchemaAdmin(SCHEMA_URL)
