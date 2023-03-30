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

"""The room DB Model."""

from typing import TYPE_CHECKING

from data.base.node import Field, Node
from data.exit import Direction
from data.handler.coordinates import CoordinateHandler
from data.handler.description import DescriptionHandler
from data.handler.exits import ExitHandler

if TYPE_CHECKING:
    from data.character import Character


class Room(Node):

    """Node to represent a room."""

    barcode: str = Field(bpk=True, default="unknown", unique=True)
    title: str = "no title"
    description: DescriptionHandler = Field(default_factory=DescriptionHandler)
    coordinates: CoordinateHandler = Field(default_factory=CoordinateHandler)
    exits: ExitHandler = Field(default_factory=ExitHandler)

    def look(self, character: "Character") -> str:
        """The character wants to look at this room.

        Args:
            character (Character): who looks at this room.

        """
        description = self.description.format()
        exits = self.exits.get_visible_by(character)
        if exits:
            exits = "Obvious exits: " + ", ".join(
                [exit.get_name_for(character) for exit in exits]
            )
        else:
            exits = "There is no obvious exit."

        lines = []

        if character.permissions.has("admin"):
            ident = f"# {self.barcode}"
            if (coordinates := getattr(self, "coordinates", None)) is not None:
                ident += f" ({coordinates.rounded})"
            lines += [ident, ""]

        lines += [
            self.title,
            "",
            description,
            "",
            exits,
        ]

        return "\n".join(lines)

    def create_neighbor(
        self,
        direction: Direction,
        barcode: str | None = None,
        title: str | None = None,
    ) -> "Room":
        """Create a room in the given direction.

        This is primarly used by builders to extend the world.

        Args:
            direction (Direction): the direction in which to build.
            barcode (str or None): the new room's barcode.  If not set,
                    it will try to find one.
            title (str or None): the new room's title.  If not set, it will
                    use the current room's title.

        Returns:
            new_room (Room): the newly-created room.

        """
        if self.exits.has(direction):
            raise ValueError(f"the direction {direction} is already used")

        title = self.title if title is None else title
        if barcode is None:
            barcode = self.find_next_barcode(self.barcode)

        destination = type(self).create(barcode=barcode, title=title)

        # If coordinates are implemented, update the neighbor.
        if coordinates := getattr(self, "coordinates", None):
            if coordinates:
                projected = coordinates.project(direction)
                destination.coordinates.update(*projected)

        # Create exits.
        self.exits.add(direction, destination, direction.value)

        return destination

    @classmethod
    def find_next_barcode(cls, barcode: str) -> str:
        """Find the next barcode, if possible.

        Args:
            barcode (str): the old barcode.

        Returns:
            barcode (str): the new (unique) barcode.

        """
        barcodes = cls.get_attributes("barcode")

        try:
            prefix, suffix = barcode.rsplit(":", 1)
        except ValueError:
            prefix, suffix = "", barcode

        while suffix and suffix[-1].isdigit():
            suffix = suffix[:-1]

        i = 1
        prefix = f"{prefix}:" if prefix else ""
        while (barcode := f"{prefix}{suffix}{i}") in barcodes:
            i += 1

        return barcode
