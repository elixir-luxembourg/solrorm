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
from solrorm.exceptions import SolrEntityNotFound
from solrorm.facets import Facet, FacetRange, Range
from solrorm.orm import BATCH_SIZE, SolrAutomaticQuery, SolrORM

from .conftest import Gadget, Trinket, Widget, solr_response


def test_get_looks_the_id_up_with_the_entity_prefix(solr_orm, indexer):
    Widget.query.get("w-1")
    q, params = indexer.last_search
    assert q == 'id:"widget_w\\-1"'
    assert params["rows"] == 1


def test_get_returns_none_when_nothing_matches(solr_orm, indexer):
    assert Widget.query.get("absent") is None


def test_get_strips_the_prefix_back_off_the_id(solr_orm, indexer):
    indexer.queue(solr_response([{"id": "widget_w-1", "widget_title": "a widget"}]))
    widget = Widget.query.get("w-1")
    assert widget is not None
    assert widget.id == "w-1"
    assert widget.title == "a widget"


def test_get_or_raise_returns_the_entity_when_it_is_there(solr_orm, indexer):
    indexer.queue(solr_response([{"id": "widget_w-1", "widget_title": "a widget"}]))
    widget = Widget.query.get_or_raise("w-1")
    assert widget.id == "w-1"
    assert widget.title == "a widget"


def test_get_or_raise_names_the_entity_and_id_it_could_not_find(solr_orm, indexer):
    with pytest.raises(SolrEntityNotFound, match="no widget with id 'absent'"):
        Widget.query.get_or_raise("absent")


def test_get_by_slug_queries_the_slugs_field(solr_orm, indexer):
    Widget.query.get_by_slug("a-widget")
    q, _params = indexer.last_search
    assert q == 'widget_slugs:"a\\-widget"'


def test_an_id_carrying_query_syntax_is_escaped(solr_orm, indexer):
    Widget.query.get('w-1" OR type:gadget OR id:(x')
    q, _params = indexer.last_search
    assert q == 'id:"widget_w\\-1\\"\\ OR\\ type\\:gadget\\ OR\\ id\\:\\(x"'


def test_a_slug_carrying_query_syntax_is_escaped(solr_orm, indexer):
    Widget.query.get_by_slug('a-widget" OR *:*')
    q, _params = indexer.last_search
    assert q == 'widget_slugs:"a\\-widget\\"\\ OR\\ \\*\\:\\*"'


def test_a_raw_field_query_is_still_passed_through(solr_orm, indexer):
    """search()'s query argument is solr syntax by contract, so the operators
    the caller wrote must survive untouched."""
    Widget.query.search(query="widget_title:foo OR widget_title:bar")
    q, params = indexer.last_search
    assert q == "*:*"
    assert params["fq"] == ["widget_title:foo OR widget_title:bar"]


def test_free_text_search_leaves_the_query_untouched(solr_orm, indexer):
    Widget.query.search(query="a phrase (with parens)")
    q, _params = indexer.last_search
    assert q == "widget_text_:'a phrase (with parens)'"


def test_search_holding_entities_escapes_its_filter_pair(solr_orm, indexer):
    Widget.query.search_holding_entities('g-1" OR *:*', "gadget", "widget")
    _q, params = indexer.last_search
    assert params["fq"] == [
        'type:"widget"',
        'widget_gadget:"g\\-1\\"\\ OR\\ \\*\\:\\*"',
    ]


def test_a_datetime_field_is_parsed_back_into_a_datetime(solr_orm, indexer):
    indexer.queue(
        solr_response(
            [{"id": "widget_w-1", "widget_published": "2024-03-01T12:00:00Z"}]
        )
    )
    widget = Widget.query.get("w-1")
    assert widget is not None
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
    assert 'widget_title:"a\\ \\"quoted\\"\\ widget"' in params["fq"]


def test_a_range_facet_is_requested_with_its_bounds(solr_orm, indexer):
    """A range facet asks solr for the prefixed field name and its bounds."""
    facet = FacetRange("size", "Size", Range(0, 100, 25, other="all"))
    Widget.query.search(query="", facets=[facet])
    _q, params = indexer.last_search
    assert params["facet.range"] == ["widget_size"]
    assert params["f.widget_size.facet.range.start"] == 0
    assert params["f.widget_size.facet.range.end"] == 100
    assert params["f.widget_size.facet.range.gap"] == 25
    assert params["f.widget_size.facet.range.other"] == "all"


def test_selected_range_facet_values_become_filter_queries(solr_orm, indexer):
    """A selected bucket is an interval clause built from the bounds this class
    handed the caller, so it reaches solr as syntax rather than as a literal."""
    facet = FacetRange("size", "Size", Range(0, 100, 25))
    facet.set_values(["[25 TO 50]", "[75 TO *]"])
    Widget.query.search(query="", facets=[facet])
    _q, params = indexer.last_search
    assert params["fq"] == ["widget_size:[25 TO 50]", "widget_size:[75 TO *]"]


