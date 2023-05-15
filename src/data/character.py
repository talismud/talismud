# Copyright (c) 2021, LE GOFF Vincent
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

"""Character storage model."""

from typing import Optional, TYPE_CHECKING

from data.base.node import Field, Node
from data.handler.channels import ChannelHandler
from data.handler.contexts import ContextHandler
from data.handler.namespace import NamespaceHandler
from data.handler.permissions import PermissionHandler

if TYPE_CHECKING:
    from data.exit import Exit
    from data.room import Room
    from data.session import Session


class Character(Node):

    """Character storage model."""

    id: int = Field(primary_key=True)
    name: str = "unknown"
    contexts: ContextHandler = Field(default_factory=ContextHandler)
    permissions: PermissionHandler = Field(default_factory=PermissionHandler)
    channels: ChannelHandler = Field(default_factory=ChannelHandler)
    db: NamespaceHandler = Field(default_factory=NamespaceHandler)
    room: Optional["Room"] = None
    session: Optional["Session"] = None

    def msg(self, text: str | bytes, prompt: bool = True) -> None:
        """Send text to this session.

        This method will contact the session on the portal protocol.
        Hence, it will write this message in a queue, since it
        would be preferable to group messages before a prompt,
        if this is supported.

        Args:
            text (str or bytes): the text, already encoded or not.
            prompt (bool, optional): display the prompt.  Set this to
                    `False` to not display a prompt below the message.
                    Note that messages are grouped, therefore, if one
                    of them deactive the prompt, it will be deactivated
                    for all the group.

        If the text is not yet encoded, use the session's encoding.

        """
        if session := self.session:
            session.msg(text, prompt=prompt)

    def move(self, exit: "Exit"):
        """Move through an exit in the room.

        Args:
            exit (Exit): the exit to move through.

        """
        self.location = exit.destination
        self.msg(self.location.look(self))
