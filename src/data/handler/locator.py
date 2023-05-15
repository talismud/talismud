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


"""Locator object, to hold node location."""

from collections import defaultdict
from typing import Optional, TYPE_CHECKING

from data.handler.abc import BaseHandler

if TYPE_CHECKING:
    from data.base.node import Node


class LocationHandler(BaseHandler):

    """Locatoin handler common to all nodes."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._stackables = defaultdict(int)

    @property
    def contents(self):
        model, _ = self.model
        return type(model).engine.locator.get_at(model.id)

    @property
    def all_contents(self):
        """Return contents and stackables in a tuple of tuple."""
        model, _ = self.model
        non_stackables = self.contents
        result = [(node, 1, node.location_filter) for node in non_stackables]

        for ((node_id, filter), quantity) in self._stackables.items():
            stackable = type(model).engine.get_model(
                type(model), raise_not_found=False, id=node_id
            )

            if stackable is not None:
                result.append((stackable, quantity, filter))

        return result

    def how_many(self, content: "Node", filter: str | None = None) -> int:
        """Return the quantity of the specified node.

        If the node is unique, it will return either 0 or 1.  It will
        return a potentially greater number if this object is stackable.
        If a filter is specified, filter nodes further.

        Args:
            content (Node): the content.
            filter (str, optional): the location filter.

        Returns:
            quantity (int): the quantity as 0 or greater.

        """
        if self.is_stackable(content):
            quantity = self._stackables.get((content.id, filter), 0)
        else:
            contents = type(content).engine.locator.get_at(content.id, filter)
            quantity = 1 if content in contents else 0

        return quantity

    def get(self) -> Optional["Node"]:
        """Return the current location of the model or None if not any."""
        model, _ = self.model
        if model and (location_id := model.location_id):
            location = type(model).engine.get_model(
                type(model), raise_not_found=False, id=location_id
            )
        else:
            location = None

        return location

    def set(
        self,
        new_location: Optional["Node"],
        old_filter: str | None = None,
        new_filter: str | None = None,
    ) -> None:
        """Change the current model's location to a new location.

        This will fail (with a ValueError) if the current model is stackable.

        Args:
            new_location (Node or None): the new location.
            old_filter (str, optional): the old location filter.
            new_filter (str, optional): the new location filter.

        """
        model, _ = self.model
        if new_location is None:
            model.location_id = None
        else:
            if self.is_stackable(model):
                raise ValueError(
                    f"the node[{model.id}] is stackable and cannot "
                    f"just be placed in node[{new_location.id}].  "
                    f"Use `location.locator.transfer` instead."
                )

            new_location.locator.transfer(
                model, old_filter=old_filter, new_filter=new_filter
            )

    def transfer(
        self,
        content: "Node",
        origin: Optional["Node"] = None,
        quantity: int = 1,
        old_filter: str | None = None,
        new_filter: str | None = None,
    ) -> int:
        """Place the specified content from origin into the current location.

        If the content is stackable (that is, if it's not unique),
        remove the quantity of this object from origin and
        add this quantity to the current location.

        Args:
            content (Node): the content to place in this location.
            origin (Node, optional): the origin of the node.  This is
                    only useful if the node is stackable, because unique
                    nodes always reference their location.  However,
                    it might be useful to specify an origin when
                    one does not know whether the object to place
                    is stackable or not.
            quantity (int, optional): the quantity (1 by default).
                    This is useful for stackable objects.  The quantity
                    will be ignored for unique contents.
            old_filter (str, optional): the old location filter.
            new_filter (str, optional): the new location filter.

        Returns:
            quantity (int): the quantity of transferred objects.

        """
        model, _ = self.model
        if self.is_stackable(content):
            # Remove the quantity from the content first.
            quantity = origin.locator.remove(
                content, quantity, filter=old_filter
            )
            if quantity > 0:
                self._stackables[(content.id, new_filter)] += quantity
                self.save()
        else:
            type(model).engine.locator.move(
                content, model.id, filter=new_filter
            )
            quantity = 1

        return quantity

    def add(
        self, content: "Node", quantity: int, filter: str | None = None
    ) -> int:
        """Add the stackable node in this location.

        Args:
            content (Node): the object (must be stackable).
            quantity (int): the quantity to add.
            filter (str, optional): the new location filter.

        """
        if self.is_stackable(content):
            self._stackables[(content.id, filter)] += quantity
            self.save()
        else:
            raise ValueError(f"the node[{content.id}] isn't stackable")

    def remove(
        self, content: "Node", quantity: int, filter: str | None = None
    ) -> int:
        """Remove and return the removed quantity from a stackable object.

        Args:
            content Node: the object (must be stackable).
            quantity (int): the maximum quantity to remove.
            filter (str, optional): the old filter.

        If the object is not present in the current location, simply
        rerusn `0`.  Otherwise, returns the actual quantity that could
        be removed.

        """
        current = self._stackables.get((content.id, filter))
        if current:
            if quantity >= current:
                quantity = current
                self._stackables.pop((content.id, filter))
            else:
                self._stackables[(content.id, filter)] = current - quantity

            self.save()
        else:
            quantity = 0

        return quantity

    @staticmethod
    def is_stackable(node: "Node") -> bool:
        """Return whether this node is stackable.

        Args:
            node (Node): the node to test.

        Returns:
            stackable (bool): whehter this node is stackable.

        """
        stackable = getattr(node, "stackable", None)
        if stackable is None:
            stackable = getattr(type(node).__config__, "stackable", False)

        return stackable