def test_a_facet_value_carrying_query_syntax_is_neutralised(solr_orm, indexer):
    """A quote, a colon and a paren in a facet value must not leak into the
    filter query and change its meaning."""
    facet = Facet("title", "Title")
    facet.set_values(['a") OR type:gadget OR ("x'])
    Widget.query.search(query="", facets=[facet])
    _q, params = indexer.last_search
    assert params["fq"] == [
        'widget_title:"a\\"\\)\\ OR\\ type\\:gadget\\ OR\\ \\(\\"x"'
    ]


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
    """An entity with no indexed field falls back to the ORM's default query
    fields instead of failing."""
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


def test_all_ids_pages_with_a_cursor(solr_orm, indexer):
    """The ids are paged for, not asked for in one enormous request."""
    indexer.queue(
        solr_response([{"id": "widget_w-1"}], next_cursor="page2"),
        solr_response([{"id": "widget_w-2"}], next_cursor="page2"),
    )

    assert Widget.query.all_ids() == ["w-1", "w-2"]

    assert [params.get("cursorMark") for _q, params in indexer.searches] == [
        "*",
        "page2",
    ]
    assert all(params["rows"] == BATCH_SIZE for _q, params in indexer.searches)
    assert all(params["fl"] == "id" for _q, params in indexer.searches)


def test_the_batch_size_is_a_number(solr_orm):
    """It was the string "500", which solr accepts but arithmetic does not."""
    assert isinstance(BATCH_SIZE, int)


@pytest.mark.parametrize("rows", [0, None])
def test_an_unlimited_search_reports_no_further_page(solr_orm, indexer, rows):
    """``rows`` only reaches solr when truthy, so the document count must not be
    compared against it on exactly the searches that ask for everything."""
    results = Widget.query.search(query="", rows=rows)

    assert results.has_more is False
    _q, params = indexer.last_search
    assert "rows" not in params


def test_delete_restricts_the_query_to_the_entity_type(solr_orm, indexer):
    Widget.query.delete("widget_title:obsolete")
    assert indexer.deleted[-1]["q"] == "widget_title:obsolete AND type:widget"


def test_delete_commits_only_when_asked(solr_orm, indexer):
    Widget.query.delete("widget_title:obsolete")
    assert indexer.commits == []
    Widget.query.delete("widget_title:obsolete", commit=True)
    assert len(indexer.commits) == 1


def _automatic_queries(solr_orm, order):
    """Build a SolrAutomaticQuery per entity class, in the given order."""
    return {
        entity_class.__name__.lower(): SolrAutomaticQuery(entity_class, solr_orm)
        for entity_class in order
    }


@pytest.mark.parametrize("order", [(Widget, Gadget), (Gadget, Widget)])
def test_each_automatic_query_keeps_its_own_boost(indexer, app_config, order):
    """The settings are resolved on the instance, so the entity constructed
    first cannot poison the ones after it -- in either order."""
    solr_orm = SolrORM(
        Settings.from_mapping(
            {
                **app_config,
                "SOLR_BOOST": {"widget": "widget_title^5", "gadget": "gadget_title^9"},
                "SOLR_DEFAULT_SORT": {"widget": "size", "gadget": "title"},
            }
        )
    )
    solr_orm.indexer = indexer
    queries = _automatic_queries(solr_orm, order)
    assert queries["widget"].BOOST == "widget_title^5"
    assert queries["gadget"].BOOST == "gadget_title^9"
    assert queries["widget"].DEFAULT_SORT == "size"
    assert queries["gadget"].DEFAULT_SORT == "title"
    # and the shared class is left as it was declared
    assert SolrAutomaticQuery.BOOST is None
    assert SolrAutomaticQuery.DEFAULT_SORT == ""


def test_the_boost_defaults_to_the_entitys_own_field_prefix(solr_orm):
    """Without configuration each entity falls back on its own prefix, rather
    than on whichever entity happened to be built first."""
    queries = _automatic_queries(solr_orm, (Widget, Gadget))
    assert queries["gadget"].BOOST == "gadget_title^5 gadget_text_^1"


def test_search_sends_the_instance_boost_as_qf(solr_orm, indexer):
    """search() must read the resolved instance value, not the class default."""
    _automatic_queries(solr_orm, (Widget,))
    gadget_query = SolrAutomaticQuery(Gadget, solr_orm)
    gadget_query.search("anything")
    _q, params = indexer.last_search
    assert params["qf"] == "gadget_title^5 gadget_text_^1"


def test_get_facets_builds_a_facet_per_declared_attribute(solr_orm):
    facets = Widget.query.get_facets([("title", "Title"), ("absent", "Absent")])
    assert list(facets) == ["title"]
    assert facets["title"].field_name == "title"
    assert facets["title"].label == "Title"
    assert facets["title"].default_values == []


def test_get_facets_takes_the_default_values_from_the_caller(solr_orm):
    """Default selected values are the host's to name -- no attribute name gets
    special treatment."""
    facets = Widget.query.get_facets([("title", "Title", ["bolt"])])
    assert facets["title"].default_values == ["bolt"]
