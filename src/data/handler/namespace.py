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

"""Namespace custom field."""

import pickle
from typing import Any

from pygasus.model import CustomField

_NOT_SET = object()


class Namespace(dict):

    """A namespace, holding attribute-like flexible data."""

    def __init__(self, *args, **kwargs):
        self.parent = None
        self.field = None
        self._bytes = None
        super().__init__(*args, **kwargs)

    def __getattr__(self, key):
        if key in ("parent", "field", "_bytes"):
            return object.__getattr__(self, key)

        self._load()
        value = super().__getitem__(key)
        return value

    def __setattr__(self, key, value):
        if key in ("parent", "field", "_bytes"):
            object.__setattr__(self, key, value)
        else:
            self._load()
            super().__setitem__(key, value)
            self.save()

    def __delattr__(self, key):
        if key in ("parent", "field", "_bytes"):
            object.__delattr__(self, key)
        else:
            self._load()
            super().__delitem__(key)
            self.save()

    def __contains__(self, element: Any):
        self._load()
        return super().__contains__(element)

    def __repr__(self):
        self._load()
        return super().__repr__()

    def __str__(self):
        self._load()
        return super().__str__()

    def __getitem__(self, key):
        self._load()
        value = super().__getitem__(key)
        return value

    def __setitem__(self, key, value):
        self._load()
        super().__setitem__(key, value)
        self.save()

    def __delitem__(self, key):
        self._load()
        super().__delitem__(key)
        self.save()

    def clear(self):
        self._load()
        if self:
            super().clear()
            self.save()

    def get(self, key: str, value: Any = _NOT_SET):
        self._load()
        if value is _NOT_SET:
            return super().get(key)

        return super().get(key)

    def items(self):
        self._load()
        return super().items()

    def keys(self):
        self._load()
        return super().keys()

    def pop(self, key, default=_NOT_SET):
        self._load()
        if default is _NOT_SET:
            value = super().pop(key)
        else:
            value = super().pop(key, default)
        self.save()
        return value

    def popitem(self):
        self._load()
        pair = super().popitem()
        self.save()
        return pair

    def setdefault(self, key, default=None):
        self._load()
        value = super().setdefault(key, default)
        self.save()
        return value

    def update(self, *args, **kwargs):
        self._load()
        super().update(*args, **kwargs)
        self.save()

    def values(self):
        self._load()
        return super().values()

    def _load(self):
        """Load, if necessary, the dictionary."""
        if self._bytes is not None:
            # Actually load the dictionary.
            super().update(pickle.loads(self._bytes))
            self._bytes = None

    def save(self):
        """Save the dictionary into the parent."""
        self._load()
        type(self.parent).repository.update(
            self.parent, self.field, {}, self.copy()
        )


class NamespaceField(CustomField):

    """A dictionary stored in a pickled bytestring."""

    field_name = "namespace"

    def add(self):
        """Add this field to a model.

        Returns:
            annotation type (Any): the type of field to store.

        """
        return bytes

    def to_storage(self, value):
        """Return the value to store in the storage engine.

        Args:
            value (Any): the original value in the field.

        Returns:
            to_store (Any): the value to store.
            It must be of the same type as returned by `add`.

        """
        return pickle.dumps(value.copy())

    def to_field(self, value: bytes):
        """Convert the stored value to the field value.

        Args:
            value (Any): the stored value (same type as returned by `add`).

        Returns:
            to_field (Any): the value to store in the field.
            It must be of the same type as the annotation hint used
            in the model.

        """
        namespace = Namespace()
        namespace._bytes = value
        return namespace
