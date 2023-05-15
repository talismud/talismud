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

"""Module containing the `Model` class from which all models should inherit."""

from typing import Any, Type

from pydantic import BaseModel, Field  # noqa: F401

from data.base.abc import ModelMetaclass
from data.decorators import LazyPropertyDescriptor


class Model(BaseModel, metaclass=ModelMetaclass):

    """Pydantic model for TalisMUD models.

    All models destined to be stored in database should inherit from
    this class.

    """

    def __repr_args__(self):
        attrs = type(self).get_primary_keys_from_model(self, unique=True)
        return tuple(attrs.items())

    def __hash__(self):
        return hash(
            type(self).get_primary_keys_from_model(self, as_tuple=True)
        )

    def __setattr__(self, key: str, value: Any) -> None:
        """Update the object."""
        cls_attr = getattr(type(self), key, None)
        if isinstance(cls_attr, (property, LazyPropertyDescriptor)):
            object.__setattr__(self, key, value)
        else:
            old_value = object.__getattribute__(self, key)
            super().__setattr__(key, value)
            try:
                ModelMetaclass.engine.update(self, key, value)
            except Exception as err:
                object.__setattr__(self, key, old_value)
                raise err from None

    def __reduce__(self):
        cls = type(self)
        attrs = cls.get_primary_keys_from_model(self)
        return (fetch, (cls, attrs))

    def is_from(self, class_path: str) -> bool:
        """Return whether this model is from a class with this class path.

        The specified class path can be incomplete.  For instance,
        if we try to `obj.is_from("data.object")`, then an object
        of `data.object.Object` will match.  You can therefore specify
        the beginning of the path (starting with `data`) and stop
        at any point.  This will match if the class path begins
        with your path followed by a dot.

        Also note that the parent classes of the specified
        objects are also browsed.

        Args:
            class_path (str): the class path to match.

        Returns:
            is_from (bool): if the object is from this class path.

        """
        partial_path = class_path + "."
        for cls in type(self).__mro__:
            path = getattr(cls, "class_path", None)
            if path is None:
                continue

            if path == class_path or path.startswith(partial_path):
                return True

        return False

    class Config:

        extra = "forbid"
        keep_untouched = (LazyPropertyDescriptor,)
        validate_assignment = True
        arbitrary_types_allowed = True
        copy_on_model_validation = None


def fetch(model_class: Type[Model], attrs: dict[str, Any]) -> Model | None:
    """Retrieve the specified model.

    Args:
        model_class (subclass of Model): the model.
        attrs (dict): the attributes.

    """
    return ModelMetaclass.engine.get_model(
        model_class, raise_not_found=False, **attrs
    )
