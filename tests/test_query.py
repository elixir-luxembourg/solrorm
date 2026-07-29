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
"""Tests for SolrQuery: what it sends to Solr and what it builds from the
response."""

import pytest

from solrorm.config import Settings
from solrorm.facets import Facet, FacetRange, Range
from solrorm.orm import SolrORM

from .conftest import Trinket, Widget, solr_response


def test_get_looks_the_id_up_with_the_entity_prefix(solr_orm, indexer):
    Widget.query.get("w-1")
    q, params = indexer.last_search
    assert q == 'id:"widget_w-1"'
    assert params["rows"] == 1


def test_get_returns_none_when_nothing_matches(solr_orm, indexer):
    assert Widget.query.get("absent") is None


def test_get_strips_the_prefix_back_off_the_id(solr_orm, indexer):
    indexer.queue(solr_response([{"id": "widget_w-1", "widget_title": "a widget"}]))
    widget = Widget.query.get("w-1")
    assert widget.id == "w-1"
    assert widget.title == "a widget"


def test_get_by_slug_queries_the_slugs_field(solr_orm, indexer):
    Widget.query.get_by_slug("a-widget")
    q, _params = indexer.last_search
    assert q == 'widget_slugs:"a-widget"'


def test_a_datetime_field_is_parsed_back_into_a_datetime(solr_orm, indexer):
    indexer.queue(
        solr_response(
            [{"id": "widget_w-1", "widget_published": "2024-03-01T12:00:00Z"}]
        )
    )
    widget = Widget.query.get("w-1")
    assert widget.published.year == 2024
    assert widget.published.month == 3


def test_count_filters_on_the_entity_type(solr_orm, indexer):
    indexer.queue(solr_response(num_found=7))
    assert Widget.query.count() == 7
    q, _params = indexer.last_search
    assert q == "type:widget"


def test_an_empty_search_matches_everything(solr_orm, indexer):
    Widget.query.search(query="")
    q, params = indexer.last_search
    assert q == "*:*"
    assert params["fq"] == []


def test_a_free_text_search_is_a_scoring_query_by_default(solr_orm, indexer):
    """The default sort is ``score desc``, and only a query in ``q`` scores --
    so the default path must not push the terms into ``fq``."""
    Widget.query.search(query="cancer")
    q, params = indexer.last_search
    assert q == "widget_text_:'cancer'"
    assert params["fq"] == []


def test_sorting_on_a_field_turns_the_query_into_a_filter(solr_orm, indexer):
    """Once relevance is irrelevant, the terms move to ``fq``, where Solr can
    cache the filter."""
    Widget.query.search(query="cancer", sort="widget_size", sort_order="asc")
    q, params = indexer.last_search
    assert q == "*:*"
    assert params["fq"] == ["widget_text_:'cancer'"]


def test_the_sort_order_is_appended_to_the_sort_field(solr_orm, indexer):
    Widget.query.search(query="", sort="widget_size", sort_order="asc")
    _q, params = indexer.last_search
    assert params["sort"] == "widget_size asc"


def test_sorting_defaults_to_score_when_no_field_is_given(solr_orm, indexer):
    Widget.query.search(query="")
    _q, params = indexer.last_search
    assert params["sort"] == "score desc"


def test_a_fuzzy_search_adds_the_configured_tolerance(app_config, indexer):
    app_config["FUZZY_SEARCH_LEVEL"] = 2
    orm = SolrORM(Settings.from_mapping(app_config))
    orm.indexer = indexer
    Widget.query.search(query="cancer", fuzzy=True)
    q, _params = indexer.last_search
    assert q == "(widget_text_:'cancer' OR widget_textfuzzy_:cancer~2)"


def test_the_fuzzy_tolerance_defaults_to_four(solr_orm, indexer):
    """The tolerance comes from the settings of the ORM issuing the query."""
    Widget.query.search(query="cancer", fuzzy=True)
    q, _params = indexer.last_search
    assert "cancer~4" in q


def test_a_facet_is_requested_with_the_prefixed_field_name(solr_orm, indexer):
    Widget.query.search(query="", facets=[Facet("title", "Title")])
    _q, params = indexer.last_search
    assert params["facet"] == "on"
    assert params["facet.field"] == ["widget_title"]


def test_selected_facet_values_are_quoted_into_a_filter_query(solr_orm, indexer):
    facet = Facet("title", "Title")
    facet.set_values(['a "quoted" widget'])
    Widget.query.search(query="", facets=[facet])
    _q, params = indexer.last_search
    assert 'widget_title:"a \\"quoted\\" widget"' in params["fq"]


