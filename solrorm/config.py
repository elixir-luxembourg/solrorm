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

solrorm does not own a Flask (or any other) application. The consuming
application injects its configuration once at startup via ``configure(...)``,
and the ORM reads the values it needs through the module-level ``config``
accessor.

A *reference* to the mapping is stored (not a copy), so values that the host
sets after configuration time -- notably the ``entities`` registry and the
``_solr_orm`` instance -- remain visible to the ORM.
"""

__author__ = "Valentin Grouès"


class _Config:
    """Thin, read-only view over the host application's config mapping."""

    def __init__(self) -> None:
        self._data = {}

    def configure(self, mapping) -> None:
        self._data = mapping

    def get(self, key, default=None):
        return self._data.get(key, default)

    def __getitem__(self, key):
        return self._data[key]

    def __contains__(self, key) -> bool:
        return key in self._data


config = _Config()


def configure(mapping) -> None:
    """Point solrorm at the host application's config mapping.

    @param mapping: a dict-like object (e.g. Flask ``app.config``) that
        provides the ``SOLR_*`` settings and the ``entities`` registry.
    """
    config.configure(mapping)
