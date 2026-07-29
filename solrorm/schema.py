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

    Every call to the schema api goes through this class. The C{create_*} and
    C{update_*} methods raise L{requests.HTTPError} when solr refuses the
    change; the ones that are expected to be attempted speculatively -- adding a
    copy field that may already be there, for instance -- return a boolean and
    log solr's own explanation instead, so that one refusal does not abandon the
    rest of the schema.
    """

    def __init__(self, url: str) -> None:
        """
        @param url: url of the schema api of the collection to administer
        """
        self.url = url

    def _report(self, response, message: str) -> bool:
        """
        Log why solr refused a request, if it did.

        @param response: the requests response of a schema api call
        @param message: what was being attempted, e.g. C{could not add field x}
        @return: True if solr accepted the request
        """
        if response.ok:
            return True
        logger.warning("%s: %s", message, _solr_error(response))
        return False

    def _raise_for_refusal(self, response, message: str) -> None:
        """
        Raise carrying the reason solr refused a request, if it did.

        A bare C{raise_for_status} would discard the body, leaving the caller
        with an opaque 400 -- and the body is where solr explains itself.

        @param response: the requests response of a schema api call
        @param message: what was being attempted, e.g. C{could not add field x}
        @raise requests.HTTPError: if solr refused the request
        """
        if response.ok:
            return
        raise HTTPError(f"{message}: {_solr_error(response)}", response=response)

    def field_exists(self, field_name: str) -> bool:
        """
        Whether the schema already declares a field.

        @param field_name: name of the solr field, e.g. C{widget_title}
        @return: True if solr knows the field
        """
        return requests.get(f"{self.url}/fields/{field_name}").ok

    def fields(self) -> list[str]:
        """
        The names of every field in the schema.

        @return: the field names, empty if solr could not be asked
        """
        ret = requests.get(f"{self.url}/fields")
        if not ret.ok:
            logger.warning(
                "could not list the fields of the schema: %s", _solr_error(ret)
            )
            return []
        return [field["name"] for field in ret.json().get("fields", [])]

    def field_type(self, field_name: str) -> str | None:
        """
        The type solr records for a field.

        @param field_name: name of the solr field, e.g. C{widget_title}
        @return: the field type, or None if the field is not in the schema
        """
        ret = requests.get(f"{self.url}/fields/{field_name}")
        if not ret.ok:
            return None
        return ret.json()["field"]["type"]

    def field_type_exists(self, type_name: str) -> bool:
        """
        Whether the schema already declares a field type.

        @param type_name: name of the solr field type, e.g. C{autocomplete_text}
        @return: True if solr knows the field type
        """
        return requests.get(f"{self.url}/fieldtypes/{type_name}").ok

    def create_field_type(self, definition: dict) -> bool:
        """
        Create a solr field type.

        @param definition: the C{add-field-type} body, name and analyzer included
        @return: True if solr accepted it; a refusal is logged, not raised
        """
        logger.debug("creating field type %s", definition.get("name"))
        ret = requests.post(self.url, json={"add-field-type": definition})
        return self._report(
            ret, f"could not create field type {definition.get('name')}"
        )

    def copy_fields(self) -> list[dict[str, str]]:
        """
        The copy field directives the schema currently holds.

        Read back from the live schema rather than derived from the
        configuration: applications may add copy fields of their own, and a
        directive left behind makes its source field undeletable.

        @return: one C{{"source": ..., "dest": ...}} mapping per directive,
            empty if solr could not be asked
        """
        ret = requests.get(f"{self.url}/copyfields", params={"wt": "json"})
        if not ret.ok:
            logger.warning(
                "could not list the copy fields of the schema: %s", _solr_error(ret)
            )
            return []
        return [
            {"source": copy_field["source"], "dest": copy_field["dest"]}
            for copy_field in ret.json().get("copyFields", [])
        ]

    def add_copy_field(self, source: str, dest: str) -> bool:
        """
        Copy one field into another at index time.

        @param source: the field to copy from
        @param dest: the field to copy into
        @return: True if solr accepted it; a refusal is logged, not raised
        """
        logger.debug("copying field %s into %s", source, dest)
        ret = requests.post(
            self.url, json={"add-copy-field": {"source": source, "dest": dest}}
        )
        return self._report(ret, f"could not copy {source} into {dest}")

    def delete_copy_fields(self, directives: list[dict[str, str]]) -> bool:
        """
        Delete copy field directives.

        @param directives: the C{{"source": ..., "dest": ...}} mappings to drop
        @return: True if solr accepted them; a refusal is logged, not raised
        """
        if not directives:
            return True
        logger.debug("deleting %d copy field directive(s)", len(directives))
        ret = requests.post(self.url, json={"delete-copy-field": directives})
        return self._report(ret, "could not delete the copy fields")

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
        self._raise_for_refusal(ret, f"could not create field {field_name}")

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
        self._raise_for_refusal(ret, f"could not update field {field_name}")

    def delete_fields(self, field_names: list[str]) -> bool:
        """
        Delete several fields in one request.

        Unlike L{delete_field} this reports a refusal instead of raising: it is
        used to clear fields that may legitimately not be there.

        @param field_names: the fields to delete
        @return: True if solr accepted the request
        """
        if not field_names:
            return True
        logger.debug("deleting fields %s", ", ".join(field_names))
        ret = requests.post(
            self.url,
            json={"delete-field": [{"name": name} for name in field_names]},
        )
        return self._report(ret, f"could not delete fields {', '.join(field_names)}")

    def delete_field(self, field_name: str) -> None:
        """
        Delete a solr field
        @param field_name: the field to delete
        @return: raises an exception if not successful
        """
        logger.debug("deleting field %s", field_name)
        ret = requests.post(self.url, json={"delete-field": {"name": field_name}})
        # solr explains the refusal in the body -- a copy field still referring
        # to the field, for instance
        self._raise_for_refusal(ret, f"could not delete field {field_name}")
