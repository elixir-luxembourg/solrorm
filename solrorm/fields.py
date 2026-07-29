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
 solrorm.fields
 --------------

Module containing the SolrField class and subclasses for different fields type

"""

import logging
from typing import Optional

logger = logging.getLogger(__name__)


class SolrField:
    """
    Class holding the solr field definition:
        - indexed: should the field be indexed by solr to allow search
        - stored: should the original field value be stored in solr to allow value retrieval
        - name: field name, can contain only alphanumeric characters and _
        - field_type: field type, see solr documentation for list of types, default type is string
        - multivalued: can the field contain multiple values (list)
    """

    def __init__(
        self,
        name: str,
        attribute_name: Optional[str] = None,
        field_type: str = "string",
        indexed: bool = True,
        stored: bool = True,
        multivalued: object = False,
    ) -> None:
        self.multivalued = multivalued
        self.indexed = indexed
        self.stored = stored
        self.name = name
        self.type = field_type
        self.attribute_name = attribute_name or name


class SolrCaseInsensitiveStringField(SolrField):
    """
    SolrField subclass setting solr type to lowercase
    """

    def __init__(
        self,
        name: str,
        attribute_name: Optional[str] = None,
        indexed: bool = True,
        stored: bool = True,
        multivalued: bool = False,
    ) -> None:
        super().__init__(
            name, attribute_name, "lowercase", indexed, stored, multivalued
        )


class SolrDateTimeField(SolrField):
    """
    SolrField subclass setting solr type to pdate
    """

    def __init__(
        self,
        name: str,
        attribute_name: Optional[str] = None,
        indexed: bool = True,
        stored: bool = True,
        multivalued: bool = False,
    ) -> None:
        if multivalued:
            super().__init__(
                name, attribute_name, "pdates", indexed, stored, multivalued
            )
        else:
            super().__init__(
                name, attribute_name, "pdate", indexed, stored, multivalued
            )


class SolrLongField(SolrField):
    """
    SolrField subclass setting solr type to plong
    """

    def __init__(
        self,
        name: str,
        attribute_name: Optional[str] = None,
        indexed: bool = True,
        stored: bool = True,
        multivalued: bool = False,
    ) -> None:
        if multivalued:
            super().__init__(
                name, attribute_name, "plongs", indexed, stored, multivalued
            )
        else:
            super().__init__(
                name, attribute_name, "plong", indexed, stored, multivalued
            )


class SolrFloatField(SolrField):
    """
    SolrField subclass setting solr type to pfloat
    """

    def __init__(
        self,
        name: str,
        attribute_name: Optional[str] = None,
        indexed: bool = True,
        stored: bool = True,
        multivalued: bool = False,
    ) -> None:
        if multivalued:
            super().__init__(
                name, attribute_name, "pfloats", indexed, stored, multivalued
            )
        else:
            super().__init__(
                name, attribute_name, "pfloat", indexed, stored, multivalued
            )


class SolrBinaryField(SolrField):
    """
    SolrField subclass setting solr type to binary
    """

    def __init__(
        self,
        name: str,
        attribute_name: Optional[str] = None,
        indexed: bool = False,
        stored: bool = True,
        multivalued: bool = False,
    ) -> None:
        super().__init__(name, attribute_name, "binary", indexed, stored, multivalued)


class SolrIntField(SolrField):
    """
    SolrField subclass setting solr type to pint
    """

    def __init__(
        self,
        name: str,
        attribute_name: Optional[str] = None,
        indexed: bool = True,
        stored: bool = True,
        multivalued: bool = False,
    ) -> None:
        if multivalued:
            super().__init__(
                name, attribute_name, "pints", indexed, stored, multivalued
            )
        else:
            super().__init__(name, attribute_name, "pint", indexed, stored, multivalued)


class SolrTextField(SolrField):
    """
    SolrField subclass setting solr type to text_end
    """

    def __init__(
        self,
        name: str,
        attribute_name: Optional[str] = None,
        indexed: bool = True,
        stored: bool = True,
        multivalued: bool = False,
    ) -> None:
        super().__init__(name, attribute_name, "text_en", indexed, stored, multivalued)


class SolrJsonField(SolrField):
    """
    SolrField subclass setting solr type to text, meant for storing JSON
    """

    def __init__(
        self,
        name: str,
        attribute_name: Optional[str] = None,
        indexed: bool = True,
        stored: bool = True,
        multivalued: bool = False,
        model: object = None,
    ) -> None:
        self.model = model
        super().__init__(name, attribute_name, "text_en", indexed, stored, multivalued)


class SolrBooleanField(SolrField):
    """
    SolrField subclass setting solr type to boolean
    """

    def __init__(
        self,
        name: str,
        attribute_name: Optional[str] = None,
        indexed: bool = True,
        stored: bool = True,
        multivalued: bool = False,
    ) -> None:
        super().__init__(name, attribute_name, "boolean", indexed, stored, multivalued)


class SolrForeignKeyField(SolrField):
    """
    SolrField subclass for links between entities
    """

    def __init__(
        self,
        name: str,
        entity_name: str,
        attribute_name: Optional[str] = None,
        multivalued: bool = False,
        reversed_by: "SolrEntity" = None,  # noqa: F821
        reversed_multiple: bool = False,
    ) -> None:
        self.linked_entity_name = entity_name
        self.reversed_by = reversed_by
        self.reversed_multiple = reversed_multiple
        super().__init__(name, attribute_name, "string", True, True, multivalued)
