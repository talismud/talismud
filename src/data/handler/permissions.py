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

"""Permissions custom field, to hold permissions."""

from typing import Sequence

from dynaconf import settings

from data.handler.abc import BaseHandler


class PermissionHandler(BaseHandler):

    """A set of permissions."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._permissions = set()

    def add(self, permission: str):
        """Add permissions.

        Args:
            permission (str): the permission to add.

        """
        if permission not in self._permissions:
            self._permissions.add(permission)
            self._extrapolate()
            self.save()

    def clear(self):
        """Remove all permissions."""
        if len(self._permissions) > 1:
            self._permissions.clear()
            self.save()

    def discard(self, permission: str):
        """Remove a permission.

        Args:
            permission (str): the permission to remove.

        """
        if permission in self._permissions:
            self._permissions.discard(permission)
            self._extrapolate()
            self.save()

    def has(self, permission: str) -> bool:
        """Return whether this permission is in the set.

        Args:
            permission (str): the permission to test.

        Returns:
            has (bool): whether this set has this permission.

        """
        return permission in self._permissions

    def remove(self, permission: str):
        """Remove a permission.

        Args:
            permission (str): the permission to remove.

        """
        if permission in self._permissions:
            self._permissions.remove(permission)
            self._extrapolate()
            self.save()

    def _extrapolate(self) -> None:
        """Use the set groups to adjust real permissions."""
        self._permissions = self._extend_groups(self._permissions)

    @staticmethod
    def _extend_groups(
        permissions: Sequence[str], group: set[str] | None = None
    ) -> set[str]:
        """Extract permissions and sub-permissions recursively."""
        group = group if group is not None else set()
        for permission in permissions:
            if permission not in group:
                group.add(permission)
                sub_groups = settings.GROUP.get(permission.lower(), [])
                if sub_groups:
                    PermissionHandler._extend_groups(sub_groups, group)

        return group
