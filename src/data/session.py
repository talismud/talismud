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
import pickle
from queue import Queue
from typing import Optional, Union, TYPE_CHECKING
from uuid import UUID

from pydantic import PrivateAttr
from pygasus import Field, Model
from pygasus.model.decorators import lazy_property

from context.base import CONTEXTS
from data.handler.namespace import NamespaceField

if TYPE_CHECKING:
    from data.character import Character

# Mutable container.
OUTPUT_QUEUE = Queue()


class Session(Model):

    """Session storage model."""

    uuid: UUID = Field(primary_key=True)
    ip_address: str
    secured: bool
    creation: datetime
    encoding: str
    db: dict = Field({}, custom_class=NamespaceField)
    context_path: str
    context_options: bytes
    character: Optional["Character"] = None
    _cached_context = PrivateAttr()

    @lazy_property
    def context(self):
        """Load the context from the context path."""
        if (context := CONTEXTS.get(self.context_path)) is None:
            raise ValueError(f"the context {self.context_path} doesn't exist")
        return context(self)

    @context.setter
    def context(self, new_context):
        """Change the session's context."""
        self.context_path = new_context.pyname
        self.context_options = pickle.dumps(new_context.options)

    def msg(self, text: Union[str, bytes]) -> None:
        """Send text to this session.

        This method will contact the session on the portal protocol.
        Hence, it will write this message in a queue, since it
        would be preferable to group messages before a prompt,
        if this is supported.

        Args:
            text (str or bytes): the text, already encoded or not.

        If the text is not yet encoded, use the session's encoding.

        """
        if isinstance(text, str):
            text = text.encode(self.encoding, errors="replace")

        if isinstance(text, bytes):
            OUTPUT_QUEUE.put((self.uuid, text))

    def logout(self):
        """Prepare the session for logout."""
        if character := self.character:
            character.db.log_at = character.room
            character.room.characters.remove(character)
