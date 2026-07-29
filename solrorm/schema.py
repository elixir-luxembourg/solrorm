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
 solrorm.schema
 --------------

Module containing the SolrSchemaAdmin class

"""

import logging

import requests
from requests import HTTPError

logger = logging.getLogger(__name__)


def _solr_error(response) -> str:
    """
    Extract the reason solr rejected a schema request.

    @param response: the requests response of a schema api call
    @return: the messages solr reported, falling back to the raw body
    """
    try:
        error = response.json().get("error", {})
    except ValueError:
        return response.text
    messages = [
        message
        for detail in error.get("details", [])
        for message in detail.get("errorMessages", [])
    ]
    return "; ".join(message.strip() for message in messages) or error.get(
        "msg", response.text
    )


class SolrSchemaAdmin:
    """
    Class to manipulate solr schema
    Create and delete fields
    """

    def __init__(self, url: str):
        """
        @param url: url of the schema api of the collection to administer
        """
        self.url = url

    def create_field(
        self,
        field_name: str,
        field_type: str,
        index: bool = True,
        store: bool = False,
        multivalued: bool = False,
    ) -> None:
        """
        Create a solr field
        @param field_name: name of the field to create
        @param field_type: type of the field to create
        @param index: should the field be marked as indexed
        @param store: should the field be marked as stored
        @param multivalued: should the field be marked as multivalued
        """
        logger.debug("creating field %s", field_name)
        json_create = {
            "add-field": {
                "name": field_name,
                "type": field_type,
                "stored": store,
                "indexed": index,
                "multiValued": multivalued,
            }
        }
        ret = requests.post(self.url, json=json_create)
        ret.raise_for_status()

    def update_field(
        self,
        field_name: str,
        field_type: str,
        index: bool = True,
        store: bool = False,
        multivalued: bool = False,
    ) -> None:
        """
        Update a solr field
        @param field_name: name of the field to update
        @param field_type: type of the field to update
        @param index: should the field be marked as indexed
        @param store: should the field be marked as stored
        @param multivalued: should the field be marked as multivalued
        """
        logger.debug("updating field %s", field_name)
        ret = requests.post(
            self.url,
            json={
                "replace-field": {
                    "name": field_name,
                    "type": field_type,
                    "stored": store,
                    "indexed": index,
                    "multiValued": multivalued,
                }
            },
        )
        ret.raise_for_status()

    def delete_field(self, field_name: str) -> None:
        """
        Delete a solr field
        @param field_name: the field to delete
        @return: raises an exception if not successful
        """
        logger.debug("deleting field %s", field_name)
        ret = requests.post(self.url, json={"delete-field": {"name": field_name}})
        if not ret.ok:
            # solr explains the refusal in the body (a copy field still
            # referring to the field, for instance); raise_for_status alone
            # would discard it and leave only an opaque 400.
            raise HTTPError(
                f"could not delete field {field_name}: {_solr_error(ret)}",
                response=ret,
            )
