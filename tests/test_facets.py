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
"""Tests for the facet configuration objects."""

from solrorm.facets import Facet, FacetRange, Range


def test_intervals_divide_the_range_evenly():
    assert list(Range(0, 10, 5).iter_intervals()) == [(0, 5), (5, 10)]


def test_a_trailing_partial_interval_overshoots_the_end():
    """The last interval is a whole gap wide even past ``end`` -- solr's own
    range faceting behaves the same way."""
    assert list(Range(0, 10, 4).iter_intervals()) == [(0, 4), (4, 8), (8, 12)]


def test_a_range_shorter_than_the_gap_yields_one_interval():
    assert list(Range(5, 7, 10).iter_intervals()) == [(5, 15)]


def test_set_values_clears_the_default_marker():
    facet = Facet("title", "Title", default_values=["Active"])
    facet.set_values(["Retired"])
    assert facet.values == ["Retired"]
    assert facet.using_default is False


def test_setting_the_default_values_marks_the_facet_as_default():
    facet = Facet("title", "Title", default_values=["Active"])
    facet.set_values(["Active"])
    assert facet.using_default is True


def test_use_default_applies_the_default_values():
    facet = Facet("title", "Title", default_values=["Active"])
    facet.use_default()
    assert facet.values == ["Active"]
    assert facet.using_default is True


def test_use_default_without_defaults_leaves_the_facet_empty():
    facet = Facet("title", "Title")
    facet.use_default()
    assert facet.values == []
    assert facet.using_default is False


def test_a_facet_range_carries_its_range():
    facet_range = Range(0, 10, 5)
    facet = FacetRange("year", "Year", facet_range)
    assert facet.range is facet_range
    assert facet.field_name == "year"
