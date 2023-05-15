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

"""Session storage model."""

from datetime import datetime
from queue import Queue
from typing import Optional, TYPE_CHECKING
from uuid import UUID

from dynaconf import settings

from context.base import CONTEXTS
from data.base.model import Field, Model
from data.decorators import lazy_property
from data.handler.namespace import NamespaceHandler
from data.room import Room

if TYPE_CHECKING:
    from data.character import Character

# Mutable container.
OUTPUT_QUEUE = Queue()


class Session(Model):

    """Session storage model."""

    uuid: UUID = Field(primary_key=True)
    ip_address: str
    secured: bool
    creation: datetime = Field(default_factory=datetime.utcnow)
    encoding: str = "utf-8"
    db: NamespaceHandler = Field(
        default_factory=NamespaceHandler, external=True
    )
    context_path: str = "unset"
    context_options: dict = Field(default_factory=dict, external=True)
    character: Optional["Character"] = Field(None, external=True)

    @lazy_property
    def context(self):
        """Load the context from the context path."""
        cls = CONTEXTS.get(self.context_path)
        if cls is None:
            raise ValueError(f"the context {self.context_path} doesn't exist")

        return cls(self, None, self.context_options)

    @context.setter
    def context(self, new_context):
        """Change the session's context."""
        self.context_path = new_context.pyname
        self.context_options = new_context.options

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
        if isinstance(text, str):
            text = text.encode(self.encoding, errors="replace")

        if isinstance(text, bytes):
            OUTPUT_QUEUE.put((self.uuid, text, {"prompt": prompt}))

    def login(self, character: "Character") -> None:
        """Login to a character."""
        self.character = character
        character.session = self

        # Browse contexts in context stack.
        for context in character.contexts:
            context.session = self

        # Place the character in a valid room, if at all possible.
        room = character.room
        if room is None:
            room = Room.get(
                barcode=settings.RETURN_ROOM, raise_not_found=False
            )
            character.room = room

        if room:
            character.location = room

        # Place the character in its subscribed channels.
        for channel in character.channels.subscribed:
            channel.subscribers.add(character)

    def logout(self):
        """Prepare the session for logout."""
        if character := self.character:
            (character.room, character.location) = (character.location, None)
