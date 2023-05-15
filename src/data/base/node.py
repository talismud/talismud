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

"""Module containing a node definition.

The node is the most common element in the stored world of your game.
Almost every part of the world (rooms, characters, objects) are nodes
behind the scenes.

"""

from typing import Optional

from pydantic import Field

from data.base.model import Model
from data.base.sql.inattr import INattr
from data.base.sql.nattr import Nattr
from data.base.sql.node import Node as SQLNode
from data.handler.locator import LocationHandler


class Node(Model):

    """The high-level, storage-agnostic node object."""

    id: int = Field(primary_key=True)
    location_id: int | None
    location_index: int | None
    location_filter: str | None
    locator: LocationHandler = Field(default_factory=LocationHandler)

    @property
    def location(self) -> Optional["Node"]:
        return self.locator.get()

    @location.setter
    def location(self, new_location: Optional["Node"]) -> None:
        self.locator.set(new_location)

    @property
    def contents(self) -> list["Node"]:
        """Return the list of nodes contained within self."""
        return self.locator.contents

    class Config:

        external_attrs = True
        base_model = "data.base.node.Node"
        table = SQLNode
        attr_table = Nattr
        iattr_table = INattr
