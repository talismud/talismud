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

"""Nothing argument."""

from typing import Optional, Union, TYPE_CHECKING

from command.args.base import ArgSpace, Argument, ArgumentError, Result

if TYPE_CHECKING:
    from data.character import Character


class Nothing(Argument):

    """Nothing class for argument."""

    name = "nothing"
    space = ArgSpace.STRICT
    in_namespace = False

    def __init__(self, dest, optional=True, default=None):
        super().__init__(dest, optional=True, default=default)
        self.msg_present = "You should not specify anything."

    def __repr__(self):
        return "NOTHING"

    def format(self):
        """Return a string description of the arguments.

        Returns:
            description (str): the formatted text.

        """
        return "|"

    def parse(
        self,
        character: "Character",
        string: str,
        begin: int = 0,
        end: Optional[int] = None,
    ) -> Union[Result, ArgumentError]:
        """Parse the argument.

        Args:
            character (Character): the character running the command.
            string (str): the string to parse.
            begin (int): the beginning of the string to parse.
            end (int, optional): the end of the string to parse.

        Returns:
            result (Result or ArgumentError).

        """
        if string[begin:end].strip():
            result = ArgumentError(self.msg_present)
        else:
            result = Result(begin=begin, end=end, string=string)

        return result

    def add_to_namespace(self, result, namespace):
        """Add the parsed search object to the namespace."""
