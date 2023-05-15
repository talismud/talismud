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

"""The object prototype DB Model."""

from typing import TYPE_CHECKING

from data.base.node import Field, Node
from data.decorators import lazy_property
from data.handler.blueprints import BlueprintHandler
from data.handler.namespace import NamespaceHandler
from data.handler.types import TypeHandler
from data.object import Object

if TYPE_CHECKING:
    from data.character import Character


class ObjectPrototype(Node):

    """Node to represent an object prototype."""

    barcode: str = Field(default="unset", bpk=True, unique=True)
    singular: str = "an object"
    plural: str = "objects"
    blueprints: BlueprintHandler = Field(default_factory=BlueprintHandler)
    db: NamespaceHandler = Field(default_factory=NamespaceHandler)
    types: TypeHandler = Field(default_factory=TypeHandler)

    @property
    def stackable(self):
        """Is this prototype stackable?"""
        return self.types.stackable

    @lazy_property
    def used_barcodes(self) -> tuple[str]:
        """Return the list of currently-used object barcodes."""
        object_ids = Object.search_attributes("prototype", self)
        barcodes = Object.get_attributes(
            "barcode", query=Object.table.id.in_(object_ids)
        )
        return tuple(sorted(barcodes))

    @used_barcodes.setter
    def used_barcodes(self, barcodes: tuple[str]) -> None:
        """Update the barcodes, do nothing, just update the cache."""
        pass

    @lazy_property
    def objects(self) -> list["Object"]:
        """Return the list of objects built on this prototype."""
        object_ids = Object.search_attributes("prototype", self)
        return Object.select(Object.table.id.in_(object_ids))

    @objects.setter
    def objects(self, objects: list["Object"]) -> None:
        """Update the objects, do nothing, just update the cache."""
        pass

    def get_name_for(self, character: "Character", number: int = 1) -> str:
        """Return the name for this character in the specified quantity.

        Args:
            character (Character): the character receiving the object's name.
            number (int, optional): the number of objects (default 1).

        Returns:
            name (str): the name to display.

        """
        if number == 1:
            name = self.singular
        else:
            name = f"{number} {self.plural}"

        return name

    def create_object_in(
        self, location: Node, barcode: str | None = None, setup: bool = True
    ) -> Node:
        """Create a new object based on this prototype.

        Args:
            location (Room or container): the new object's future location.
            barcode (str, optional): the barcode to use.
            setup (bool): if True (default), setup the types of the new object.
                    Note that the types will be added regardless, but
                    if `setup` is `False`, `type.setup_object` will not
                    be called on individual types.

        Returns:
            object (Object): the new object.

        """
        if self.types.stackable:
            raise ValueError(
                f"spawning {self} is impossible, one of its type is stackable"
            )

        if barcode is None:
            barcodes = self.used_barcodes
            found = False
            i = 1
            while not found:
                barcode = f"{self.barcode}_{i}"
                if barcode not in barcodes:
                    found = True
                else:
                    i += 1

        obj = Object.create(prototype=self, barcode=barcode)
        self.objects = sorted(self.objects + [obj], key=lambda o: o.barcode)
        self.used_barcodes = tuple(sorted(self.used_barcodes + (barcode,)))
        obj.location = location

        # Copy types.
        for name, _ in self.types:
            obj.types.add(name, quiet=True, save=False)
        obj.types.save()

        # Setup the individual types.
        if setup:
            for _, o_type in obj.types:
                o_type.setup_object()

        return obj
