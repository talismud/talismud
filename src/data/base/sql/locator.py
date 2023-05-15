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

"""Module containing the locator object."""

from typing import TYPE_CHECKING

from data.base.node import Node
from data.base.sql.node import Node as SQLNode

if TYPE_CHECKING:
    from data.base.sql.engine import SqliteEngine


class Locator:

    """Locator, sub-engine to keep track of node locations."""

    def __init__(self, engine: "SqliteEngine") -> None:
        self.engine = engine
        self.contents = {}

    def clear(self):
        """Clear all contents."""
        self.contents.clear()

    def get_at(
        self, location_id: int, filter: str | None = None
    ) -> list["Node"]:
        """Load all nodes from a location ID.

        If a filter is specified, only load nodes with this filter.

        Args:
            location_id (int): the location ID.
            filter (str, optional): the location filter.

        Returns:
            nodes (list of Node): all nodes with this location.

        The cache is used, if it exists.

        """
        if nodes := self.contents.get(location_id):
            if filter is not None:
                return [
                    node for node in nodes if node.location_filter == filter
                ]

            return nodes

        nodes = self.engine.select_models(
            Node, SQLNode.location_id == location_id
        )
        nodes.sort(key=lambda node: node.location_index)
        self.contents[location_id] = nodes

        if filter is not None:
            nodes = [node for node in nodes if node.location_filter == filter]

        return nodes

    def move(
        self, node: "Node", new_location_id: int, filter: str | None = None
    ) -> None:
        """Move this node to a new location.

        The node is added at the end of a location (maximum index).

        Args:
            node (Node): the node to move.
            new_location_id (int): the new location as ID.
            filter (str, optional): the new location filter of this node.

        The cache is refreshed if necessary.

        """
        old_location_id = node.location_id

        # First, check that the movement is allowed.
        # An object A cannot move inside B if B contains A.
        parent = self.engine.get_model(Node, id=new_location_id)
        while parent is not None:
            if parent.id == node.id:
                raise ValueError(
                    f"cannot move node[{node.id}] into "
                    f"node[{new_location_id}], because "
                    f"node[{new_location_id}] is contained within "
                    f"node[{node.id}]"
                )

            if (parent_id := parent.location_id) is not None:
                parent = self.engine.get_model(Node, id=parent_id)
            else:
                break

        if nodes := self.contents.get(old_location_id):
            nodes.remove(node)

        if nodes := self.contents.get(new_location_id):
            node.location_index = max(n.location_index for n in nodes) + 1
            nodes.append(node)
        else:
            node.location_index = 0
            self.contents[new_location_id] = [node]

        node.location_id = new_location_id

        if filter is not None:
            node.location_filter = filter
