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

"""Coodinates handler, to store coordinates for any node."""

from math import sqrt
from typing import Type

from sqlalchemy import func

from data.base.coordinates import Coordinates, closure
from data.base.node import Node
from data.direction import Direction
from data.handler.abc import BaseHandler

# Constants
DIRECTIONS = {
    Direction.EAST: closure({"x": 1}),
    Direction.SOUTHEAST: closure({"x": 1, "y": -1}),
    Direction.SOUTH: closure({"y": -1}),
    Direction.SOUTHWEST: closure({"x": -1, "y": -1}),
    Direction.WEST: closure({"x": -1}),
    Direction.NORTHWEST: closure({"x": -1, "y": 1}),
    Direction.NORTH: closure({"y": 1}),
    Direction.NORTHEAST: closure({"x": 1, "y": 1}),
    Direction.DOWN: closure({"z": -1}),
    Direction.UP: closure({"z": 1}),
}
PRECISION = 5


class CoordinateHandler(BaseHandler):

    """Soft-link with the coordinates table.

    All nodes can have valid coordinates, although this is optional.
    Rooms may implement the `CoordinateHandler`, for instance.

    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._x = None
        self._y = None
        self._z = None
        self._valid = False
        self._row = None
        self._has_valid = False

    @property
    def x(self) -> float | None:
        """Return X as a floating point number or None if not valid."""
        self._fetch_coordinates()
        return self._x if self._valid else None

    @x.setter
    def x(self, x: int | float | None):
        """Update X."""
        self._fetch_coordinates()
        self._x = round(x, PRECISION) if x is not None else x
        self._check_valid()
        self.save()

    @property
    def y(self) -> float | None:
        """Return Y as a floating point number or None if not valid."""
        self._fetch_coordinates()
        return self._y if self._valid else None

    @y.setter
    def y(self, y: int | float | None):
        """Update Y."""
        self._fetch_coordinates()
        self._y = round(y, PRECISION) if y is not None else y
        self._check_valid()
        self.save()

    @property
    def z(self) -> float | None:
        """Return Z as a floating point number or None if not valid."""
        self._fetch_coordinates()
        return self._z if self._valid else None

    @z.setter
    def z(self, z: int | float | None):
        """Update Z."""
        self._fetch_coordinates()
        self._z = round(z, PRECISION) if z is not None else z
        self._check_valid()
        self.save()

    @property
    def rounded(self) -> str:
        """Return the rounded coordinates (as ints)."""
        coordinates = (x, y, z) = (self.x, self.y, self.z)
        if any(c is None for c in coordinates):
            msg = "UNSET"
        else:
            msg = f"{round(x)} {round(y)} {round(z)}"

        return msg

    def __repr__(self):
        if self._valid:
            ret = f"<Coordinates {self._x} {self._y} {self._z}>"
        else:
            ret = "<InvalidCoordinates>"

        return ret

    def __bool__(self) -> bool:
        return self._valid

    def get_at(
        self, x: int | float, y: int | float, z: int | float
    ) -> Node | None:
        """Return the node at these coordinates or None.

        Since coordinates can be floats, one has to be careful
        with this command.  Preferably only use it to find nodes
        at int coordinates.

        Args:
            x (int or float): the X axis.
            y (int or float): the Y axis.
            z (int or float): the Z axis.

        Returns:
            found (Node or None): the Node if found else None.

        """
        self._fetch_coordinates()
        table = Coordinates.table
        query = (
            table.valid.is_(True)
            & (table.x == x)
            & (table.y == y)
            & (table.z == z)
        )

        at = Coordinates.engine.select_values(
            Coordinates, Coordinates.table.model, query
        )

        model, _ = self.model
        model = type(model)

        match at:
            case []:
                node = None
            case [node_id]:
                node = model.get(id=node_id, raise_not_found=False)
            case _:
                raise ValueError(
                    "more than one node found at these coordinates"
                )

        return node

    def around(
        self,
        radius: int | float,
        x: int | float | None = None,
        y: int | float | None = None,
        z: int | float | None = None,
        only: Type[Node] | None = ...,
        exclude: Node | list[Node] | None = ...,
    ) -> list[Node]:
        """Return the node objects with coordinates as a maximum distance.

        By default, this will return a list of node objects around
        a set of coordinates.  The coordinates can be overridden
        by specifying the `x`, `y`, and `z` parameters.

        Args:
            radius (int or float): the maximum distance.  The list
                    will contain only node objects with valid coordinates
                    in a circular pattern around the current coordinates
                    (or overridden ones).  Therefore, a room at (1, 0, 0)
                    will be returned when looking for all rooms
                    at a 1 max radius of (0, 0, 0), but (1, 1, 0)
                    will not (the distance between (0, 0, 0) and (1, 1, 0)
                    is not 1).
            x (int or float, optional): the overridden X coordinate.
            y (int or float, optional): the overridden Y coordinate.
            z (int or float, optional): the overridden Z coordinate.
            only (subclass of Node): only return nodes of this subclass.
                    By default, return only the nodes of the parent model.
            exclude (Node or list of nodes): the node(s) to exclude.
                    If unset, exclude the model calling
                    `coordinates.around`, which will presumably be the center
                    (unless the coordinates have been overridden).

        Returns:
            distances (list of tuple): the distances ordered by distance
                    from the center (or overridden coordinates)
                    where each element of the list is a tuple
                    containing the distance (as a float) and the node
                    at this distance.

        """
        self._fetch_coordinates()
        if any(c is None for c in (x, y, z)):
            x, y, z = self.x, self.y, self.z

        table = Coordinates.table
        query = table.valid.is_(True) & (
            func.sqrt(
                func.pow((table.x - x), 2)
                + func.pow((table.y - y), 2)
                + func.pow((table.z - z), 2)
            )
            <= radius
        )

        if only is ...:
            model = type(self.model[0])
        elif only is None:
            model = Node
        else:
            model = only

        close = Coordinates.engine.select_values(
            Coordinates, Coordinates.table.model, query
        )

        # Remove nodes to exclude.
        if exclude is ...:
            exclude, _ = self.model
            close.remove(exclude.id)
        elif isinstance(exclude, Node):
            close.remove(exclude.id)
        else:
            for node in exclude:
                close.remove(node.id)

        # Fetch the nodes with these IDs.
        nodes = model.select(model.table.id.in_(close))

        # Sort by distances.
        distances = [(self.distance(node), node) for node in nodes]
        distances.sort(key=lambda tup: tup[0])
        return distances

    def distance(
        self, coordinates: Node | tuple[int | float, int | float, int | float]
    ) -> int | float:
        """Return the distance between the current coordinates and another set.

        Args:
            coordinates (tuple): the other coordinates (x, y, z).

        Returns:
            distance (int or float): the distance.

        """
        self._fetch_coordinates()
        if isinstance(coordinates, Node):
            coordinates = coordinates.coordinates
            x, y, z = coordinates.x, coordinates.y, coordinates.z
        else:
            x, y, z = coordinates

        return round(
            sqrt((x - self.x) ** 2 + (y - self.y) ** 2 + (z - self.z) ** 2),
            PRECISION,
        )

    def project(
        self,
        direction: Direction,
        units: int | float = 1,
        x: int | float | None = None,
        y: int | float | None = None,
        z: int | float | None = None,
    ) -> tuple[int | float, int | float, int | float]:
        """Project a set of coordinates in a given direction.

        WARNING:
            this method SHOULD NOT be used for movement.  It can
            be used for builders, however, particularly when adding
            rooms that usually have static coordinates.  `units` is NOT
            an indicator of distance, rather, it is an indicator of
            the number of operations to perform on the coordinates.
            For instance, projecting the room northeast of (0, 0, 0)
            will return (1, 1, 0).  The distance between (0, 0, 0)
            and (1, 1, 0) is not 1 (it is around 1.41)  If you need
            to simulate movement of a set of coordinates, do not
            use this method.

        Args:
            direction (Direction): the direction to project.
            units (int): the number of units to project.  By default, it is 1.
            x (int or float, optional): the overridden X coordinate.
            y (int or float, optional): the overridden Y coordinate.
            z (int or float, optional): the overridden Z coordinate.

        Returns:
            projected (X, Y, Z): the project coordinates.

        """
        self._fetch_coordinates()
        if any(c is None for c in (x, y, z)):
            x, y, z = self.x, self.y, self.z

        closure = DIRECTIONS.get(direction)
        if closure is None:
            raise ValueError(f"cannot project ({x}, {y}, {z}) in {direction}")

        x, y, z = closure(units, x, y, z)
        return x, y, z

    def update(self, x: int | float, y: int | float, z: int | float) -> None:
        """Update all three coordinates in a row.

        Args:
            x (int or float): the X axis.
            y (int or float): the Y axis.
            z (int or float): the Z axis.

        """
        self._fetch_coordinates()
        if x is not None:
            x = round(x, PRECISION)

        if y is not None:
            y = round(y, PRECISION)

        if z is not None:
            z = round(z, PRECISION)

        self._x, self._y, self._z = x, y, z
        self._check_valid()
        self.save()

    def save(self):
        """Save the current handler."""
        if self._valid or self._has_valid:
            self._create_row()
            row = Coordinates.get(id=self._row)

            if row.x != self._x:
                row.x = self._x if self._x is not None else 0.0

            if row.y != self._y:
                row.y = self._y if self._y is not None else 0.0

            if row.z != self._z:
                row.z = self._z if self._z is not None else 0.0

            if row.valid is not self._valid:
                row.valid = self._valid

            self._has_valid = self._valid

    def from_blueprint(self, coordinates: dict[str, int | float]) -> None:
        """Recover the description from a blueprint."""
        match coordinates:
            case {"x": x, "y": y, "z": z}:
                self.update(x, y, z)

    def _fetch_coordinates(self):
        """Fetch the object coordinates."""
        if self._row is None:
            model, _ = self.model
            row = Coordinates.get(model=model.id, raise_not_found=False)
            if row is not None:
                self._row = row.id
                self._valid = self._has_valid = row.valid
                self._x, self._y, self._z = row.x, row.y, row.z

    def _check_valid(self):
        """If valid, alter self._valid."""
        if not self._valid and all(
            c is not None for c in (self._x, self._y, self._z)
        ):
            self._valid = True

    def _create_row(self):
        """Createe a row, if necessary."""
        if self._row is None:
            model, _ = self.model
            row = Coordinates.get(model=model.id, raise_not_found=False)
            if row is None:
                row = Coordinates.create(
                    valid=self._valid,
                    x=self._x if self._x is not None else 0.0,
                    y=self._y if self._y is not None else 0.0,
                    z=self._z if self._z is not None else 0.0,
                    model=model.id,
                )
            self._row = row.id
            self._has_valid = row.valid
