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
 solrorm.exceptions
 ------------------

Exceptions raised by the Solr ORM.
"""

__author__ = "Valentin Grouès"


class SolrORMError(Exception):
    """Base class for all solrorm errors."""

    pass


class SolrQueryException(SolrORMError):
    """Raised when a Solr query fails."""

    pass


class SolrEntityNotFound(SolrORMError):
    """Raised when a lookup finds no entity.

    The library itself never raises this: `SolrQuery.get` and
    `SolrQuery.get_by_slug` return `None`. It is provided for hosts that
    prefer an exception at their own lookup boundary.
    """

    pass
