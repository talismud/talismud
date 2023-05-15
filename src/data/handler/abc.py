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

"""Base handler, base class for all handlers."""

from typing import Any


class BaseHandler:

    """Base class for all handlers."""

    def __getstate__(self):
        return {
            key: value
            for key, value in self.__dict__.items()
            if key.startswith("_")
        }

    def __setstate__(self, attrs):
        self.__dict__.update(attrs)

    def __setattr__(self, key: str, value: any) -> None:
        object.__setattr__(self, key, value)
        if key != "model" and not key.startswith("_"):
            self.save()

    def save(self):
        """Save the handler in its owner."""
        model, attr = getattr(self, "model", (None, None))
        if model is not None and attr is not None:
            # Force the model to save.
            field = type(model).__fields__[attr]
            if field.field_info.extra.get("savable", True):
                type(model).engine.update(model, attr, self)

    def from_blueprint(self, value: Any) -> None:
        """Update the handler from the blueprint.

        Args:
            value (Any): the value to update.

        """
        pass