def test_a_range_facet_is_requested_with_its_bounds(solr_orm, indexer):
    """Every FacetRange search used to raise TypeError: the prefixed field name
    was passed to list.append as two arguments."""
    facet = FacetRange("size", "Size", Range(0, 100, 25, other="all"))
    Widget.query.search(query="", facets=[facet])
    _q, params = indexer.last_search
    assert params["facet.range"] == ["widget_size"]
    assert params["f.widget_size.facet.range.start"] == 0
    assert params["f.widget_size.facet.range.end"] == 100
    assert params["f.widget_size.facet.range.gap"] == 25
    assert params["f.widget_size.facet.range.other"] == "all"


def test_selected_range_facet_values_become_filter_queries(solr_orm, indexer):
    facet = FacetRange("size", "Size", Range(0, 100, 25))
    facet.set_values(["[0 TO 25]"])
    Widget.query.search(query="", facets=[facet])
    _q, params = indexer.last_search
    assert "widget_size:[0 TO 25]" in params["fq"]


def test_the_entity_prefix_is_stripped_from_the_returned_facets(solr_orm, indexer):
    indexer.queue(
        solr_response(facets={"facet_fields": {"widget_title": ["a widget", 3]}})
    )
    results = Widget.query.search(query="", facets=[Facet("title", "Title")])
    assert results.facets["facet_fields"] == {"title": ["a widget", 3]}


@pytest.fixture
def unindexed(solr_orm, monkeypatch):
    """Trinket with only unindexed fields, so query-field resolution has to fall
    back on SolrORM.DEFAULT_QUERY_FIELDS.

    Trinket declares its own fields ``indexed=False``, but ``_solr_fields`` also
    carries SolrEntity's indexed ``created``/``modified`` -- and a base class's
    field wins over a subclass's redefinition (``_find_fields`` walks bases
    last), so the registry is patched rather than declared.
    """
    fields = {
        name: field for name, field in Trinket._solr_fields.items() if not field.indexed
    }
    monkeypatch.setattr(Trinket, "_solr_fields", fields)
    return Trinket


def test_query_field_detection_falls_back_to_the_orm_default(unindexed, indexer):
    """With no indexed field the fallback used to read a non-existent
    SolrQuery.DEFAULT_QUERY_FIELDS and raise AttributeError."""
    assert unindexed.query.query_has_solr_query_field("trinket_title:thing") is True
    assert unindexed.query.query_has_solr_query_field("trinket_note:thing") is False


def test_a_field_query_on_an_unindexed_entity_still_searches(unindexed, indexer):
    unindexed.query.search(query="trinket_title:thing")
    q, params = indexer.last_search
    assert q == "*:*"
    assert params["fq"] == ["trinket_title:thing"]


def test_search_attaches_built_entities_to_the_results(solr_orm, indexer):
    indexer.queue(solr_response([{"id": "widget_w-1", "widget_title": "a widget"}]))
    results = Widget.query.search(query="")
    assert [widget.title for widget in results.entities] == ["a widget"]


def test_all_follows_the_cursor_until_it_stops_moving(solr_orm, indexer):
    indexer.queue(
        solr_response([{"id": "widget_w-1"}], next_cursor="page2"),
        solr_response([{"id": "widget_w-2"}], next_cursor="page2"),
    )
    widgets = list(Widget.query.all())
    assert [widget.id for widget in widgets] == ["w-1", "w-2"]
    assert [params.get("cursorMark") for _q, params in indexer.searches] == [
        "*",
        "page2",
    ]


def test_all_ids_strips_the_entity_prefix(solr_orm, indexer):
    indexer.queue(solr_response([{"id": "widget_w-1"}, {"id": "widget_w-2"}]))
    assert Widget.query.all_ids() == ["w-1", "w-2"]


def test_delete_restricts_the_query_to_the_entity_type(solr_orm, indexer):
    Widget.query.delete("widget_title:obsolete")
    assert indexer.deleted[-1]["q"] == "widget_title:obsolete AND type:widget"


def test_delete_commits_only_when_asked(solr_orm, indexer):
    Widget.query.delete("widget_title:obsolete")
    assert indexer.commits == []
    Widget.query.delete("widget_title:obsolete", commit=True)
    assert len(indexer.commits) == 1
