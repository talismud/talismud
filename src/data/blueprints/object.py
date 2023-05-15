# Copyright (c) 2023, LE GOFF Vincent
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

"""Module containing blueprint models for object."""

from data.blueprints.base import BlueprintModel
from data.object import Object


class ObjectBlueprint(BlueprintModel):

    """Blueprint for object prototypes."""

    name = "object"
    model_path = "data.prototype.object.ObjectPrototype"
    special = {
        "objects": list,
    }

    @classmethod
    def update_objects(cls, logger, prototype, objects):
        """Update the list of objects."""
        from data.room import Room

        for definition in objects:
            barcode = definition.pop("barcode", None)
            if barcode is None:
                continue

            if Object.get(barcode=barcode, raise_not_found=False) is not None:
                continue

            location = definition.pop("location", None)
            if location is not None:
                location = Room.get(barcode=location)
            obj = prototype.create_object_in(
                location, barcode=barcode, setup=False
            )
            logger.info(f"Create {obj!r} in {location!r}")
            for type_def in definition.pop("types", []):
                type_name = type_def.pop("type", None)
                if type_name is None:
                    continue

                o_type = obj.types.get(type_name)
                if o_type is None:
                    continue

                o_type.setup_object(**type_def)
