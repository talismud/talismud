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

"""Base class for commands."""

from importlib import import_module
import inspect
from pathlib import Path
from textwrap import dedent
import traceback
from typing import Any, Dict, Sequence, Type, TYPE_CHECKING

from command.abc import CommandMetaclass
from command.args import ArgumentError, CommandArgs, Namespace
from command.log import logger
from command.namespace import ProxyNamespace
from service.base import BaseService
from tools.delay import Delay

if TYPE_CHECKING:
    from data.character import Character

_NOT_SET = object()


class Command(metaclass=CommandMetaclass):

    """Base class for commands.

    Commands are defined in modules and dynamically imported
    from the file system, from the 'command' directory and its
    sub-directories.

    A command can have a name, inferred from the class name if not
    provided.  It can also have aliases, a command category, tags
    and basic command permissions.  Its help entry is inferred from
    the command's docstring.

    Here's a very basic example.  Assuming you want to add the 'look'
    command, just create a file with the '.py' extension in the command
    package (it can be in a sub-package, for the sake of organization).

    ```python
    from command import Command

    class Look(Command): # 'look' (lowercase class name) will be the name

        '''
        Look command, to look around you.

        Syntax:
            look [object]

        This command is used to look around you or look a specific object
        more in details.

        '''

        # If you're not happy with the default name, just provide a
        # class variable 'name' and set the command name to it.  You can
        # define the category in the 'category' class variable as a
        # string, and the command permissions, still as a string, in the
        # 'permissions' class variable.  If they're not defined,
        # these last two values will be searched in parent packages
        # following a capitalized convention (see below).
        args = Command.new_parser()
        args.add_argument("object", optional=True)

        def run(self, args):
            '''The command is executed.'''
            self.msg("Ho, look!")
    ```

    If the `category` and/or `permissions` class variables aren't
    provided, they're automatically searched in the module and
    parent packages.  A `CATEGORY` variable is searched in this module
    and, if not found, in parent packages recursively.  Similarly,
    a `PERMISSIONS` variable is searched in the module and parent
    packages.  This system allows to easily organize commands.

    For instance, assuming you want to create commands that only the
    administrators should use:  you could create a directory called
    'admin' inside of the 'command' package.  In this new directory,
    add an `__init__.py` file.  Inside write the following:

    ```python
    CATEGORY = "Admin commands"
    PERMISSIONS = "admin"
    ```

    Then you can create a file per command as usual.  For instance,
    create a file 'services.py' that contains the following code:

    ```python
    from command import Command

    class Services(Command):

        '''Command services, to look for active services in the game.'''

        # name will be 'services'
        # ...
    ```

    Because we haven't defined a `category` class variable, a
    `CATEGORY` top-level variable will be searched in the module
    itself.  Since we haven't defined one, it will be searched in the
    parent package (that is, in our 'command/admin/__init.py' file).
    In this file is our `CATEGORY` variable, so the 'services'
    command will have its category set to 'Admin commands'.  The same
    process applies for permissions.  Notice that you can always
    override this behavior should the need arise, but it makes
    organization much easier.

    """

    args: CommandArgs = CommandArgs()
    seps: str | tuple[str] = " "
    alias: str | tuple[str] = ()
    in_help: bool = True
    can_shorten: bool = True

    # Sub-commands only
    parent: Type["Command"] | None = None
    global_alias: str | tuple[str] = ()

    # Do not override this.
    service: BaseService
    sub_commands: set["Command"] = set()

    def __init__(self, character=None, sep=None, arguments=""):
        self.character = character
        self.sep = sep
        self.arguments = arguments

    @property
    def session(self):
        return self.character and self.character.session or None

    @property
    def db(self):
        """Return the ProxyNamespace for this command."""
        return ProxyNamespace(self)

    @classmethod
    def can_run(cls, character) -> bool:
        """Can the command be run by the specified character?

        Args:
            character (Character): the character to run this command.

        By default, check the command's permissions.  You can,
        however, override this method in individual commands
        to perform other checks.

        Returns:
            can_run (bool): whether this character can run this command.

        """
        if parent := cls.parent:
            if not parent.can_run(character):
                return False

        if cls.permissions:
            return character.permissions.has(cls.permissions)

        return True

    @classmethod
    def get_help(cls, character=None) -> str:
        """Return the help of a command, tailored for a character.

        If a character asks for this command help, the command
        permissions are checked beforehand.  It can be assumed
        the character is authorized to see this command at this
        point.  However, if the character isn't specified, there's
        no way to be sure she could execute the command, as she's
        not specified.  Handle this use case before calling
        `get_help` with no argument, as this is a rather special
        use case.

        Args:
            character (Character, optional): the character asking for help.

        Returns:
            help (str): the command help as a str.

        """
        docstring = inspect.getdoc(cls)
        return dedent(docstring)

    @classmethod
    def new_parser(self) -> CommandArgs:
        """Simply return an empty command argument parser."""
        return CommandArgs()

    def parse(self, character: "Character"):
        """Parse the command, returning the namespace or an error."""
        return type(self).args.parse(character, self.arguments)

    def run(self, args: Namespace):
        """Run the command with the provided arguments.

        The command arguments are first parsed through the command
        argument parser (see `command/args.py`), so that this method
        is only called if arguments are parsed correctly.

        Args:
            args (namespace): The correctly parsed arguments.

        The method signature is actually quite variable.  You can specify
        the keyword arguments for your command which helps to parse them.
        See 'admin/py.py' for instance.

        """
        self.msg(f"Great!  You reached the command {self.name}.")

    def parse_and_run(self):
        """Parse and, if possible, run the command.

        This is a shortcut to first parse, then run the command
        withint a try/except block to catch errors.

        """
        try:
            result = self.parse(self.character)
            if isinstance(result, ArgumentError):
                self.msg(str(result))
                return

            method_name = getattr(result, "_run_in", "run")
            method = getattr(self, method_name, None)
            if method is None:
                if self.character and self.character.permissions.has("admin"):
                    self.msg(
                        "Cannot access the command's {method_name!r} method."
                    )
                else:
                    self.msg(
                        "Sorry, this command is not accessible right now."
                    )
                return

            args = self.args_to_dict(method, result)
            method(**args)
        except Exception:
            # If an administrator, sends the traceback directly
            if self.character and self.character.permissions.has("admin"):
                self.msg(traceback.format_exc())

            logger.exception(
                "An error occurred while parsing and running the "
                f"{self.name} commnd:"
            )
            raise

    def msg(self, text: str, raw: bool = False, prompt: bool = True):
        """Send the message to the character running the command.

        Args:
            text (str): text to send to the character.
            raw (bool, optional): if True, escape braces.
            prompt (bool, optional): display the prompt.  Set this to
                    `False` to not display a prompt below the message.
                    Note that messages are grouped, therefore, if one
                    of them deactive the prompt, it will be deactivated
                    for all the group.

        """
        self.character.msg(text, prompt=prompt)

    def display_sub_commands(self) -> None:
        """Display sub-commands to help syntax."""
        lines = [
            f"Available sub-commands for {self.name}:",
            "",
        ]

        max_name = max(len(cls.name) for cls in type(self).sub_commands)
        for sub in type(self).sub_commands:
            if not sub.can_run(self.character):
                continue

            name = sub.name
            synopsis = sub.get_help(self.character)
            synopsis = synopsis.splitlines()[0]
            limit = 72 - max_name
            if len(synopsis) > limit:
                synopsis = synopsis[:limit] + "..."
            lines.append(f"  {name:<{max_name}} - {synopsis}")

        self.msg("\n".join(lines))

    def call_in(self, *args, **kwargs):
        """Schedule a callback to run in X seconds.

        Args:
            delay (int or float or timedelta): the delay (in seconds).
            callback (Callable): the callback (usually an instance method).

        Additional positional or keyword arguments will be sent to the
        callback when it's time to execute it.

        """
        return Delay.schedule(*args, **kwargs)

    @classmethod
    def extrapolate(cls, path: Path):
        """Extrapolate name, category and permissions if not set.

        This will entail looking into parent modules if needed.

        Args:
            path (pathlib.Path): path leading to the command.

        """
        # Try to find the command name
        if not hasattr(cls, "name"):
            cls.name = cls.__name__.lower()

        # Try to find the command category, permissions and layer
        if any(
            not hasattr(cls, missing)
            for missing in ("category", "permissions")
        ):
            category, permissions = cls._explore_for(
                path, ("CATEGORY", "PERMISSIONS")
            )

            if not hasattr(cls, "category"):
                category = category or "General"
                cls.category = category

            if not hasattr(cls, "permissions"):
                permissions = permissions or ""
                cls.permissions = permissions

    @staticmethod
    def _explore_for(path: Path, names: Sequence[str]):
        """Explore for the given variable names."""
        values = [_NOT_SET] * len(names)
        current = path
        while str(current) != ".":
            if current.parts[-1].endswith(".py"):
                current = current.parent / current.stem

            pypath = ".".join(current.parts)
            module = import_module(pypath)
            for i, name in enumerate(names):
                if values[i] is not _NOT_SET:
                    continue

                value = getattr(module, name, _NOT_SET)
                if value is not _NOT_SET:
                    values[i] = value

            if not any(value is _NOT_SET for value in values):
                return tuple(values)

            current = current.parent

        # Some values couldn't be found in parent directories.
        for i, value in enumerate(values):
            if value is _NOT_SET:
                values[i] = None

        return tuple(values)

    @classmethod
    def args_to_dict(cls, method, args: Namespace) -> Dict[str, Any]:
        """Return a dictionary based on the `run` arguments.

        The `run` method can have:
            An argument called `args` which contains the entire namespace.
            An argument for each namespace arguments.

        This class method will create a dictionary based on the
        expected arguments of the `run` method.

        Returns:
            args_as_dict (dict): the packed namespace as a dict.

        """
        to_dict = {}
        signature = inspect.signature(method)
        parameters = [
            p for p in signature.parameters.values() if p.name != "self"
        ]

        for parameter in parameters:
            if parameter.name == "args":
                to_dict["args"] = args
            else:
                value = getattr(args, parameter.name, _NOT_SET)
                if value is _NOT_SET:
                    default = parameter.default
                    if default is inspect._empty:
                        raise ValueError(
                            f"{cls}: the command requires the keyword "
                            f"argument {parameter.name!r}, but it's not "
                            "defined as a command argument in the method "
                            f"{method.__name__} and doesn't "
                            "have a default value in the method signature"
                        )

                    value = default
                to_dict[parameter.name] = value

        return to_dict
