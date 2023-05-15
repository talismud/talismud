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

"""Blueprint handler, to store blueprints for a data."""

from data.base.blueprint import Blueprint
from data.decorators import lazy_property
from data.handler.abc import BaseHandler


class BlueprintHandler(BaseHandler):

    """A set of blueprints.

    Blueprints are saved as strings (their unique name), the blueprint
    objects themselves are cached when retrieved.

    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._blueprints = set()

    def __repr__(self):
        return f"<BlueprintHandler({self._blueprints})>"

    @lazy_property
    def blueprints(self):
        """Return the set of blueprints and cache it."""
        blueprints = set()
        for name in self._blueprints:
            blueprint = Blueprint.service.blueprints.get(name)
            if blueprint is not None:
                blueprints.add(blueprint)

        return blueprints

    @blueprints.setter
    def blueprints(self, blueprints):
        """Update the blueprints."""

    def add(self, blueprint: str | Blueprint) -> None:
        """Add a blueprint for this object.

        Args:
            blueprint (str or Blueprint): the blueprint to add.

        """
        if isinstance(blueprint, str):
            name = blueprint
            blueprint = Blueprint.service.blueprints.get(name)
            if blueprint is None:
                raise ValueError(f"cannot find the blueprint {name!r}")
        else:
            name = blueprint.unique_name

        if name not in self._blueprints:
            self._blueprints.add(name)
            self.blueprints = self.blueprints | {blueprint}
            self.save()

    def clear(self):
        """Remove all blueprints."""
        if len(self._blueprints) > 1:
            self._blueprints.clear()
            self.blueprints = set()
            self.save()

    def discard(self, blueprint: str | Blueprint):
        """Remove a blueprint.

        Args:
            blueprint (str or Blueprint): the blueprint to remove.

        """
        if isinstance(blueprint, str):
            name = blueprint
        else:
            name = blueprint.unique_name

        if name in self._blueprints:
            self._blueprints.discard(name)
            self.blueprints = {
                blueprint
                for blueprint in self.blueprints
                if blueprint.unique_name != name
            }
            self.save()

    def has(self, blueprint: str | Blueprint) -> bool:
        """Return whether this blueprint is in the set.

        Args:
            blueprint (str or Blueprint): the blueprint to test.

        Returns:
            has (bool): whether this set has this blueprint.

        """
        if isinstance(blueprint, str):
            name = blueprint
        else:
            name = blueprint.unique_name

        return name in self._blueprints

    def remove(self, blueprint: str | Blueprint):
        """Remove a blueprint.

        Args:
            blueprint (str or Blueprint): the blueprint to remove.

        """
        if isinstance(blueprint, str):
            name = blueprint
        else:
            name = blueprint.unique_name

        if name in self._blueprints:
            self._blueprints.remove(name)
            self.blueprints = {
                blueprint
                for blueprint in self.blueprints
                if blueprint.unique_name != name
            }
            self.save()
