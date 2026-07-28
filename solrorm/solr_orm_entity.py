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
 solrorm.solr_orm_entity
 -------------------

Module containing the SolrEntity class

"""

import base64
import json
import logging
import uuid
from datetime import datetime
from typing import Optional, Any

from .solr_orm_fields import (
    SolrDateTimeField,
    SolrField,
    SolrIntField,
    SolrJsonField,
    SolrBinaryField,
)
from . import config

logger = logging.getLogger(__name__)
# datetime formats for json serialization
DATETIME_FORMAT = "%Y-%m-%dT%H:%M:%S.%fZ"
DATETIME_FORMAT_NO_MICRO = "%Y-%m-%dT%H:%M:%SZ"


class SolrEntity:
    """
    Base class for a solr entity
    Base entity contains a created and modified field
    Provides methods to save, delete, parse ans serialize the entity
    """

    created = SolrDateTimeField("created")
    modified = SolrDateTimeField("modified")
    former_ids = SolrField("former_ids", multivalued=True, indexed=False)
    connector_name = SolrField("connector_name", multivalued=False, indexed=False)

    # dict holding reverse foreign keys references
    reversed_field = {}
    query = None
    _solr_orm = None
    ADD_PREFIX_ID = True

    def __init__(self, entity_id: Optional[str] = None) -> None:
        """
        Initialize a SolrEntity instance setting its id or generating one if none is provided.
        Generated id is based on uuid.uuid1 method.
        Also initialize the created and modified date to current datetime.
        @param entity_id: entity id or None if id should be generated
        @type entity_id:
        """
        for attribute_name in self._solr_fields.keys():
            setattr(self, attribute_name, None)
        if entity_id is None:
            self.id = str(uuid.uuid1())
        else:
            self.id = entity_id
        self.created = datetime.now()
        self.modified = self.created

    @classmethod
    def plural_name(cls) -> str:
        """
        Plural form of the entity name for display
        @return: a string representing the plural version of the entity name
        """
        return cls.__name__.lower() + "s"

    def __getattr__(self, attribute: str) -> Any:
        """
        check if we have foreign key reference and resolve it if it's the case
        @todo: ADD caching
        @param attribute: name of the attribute
        @return: list of entities if many to many relationship
        """
        elements = attribute.rsplit("_")
        suffix = elements[-1]
        prefix = "".join(elements[0:-1])
        if suffix in ["entities", "entity"]:
            # check if it's a reversed relationship
            if prefix in self.reversed_field:
                (
                    source_entity_name,
                    field_name,
                    field_reversed_multiple,
                ) = self.reversed_field[prefix]
                source_entity_class = config.get("entities").get(source_entity_name)
                holding_entities = source_entity_class.query.search_holding_entities(
                    field_name=field_name,
                    target_entity_id=self.id,
                    source_entity_type=source_entity_name,
                ).entities
                if field_reversed_multiple or not holding_entities:
                    return holding_entities
                else:
                    return holding_entities[0]
            else:
                entities_ids = getattr(self, prefix, [])
                results = []
                if entities_ids:
                    # get foreign entity type
                    linked_entity_name = self._solr_fields[prefix].linked_entity_name
                    linked_entity_class = config["entities"][linked_entity_name]
                    for entity_id in entities_ids:
                        linked_entity = linked_entity_class.query.get(entity_id)
                        if linked_entity is not None:
                            results.append(linked_entity)
            return results
        raise AttributeError(
            "'{}' object has no attribute '{}'".format(
                self.__class__.__name__, attribute
            )
        )

    def save(self, commit=False, soft_commit=False) -> str:
        """
        Create dict representation of the entity instance and index it in solr
        Beware that this method doesn't trigger a commit
        @return: a string containing the solr response body
        """
        entity_dict = self.to_dict()
        entity_type = self.__class__.__name__.lower()
        if self.ADD_PREFIX_ID:
            entity_dict["id"] = entity_type + "_" + entity_dict["id"]
        entity_dict["type"] = entity_type
        logger.info("Indexing entity %s (%s)", self.id, entity_type)
        for field_name, info in self.reversed_field.items():
            source_entity_class_name, reversed_field_name, reversed_multiple = info
            field_value = getattr(self, field_name, None)
            if field_value and self.id:
                # get linked entity     from solr
                source_entity_class = config["entities"].get(source_entity_class_name)
                source_entity = source_entity_class.query.get(field_value)
                if source_entity:
                    entities = getattr(source_entity, reversed_field_name, []) or []
                    if self.id not in entities:
                        entities.append(self.id)
                        setattr(source_entity, reversed_field_name, entities)
                        source_entity.save(commit=commit, soft_commit=soft_commit)
        result_add = self._solr_orm.add(entity_dict)
        if commit or soft_commit:
            self._solr_orm.commit(soft_commit=soft_commit)
        return result_add

    def to_dict(self, add_prefix=True) -> dict:
        """
        Create a dict containing all attributes as key and the field values as value
        @return: dict representation of the entity instance
        """
        entity_dict = {}
        entity_type = self.__class__.__name__.lower()
        for attribute_name, field in self.__class__._solr_fields.items():
            attribute_value = getattr(self, attribute_name, None)
            if isinstance(attribute_value, SolrField):
                attribute_value = None
            if add_prefix:
                key = entity_type + "_" + field.name
            else:
                key = field.name
            if (
                isinstance(field, SolrBinaryField)
                and attribute_value
                and isinstance(attribute_value, bytes)
            ):
                attribute_value = base64.b64encode(attribute_value).decode("ascii")
            if isinstance(field, SolrJsonField):
                if field.model:
                    if attribute_value is not None:
                        for count, value in enumerate(attribute_value):
                            attribute_value[count] = json.dumps(value.to_json())
                else:
                    attribute_value = json.dumps(attribute_value)
            entity_dict[key] = attribute_value
        if self.id is None or isinstance(self.id, SolrField):
            self.id = str(uuid.uuid1())
        entity_dict["id"] = self.id.replace(" ", "_")
        return entity_dict

    def to_api_dict(self) -> dict:
        """
        Similar to method to_dict but can be used to restrict the list of fields exported via api endpoints.
        @return: dict representation of the entity instance
        """
        return self.__dict__

    def delete(self) -> str:
        """
        Delete an entity from Solr
        Beware that this method doesn't trigger a commit
        @return:
        """
        logger.info("Deleting entity %s", self.id)
        return self._solr_orm.delete(self.id)

    @classmethod
    def from_json(cls, entity_json: dict) -> "SolrEntity":
        """
        Create a SolrEntity instance based on a dict containing the fields names and values
        @param entity_json: source dict
        @return: new SolrEntity instance
        """
        new_instance = cls()
        entity_type = cls.__name__.lower()
        for attribute_name, field in cls._solr_fields.items():
            solr_value = entity_json.get(entity_type + "_" + field.name)
            if solr_value is not None and field.type == "date":
                try:
                    solr_value = datetime.strptime(solr_value, DATETIME_FORMAT)
                except ValueError:
                    solr_value = datetime.strptime(solr_value, DATETIME_FORMAT_NO_MICRO)
            if solr_value is not None and isinstance(field, SolrIntField):
                solr_value = int(solr_value)
            if solr_value is not None and isinstance(field, SolrBinaryField):
                solr_value = base64.b16decode(solr_value)
            setattr(new_instance, attribute_name, solr_value)
        if "id" in entity_json:
            new_instance.id = entity_json.get("id")
        return new_instance

    def set_computed_values(self):
        pass
