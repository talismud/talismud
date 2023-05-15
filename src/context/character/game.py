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

"""Default context for logged-in characters.

This context is responsible for handling commands, exits and channels.
It always is the default context in the character's command stack
and cannot be entirely removed, though other contexts can be added
and they can "block" user input to make sure it is not sent to the game
context at all.

Note:
    This context can seem close to the "connection.game" context,
    yet the two are really different: the "connection.game" context
    forwards to the character's command stack.  The "character.game"
    context, on the other hand, is the default active context on
    the context stack: therefore, user input is, by default, forwarded
    from "connection.game" to "character.game", but it is possible
    to add new contexts on the character's context stack.  The
    "character.game" context is always available to the context
    stack, but another context might be active at the time.

"""

from dynaconf import settings

from command.base import Command
from context.base import Context


class Game(Context):

    """Default context called when the user is logged in to a character."""

    def get_prompt(self) -> str:
        """Return the active context prompt."""
        return "HP: 100"

    def greet(self) -> str:
        """Return the active context's greeting."""
        room = self.character.room
        if room:
            return room.look(self.character)

        return "You are floating in the void..."

    def handle_input(self, user_input: str):
        """Route the user input to the context stack."""
        character = self.character
        commands = []

        # Add exit commands (specific to the room).
        if (room := character.location) is not None:
            if (exits := getattr(room, "exits", None)) is not None:
                commands = list(exits.get_commands_for(character).values())

        # Add all other commands (non-specific to location).
        commands += list(Command.service.commands.values())

        root = commands
        parent = command = method = None
        while commands:
            names = {}
            commands = {
                cls
                for cls in commands
                if cls.parent is parent and cls.can_run(character)
            }
            seps = {sep: () for comm in commands for sep in comm.seps}
            for sep in seps.keys():
                try:
                    before, after = user_input.split(sep, 1)
                except ValueError:
                    before, after = user_input, ""

                seps[sep] = (before, after)

            # Create a dictionary (hashed structure) to access command names.
            for cls in commands:
                record_names(names, cls.name, cls)

                # Add aliases.
                if alias := cls.alias:
                    if isinstance(alias, str):
                        aliases = (alias,)
                    else:
                        aliases = alias

                    for alias in aliases:
                        record_names(names, alias, cls)

            # Add global aliases if theree's no parent.
            if parent is None:
                sub_commands = [
                    cls
                    for cls in root
                    if cls.parent is not None and cls.can_run(character)
                ]
                for cls in sub_commands:
                    if alias := cls.global_alias:
                        if isinstance(alias, str):
                            aliases = (alias,)
                        else:
                            aliases = alias

                        for alias in aliases:
                            record_names(names, alias, cls)

            # We have a dictionary containing completion commands names.
            # We then try to match the command using different separators.
            for before, after in seps.values():
                command = names.get(before, None)
                if command is not None:
                    parent = command
                    commands = command.sub_commands
                    user_input = after
                    break

            if command is None:
                command = parent
                method = "display_sub_commands"
                commands = None

        found = False
        if command:
            command = command(character, sep, after)
            if method is None:
                method = command.parse_and_run
            else:
                method = getattr(command, method)
            method()
            found = True

        return found

    def unknown_input(self, user_input: str) -> str:
        """What to do when the input doesn't match?"""
        return f"Command not found: {user_input}"


def can_shorten(command: Command) -> bool:
    """Can this command be shortened, using aliases?"""
    return settings.CAN_SHORTEN_COMMANDS and command.can_shorten


def record_names(
    names: dict[str, Command], name: str, command: Command
) -> None:
    """Record the names for the given command under the given name.

    Args:
        names (dict): the names to update.
        name (str): the command name to add.
        command (Command): the command matching this name.

    If the command can be shortened, also add partial names.

    """
    names[name] = command

    # Add completition names.
    if can_shorten(command):
        for i in range(len(name) - 1, 0, -1):
            partial = name[:i]
            names.setdefault(partial, command)
