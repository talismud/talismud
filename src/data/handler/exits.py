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

"""Exit handler, to store room exits."""

from typing import Any, Optional, Type, TYPE_CHECKING

from command.special.exit import ExitCommand
from data.base.blueprint import logger
from data.decorators import lazy_property
from data.direction import Direction
from data.exit import Exit
from data.handler.abc import BaseHandler

if TYPE_CHECKING:
    from data.character import Character
    from data.room import Room


class ExitHandler(BaseHandler):

    """A handler for exits."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._exits = None

    def __iter__(self):
        self.load_exits()
        return iter(self.all)

    @property
    def all(self) -> tuple[Exit]:
        """Only return linked exits in the direction order."""
        self.load_exits()
        exits = []
        for direction in Direction:
            exit = self._exits.get(direction)
            if exit:
                exits.append(exit)

        return tuple(exits)

    @lazy_property
    def commands(self):
        """Return the exit commands for this room."""
        return self._refresh_commands()

    @commands.setter
    def commands(self, commands):
        """Modify the dictionary of commands."""

    def get_visible_by(self, character: "Character") -> tuple[Exit]:
        """Only return visible exits by this character."""
        return [exit for exit in self.all if exit.can_see(character)]

    def get(self, direction: Direction) -> Exit | None:
        """Return the exit room in this direction or None.

        Args:
            direction (Direction): the direction in which to test.

        """
        self.load_exits()
        return self._exits.get(direction)

    def has(self, direction: Direction) -> bool:
        """Return whether this room has an exit in this direction.

        Args:
            direction (Direction): the direction in which to test.

        """
        self.load_exits()
        return direction in self._exits

    def get_commands_for(
        self, character: "Character"
    ) -> dict[Direction, Type[ExitCommand]]:
        """Return a filtered dictionary of exit commands for a character.

        Args:
            character (Character): the character to filter.

        Exits that are limited in terms of permissions will not appear,
        so an exit command for a character that cannot traverse it will
        not be created.

        Returns:
            commands (dict): a dictionary of {Direction: ExitCommand].
                    Exits that can not be traversed by a character
                    will not be present in this dictionary.

        """
        return {
            direction: command
            for direction, command in self.commands.items()
            if self.get(direction).can_traverse(character)
        }

    def add(
        self,
        direction: Direction,
        destination: "Room",
        name: str,
        aliases: Optional[set[str]] = None,
        back: bool = True,
    ) -> Exit:
        """Add a new exit, if no exit exists in this direction.

        Args:
            direction (Direction): the direction in which to build this exit.
            destination (Room): the destination of this exit.
            name (str): the exit's name.
            aliases (set, optional): the optional aliases of this exit.
            back (bool, optional): if `true` (the default, creates
                    an exit in the destination linking back to
                    the current room.

        If an exit already exists in this direction, raisess a ValueError.

        """
        self.load_exits()
        if self._exits.get(direction):
            raise ValueError(
                f"an exit already exists in the direction: {direction}"
            )

        origin, _ = self.model
        exit = Exit.create(
            key=direction.value,
            direction=direction,
            origin_id=origin.id,
            destination_id=destination.id,
            name=name,
            aliases=aliases or (),
        )
        self._exits[direction] = exit
        self.commands = self._refresh_commands()
        self.save()

        if back:
            destination.exits.load_exits()
            opposite = direction.opposite
            if not destination.exits.has(opposite):
                destination.exits.add(
                    opposite, origin, opposite.value, back=False
                )

        return exit

    def load_exits(self):
        """Load, if necessary, this room's exit."""
        if self._exits is None:
            room, _ = self.model
            query = (Exit.table.origin_id == room.id) & (
                Exit.table.destination_id.isnot(None)
            )
            exits = Exit.select(query)
            self._exits = {exit.direction: exit for exit in exits}

    def from_blueprint(self, exits: Any) -> None:
        """Create exits from a blueprint."""
        room_cls = type(self.model[0])
        for exit in exits:
            match exit:
                case {
                    "direction": direction,
                    "name": name,
                    "destination": destination,
                }:
                    try:
                        direction = Direction(direction)
                    except ValueError as err:
                        logger.warning(str(err))
                        continue

                    aliases = set(exit.get("aliases", direction.aliases))
                    aliases.remove(name)
                    destination = room_cls.get_or_none(barcode=destination)
                    if destination is None:
                        logger.warning(
                            f"Cannot find the destination {destination} "
                            f"for exit {direction.name}"
                        )
                        continue

                    exit = self.get(direction)
                    if exit is None:
                        self.add(
                            direction,
                            destination,
                            name,
                            aliases=aliases,
                            back=False,
                        )
                    else:
                        exit.destination = destination
                        exit.name = name
                        exit.aliases = aliases

    def _refresh_commands(self) -> dict:
        """Refresh the commands."""
        commands = {}
        for exit in self.all:
            attrs = {
                "name": exit.name,
                "alias": exit.aliases,
                "permissions": "",
                "exit": exit,
            }
            command = type(exit.name, (ExitCommand,), attrs)
            commands[exit.direction] = command

        return commands
