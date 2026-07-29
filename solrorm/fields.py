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
from typing import Any, overload

logger = logging.getLogger(__name__)


class SolrField:
    """
    Class holding the solr field definition:
        - indexed: should the field be indexed by solr to allow search
        - stored: should the original field value be stored in solr to allow value retrieval
        - name: field name, can contain only alphanumeric characters and _
        - field_type: field type, see solr documentation for list of types, default type is string
        - multivalued: can the field contain multiple values (list)

    A field is a I{descriptor}: declared on a L{SolrEntity} subclass it defines
    the schema, but read on an instance it yields the value that instance
    carries, and assigning to it stores that value. Reading it on the class
    itself still yields the field, which is how the entity's schema is
    collected.
    """

    def __init__(
        self,
        name: str,
        attribute_name: str | None = None,
        field_type: str = "string",
        indexed: bool = True,
        stored: bool = True,
        multivalued: bool = False,
    ) -> None:
        self.multivalued = multivalued
        self.indexed = indexed
        self.stored = stored
        self.name = name
        self.type = field_type
        self.attribute_name = attribute_name or name
        # the attribute the field is declared as, which is the key the value is
        # kept under in the instance dict. Defaults to the field name for a
        # field that is never assigned to a class body.
        self._storage_name = self.attribute_name

    def __set_name__(self, owner: type, name: str) -> None:
        self._storage_name = name

    @overload
    def __get__(self, instance: None, owner: type | None = None) -> "SolrField": ...

    @overload
    def __get__(self, instance: object, owner: type | None = None) -> Any: ...

    def __get__(self, instance, owner=None):
        if instance is None:
            return self
        return instance.__dict__.get(self._storage_name)

    def __set__(self, instance: object, value: Any) -> None:
        instance.__dict__[self._storage_name] = value


class SolrCaseInsensitiveStringField(SolrField):
    """
    SolrField subclass setting solr type to lowercase
    """

    def __init__(
        self,
        name: str,
        attribute_name: str | None = None,
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
        attribute_name: str | None = None,
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
        attribute_name: str | None = None,
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
        attribute_name: str | None = None,
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
        attribute_name: str | None = None,
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
        attribute_name: str | None = None,
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
        attribute_name: str | None = None,
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
        attribute_name: str | None = None,
        indexed: bool = True,
        stored: bool = True,
        multivalued: bool = False,
        model: Any | None = None,
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
        attribute_name: str | None = None,
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
        attribute_name: str | None = None,
        multivalued: bool = False,
        reversed_by: str | None = None,
        reversed_multiple: bool = False,
    ) -> None:
        self.linked_entity_name = entity_name
        self.reversed_by = reversed_by
        self.reversed_multiple = reversed_multiple
        super().__init__(name, attribute_name, "string", True, True, multivalued)
