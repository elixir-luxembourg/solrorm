# coding=utf-8
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
 solrorm.config
 --------------

solrorm does not own a Flask (or any other) application. Every setting the
library reads lives on a L{Settings} instance handed to ``SolrORM`` at
construction time, so two collections can be served from one process and no
module-level state is involved.

A host that already keeps its configuration in a mapping (Flask's
``app.config``, say) builds one with L{Settings.from_mapping}.

Settings are read *eagerly*: the ``entities`` registry must be populated before
``SolrORM`` is constructed.
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Mapping, Type

__author__ = "Valentin Grouès"


@dataclass(frozen=True)
class Settings:
    """
    The complete configuration surface of the library.

    @ivar endpoint: solr hostname, port and path, e.g. http://localhost:8983/solr
    @ivar collection: name of the solr collection (core) to work in
    @ivar entities: registry of SolrEntity subclasses by lowercased name
    @ivar fuzzy_search_level: edit distance appended to fuzzy query terms
    @ivar use_cursor_pagination: request a cursor mark instead of start/rows
    @ivar boost: per entity name, the solr C{qf} boost expression
    @ivar default_sort: per entity name, the field to sort on by default
    @ivar query_text_field: per entity name, the fields copied into the
        C{_text_} catch-all; entities absent from the mapping fall back to
        C{SolrORM.DEFAULT_QUERY_FIELDS}
    @ivar query_search_extended: legacy flag, removed by T9 of RELEASE_PLAN.md
    @ivar query_search_extended_2_way_index: legacy flag, removed by T9
    """

    endpoint: str
    collection: str
    entities: Dict[str, Type[Any]] = field(default_factory=dict)
    fuzzy_search_level: int = 4
    use_cursor_pagination: bool = False
    boost: Dict[str, str] = field(default_factory=dict)
    default_sort: Dict[str, str] = field(default_factory=dict)
    query_text_field: Dict[str, List[str]] = field(default_factory=dict)
    # the two flags below bake one application's entity names into the library;
    # they survive only until T9 replaces them with an explicit query_text_field
    query_search_extended: bool = False
    query_search_extended_2_way_index: bool = False

    @classmethod
    def from_mapping(cls, mapping: Mapping[str, Any]) -> "Settings":
        """
        Build settings from a host application's configuration mapping.

        @param mapping: a dict-like object providing the C{SOLR_*} keys and the
            C{entities} registry. C{SOLR_ENDPOINT} and C{SOLR_COLLECTION} are
            required; every other key is optional and falls back to the field
            default.
        @return: the corresponding Settings instance
        """
        values: Dict[str, Any] = {
            "endpoint": mapping["SOLR_ENDPOINT"],
            "collection": mapping["SOLR_COLLECTION"],
        }
        for name, key in (
            ("entities", "entities"),
            ("fuzzy_search_level", "FUZZY_SEARCH_LEVEL"),
            ("use_cursor_pagination", "USE_CURSOR_PAGINATION"),
            ("boost", "SOLR_BOOST"),
            ("default_sort", "SOLR_DEFAULT_SORT"),
            ("query_text_field", "SOLR_QUERY_TEXT_FIELD"),
            ("query_search_extended", "SOLR_QUERY_SEARCH_EXTENDED"),
            (
                "query_search_extended_2_way_index",
                "SOLR_QUERY_SEARCH_EXTENDED_2_WAY_INDEX",
            ),
        ):
            if key in mapping:
                values[name] = mapping[key]
        if "entities" in values:
            # copied, not aliased: the registry is read once, at construction,
            # so a host adding an entity later must not silently be obeyed
            values["entities"] = dict(values["entities"])
        return cls(**values)
