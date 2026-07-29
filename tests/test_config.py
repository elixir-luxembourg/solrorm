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
"""Tests for the configuration accessor."""

import pytest

import solrorm


def test_get_returns_the_default_when_absent():
    assert solrorm.config.get("MISSING") is None
    assert solrorm.config.get("MISSING", 4) == 4


def test_lookup_and_membership(configured):
    assert solrorm.config["SOLR_COLLECTION"] == "test_collection"
    assert "entities" in solrorm.config
    assert "MISSING" not in solrorm.config
    with pytest.raises(KeyError):
        solrorm.config["MISSING"]


def test_a_reference_is_stored_not_a_copy(configured):
    """
    Values the host sets after configure() must stay visible.

    This is what lets an application register its ``entities`` registry after
    calling configure(). T3 replaces this with an eagerly-read Settings object,
    at which point this test documents the *old* contract and should be
    replaced rather than kept passing.
    """
    configured["ADDED_LATER"] = "visible"
    assert solrorm.config.get("ADDED_LATER") == "visible"
