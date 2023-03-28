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

"""Package containing the basic data storage mechanism for TalisMUD.

TalisMUD uses a database to store its world data, like rooms, exits, objects,
or characters.  It uses a generic model representation with only two elements
from which all information is createed:

1.  Node: a node represents an information, possibly situated in a location
    (another node) and containing other nodes as children.  Rooms are
    the most simple representation of nodes: they are not located inside
    anything (except if one wishes to create a vehicle with rooms)
    and they can contain several objects or characters.  Most other
    world elements are nodes as well: characters are nodes (their location
    is the room where they stand, their contents is their equipment or
    inventory).  Objects are nodes too (their location is the room
    where they are or the object containing them), vehicles can be nodes
    as well (perhaps without location, but might contain other rooms).
2.  Link: a link represents a connection between two nodes.  The most
    common example is exits: exits usually connect one room to the next.
    However, they could also connect less obvious things, like a vehicle
    to a room, or even a character to an object.  A link is a one-way
    connection between two nodes, though the destination node might
    not be specified at the time.

In terms of storage, nodes and links are stored in two different database
tables.  Both can also contain additional information which is serialized
(see the `data.base.attributes` module for examples).

"""

from typing import Callable

from data.base.sql.engine import SqliteEngine


def handle_data(
    logging: Callable[[str, str], None] = None, memory: bool = False
) -> SqliteEngine:
    """Connect to the database and bind models."""
    from data.account import Account
    from data.base.coordinates import Coordinates
    from data.character import Character
    from data.delay import Delay
    from data.exit import Exit
    from data.generator import Generator
    from data.npc import NPC
    from data.object import Object
    from data.prototype.object import ObjectPrototype
    from data.player import Player
    from data.room import Room
    from data.session import Session

    engine = SqliteEngine()
    kwargs = dict(file_name="talismud.db", memory=memory, logging=logging)
    engine.init(**kwargs)
    engine.bind(
        {
            Account,
            Character,
            Coordinates,
            Delay,
            Exit,
            Generator,
            NPC,
            Object,
            ObjectPrototype,
            Player,
            Room,
            Session,
        }
    )
    return engine
