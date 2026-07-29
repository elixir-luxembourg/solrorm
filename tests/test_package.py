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
"""Tests for the public surface of the ``solrorm`` package itself.

Users import from ``solrorm`` rather than from its modules, so the re-exports
are part of the API and worth pinning.
"""

from importlib import metadata
from pathlib import Path

import pytest

import solrorm

PUBLIC_NAMES = [
    "Facet",
    "FacetRange",
    "Range",
    "Settings",
    "SolrAutomaticQuery",
    "SolrBinaryField",
    "SolrBooleanField",
    "SolrCaseInsensitiveStringField",
    "SolrDateTimeField",
    "SolrEntity",
    "SolrEntityNotFound",
    "SolrField",
    "SolrFloatField",
    "SolrForeignKeyField",
    "SolrIntField",
    "SolrJsonField",
    "SolrLongField",
    "SolrORM",
    "SolrORMError",
    "SolrQuery",
    "SolrQueryException",
    "SolrResults",
    "SolrSchemaAdmin",
    "SolrTextField",
    "escape_solr_value",
]


@pytest.mark.parametrize("name", PUBLIC_NAMES)
def test_the_name_is_reachable_from_the_package_root(name):
    assert getattr(solrorm, name) is not None
    assert name in solrorm.__all__


def test_all_lists_nothing_that_is_missing():
    for name in solrorm.__all__:
        assert hasattr(solrorm, name), name


def test_the_distribution_version_comes_from_the_package():
    """`pyproject.toml` reads the version from `solrorm.__version__`, so the
    installed distribution metadata and the attribute cannot drift apart."""
    assert metadata.version("solrorm") == solrorm.__version__


def test_the_package_ships_its_type_annotations():
    assert (Path(solrorm.__file__).parent / "py.typed").is_file()
