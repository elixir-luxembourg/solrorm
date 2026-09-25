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
 solrorm
 -------

A lightweight Solr ORM: entity mapping, typed fields, faceting and query
building over pysolr. Framework-neutral -- the host application injects its
configuration by handing a :class:`Settings` instance to :class:`SolrORM`.
"""

__author__ = "Valentin Grouès"
__version__ = "0.3.0"

from .config import Settings
from .entity import SolrEntity
from .exceptions import SolrEntityNotFound, SolrORMError, SolrQueryException
from .facets import Facet, FacetRange, Range
from .fields import (
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
from .orm import SolrAutomaticQuery, SolrORM, SolrQuery, SolrResults, escape_solr_value
from .schema import SolrSchemaAdmin

__all__ = [
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
