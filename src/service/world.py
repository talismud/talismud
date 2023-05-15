# Copyright (c) 2022, LE GOFF Vincent
# All rights reserved.

# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions are met:

# 1. Redistributions of source code must retain the above copyright notice,
#    this list of conditions and the following disclaimer.

# 2. Redistributions in binary form must reproduce the above copyright notice,
#    this list of conditions and the following disclaimer in the documentation
#    and/or other materials provided with the distribution.

# 3. Neither the name of the copyright holder nor the names of its
#    contributors may be used to endorse or promote products derived from
#    this software without specific prior written permission.

# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"
# AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
# IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE
# ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS
# BE LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY,
# OR CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF
# SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS
# INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN
# CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE)
# ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED
# OF THE POSSIBILITY OF SUCH DAMAGE.

"""World service, here to handle blueprints."""

from pathlib import Path
from typing import Any

from dynaconf import settings

import yaml

from data.base.blueprint import Blueprint, logger
from service.base import BaseService


# Setup the YAML parser/representer.
def str_presenter(dumper, data):
    """Force using the | format with multiline strings."""
    if len(data.splitlines()) > 1:  # check for multiline string
        return dumper.represent_scalar(
            "tag:yaml.org,2002:str", data, style="|"
        )

    return dumper.represent_scalar("tag:yaml.org,2002:str", data)


yaml.add_representer(str, str_presenter)


class Service(BaseService):

    """World service, to handle blueprints."""

    name = "world"

    async def init(self):
        """Asynchronously initialize the service.

        This method should be overridden in subclasses.  It is called by
        `start`` before sub-services are created.  It plays the role of
        an asynchronous constructor for the service, and service attributes
        often are created there for consistency.

        """
        self.blueprints = {}

    async def setup(self):
        """Set the MudIO up."""
        Blueprint.service = self
        self.load_blueprints()
        data = self.parent.services["data"]

        if settings.BLUEPRINT_AUTO_APPLY:
            logger.debug("Handling priority objects in blueprints")
            for blueprint in self.blueprints.values():
                with data.engine.session.begin():
                    blueprint.apply()

            # Apply delayed blueprints.
            logger.debug("Handling delayed objects in blueprints")
            for blueprint in self.blueprints.values():
                with data.engine.session.begin():
                    blueprint.complete()

    async def cleanup(self):
        """Clean the service up before shutting down."""

    def load_blueprints(self):
        """Load all blueprints."""
        world_dir = (Path() / "../world").resolve()
        for file_path in world_dir.rglob("*.yml"):
            if file_path.is_dir():
                logger.warning(
                    f"{file_path} appears like a world file but is a directory"
                )
                continue

            # Try and read this file.
            try:
                with file_path.open("r", encoding="utf-8") as file:
                    content = file.read()
            except Exception:
                logger.exception(f"Cannot read {file_path}:")
            else:
                try:
                    blueprint = yaml.safe_load_all(content)
                except Exception:
                    logger.exception(f"Cannot parse {file_path}:")
                else:
                    relative = file_path.relative_to(world_dir)
                    bp_name = "/".join(relative.parts[:-1])
                    if bp_name:
                        bp_name += "/"
                    bp_name += file_path.stem
                    logger.debug(
                        f"Loaded {bp_name} in {file_path} successfully."
                    )

                    blueprint = Blueprint(bp_name, file_path, list(blueprint))
                    self.blueprints[bp_name] = blueprint

    def update_document(
        self, blueprint: str, document_id: int, definition: dict[str, Any]
    ) -> None:
        """Update and save a blueprint.

        Args:
            blueprint (str): the blueprint's unique name.
            document_id (int): the document ID to update.
            definition (dict): the new definition.

        """
        blueprint = self.blueprints[blueprint]
        blueprint.update_document(document_id, definition)
        documents = [
            document.pop("document_id", True) and document
            for document in [dict(d) for d in blueprint.content]
        ]

        with blueprint.file_path.open("w", encoding="utf-8") as file:
            yaml.dump_all(documents, file, sort_keys=False, allow_unicode=True)
