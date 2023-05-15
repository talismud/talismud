# Copyright (c) 2022 LE GOFF Vincent
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

from collections import defaultdict

from command import Command
from tools.list import ListView


class Help(Command):

    """Provide help on a command.

    Usage:
        help (command name)

    This command allows you to obtain help.  Use this command without
    argument to see the list of available commands.  You can also ask
    for specific help on a command, providing the command name
    as argument:
      help look

    """

    args = Command.new_parser()
    args.add_argument("text", dest="name", optional=True)

    def run(self, name):
        """Run the command."""
        commands = Command.service.commands
        commands = {
            command.full_name: command
            for command in commands.values()
            if command.in_help
        }
        if character := self.character:
            commands = {
                cmd_name: command
                for cmd_name, command in commands.items()
                if command.can_run(character)
            }

        if name:
            command = commands.get(name.lower())
            if command is None:
                self.msg(f"Cannot find this command: '{name}'.")
            else:
                lines = (
                    f"={'-' * 20} Help on '{command.name}' {'-' * 20}=",
                    command.get_help(self.character),
                )
                self.msg("\n".join(lines))
        else:
            view = ListView(orientation=ListView.HORIZONTAL)
            view.items.indent_width = 4
            categories = defaultdict(list)
            for command in commands.values():
                if command.parent:
                    continue

                categories[command.category].append(command)

            for category, commands in sorted(categories.items()):
                view.add_section(
                    category, [command.name for command in commands]
                )

            self.msg(view.render())
