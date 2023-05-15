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

from itertools import chain
import pickle
from typing import Any, Optional, Type, TYPE_CHECKING

from pydantic import Field
from pydantic.main import ModelMetaclass as BaseModelMetaclass
from sqlalchemy.sql.roles import SQLRole

from data.base.sql.registry import BASE

if TYPE_CHECKING:
    from data.base.model import Model


class ModelMetaclass(BaseModelMetaclass):

    """Metaclass common to all models stored in TalisMUD."""

    models = set()
    paths = {}
    engine = None

    def __new__(
        cls, name: str, bases: tuple[type], attrs: dict[str, Any]
    ) -> type:
        new_cls = super().__new__(cls, name, bases, attrs)
        ModelMetaclass.models.add(new_cls)
        ModelMetaclass.paths[new_cls.class_path] = new_cls
        new_cls.__config__.primary_keys = new_cls.get_primary_keys_from_class()
        new_cls.__config__.children = set()
        base = new_cls.base_model
        if base is not new_cls:
            base.__config__.children.add(new_cls)

        return new_cls

    @property
    def class_path(cls) -> str:
        return f"{cls.__module__}.{cls.__qualname__}"

    @property
    def base_model(cls) -> Type["Model"]:
        """Return the base model of the specified model class.

        A model class can inherit from a base class that defines
        its structure.  First class models do not have a base class,
        just themselves (so they store all their data in a specific table).
        Models that do have a base class configured record their data in
        a table shared with other classes, thus they need to remember
        the `class_path` for every row in the table.

        Args:
            None.

        Returns:
            base_model (subclass of Model): the model base class.

        """
        base_model = getattr(cls.__config__, "base_model", "")

        # Try to get the base model.
        if not base_model:
            return cls

        base = cls.get_class_from_path(base_model, raise_error=False)
        if base is None:
            raise ValueError(
                f"the {cls} class model defines "
                f"{base_model!r} has base model, but this model "
                "path cannot be found"
            )

        return base

    @property
    def is_first_class(cls) -> bool:
        """Return whether this model is a first class model."""
        return cls.base_model is cls

    @property
    def table(cls) -> BASE:
        """Return the class table from the engine."""
        path = cls.base_model.class_path
        return cls.engine.tables[path]

    @property
    def nattr(cls) -> BASE:
        """Return the class attribute table from the engine."""
        path = cls.base_model.class_path
        return cls.engine.attr_tables[path]

    @property
    def inattr(cls) -> BASE:
        """Return the class indexed attribute table from the engine."""
        path = cls.base_model.class_path
        return cls.engine.iattr_tables[path]

    def is_base_field(cls, field: Field) -> bool:
        """Return whether this field is a base field.

        Base fields are defined in base models.

        Args:
            field (Field): the field to test.

        Returns:
            base (bool): whether this field is a base field or not.

        """
        base = cls.base_model
        return field.name in base.__fields__

    def is_primary_key(cls, field: Field) -> bool:
        """Return whether this field is a primary key.

        Args:
            field (Field): the field to test.


        Returns:
            primary_key (bool): whether this field is a primary key.

        """
        return field.field_info.extra.get("primary_key", False)

    def is_external(cls, field: Field) -> bool:
        """Return whether this field is external (stored in another table).

        Args:
            field (Field): the field to test.

        Returns:
            external (bool): whether this field is an external field or not.

        """
        if cls.is_primary_key(field):
            external = False
        else:
            external = field.field_info.extra.get("external", False)

        return external

    def is_safe(cls, field: Field) -> bool:
        """Return whether this field is safe.

        Args:
            field (Field): the field to test.

        Returns:
            safe (bool): whether this field is safe.

        """
        return field.field_info.extra.get("safe", False)

    def create(cls, **kwargs):
        """Create a node and store it in the database.

        Args:
            Other attributes can also be used.
            They should match the object fields.

        Returns:
            node (Node or subclass): the node object.

        """
        return ModelMetaclass.engine.create_model(cls, **kwargs)

    def get(cls, **kwargs):
        """Try to retrieve the object from storage, raises NotFound if error.

        Primary key or unique fields should be specified as keyword arguments.

        """
        return ModelMetaclass.engine.get_model(cls, **kwargs)

    def get_or_none(cls, **kwargs) -> Optional["Model"]:
        """Try to retrieve the object from storage, return None if not found.

        Primary key or unique fields should be specified as keyword arguments.

        """
        kwargs["raise_not_found"] = False
        return ModelMetaclass.engine.get_model(cls, **kwargs)

    def all(cls) -> list["Model"]:
        """Retrieve the list of all stored models.

        WARNING:
            Do this only if you are quite confident the table
            isn't big or loading absolutely every row is necessary.
            In doubt, prefer using `select` with a filter query.

        Returns:
            objects (list of Model): the list of all model objects.

        """
        return ModelMetaclass.engine.select_models(cls)

    def count(cls, query: SQLRole | None = None) -> int:
        """Retrieve the number of models, optionally following a filter.

        Args:
            query (SQLRole, optional): the query to filter with.

        Returns:
            number (int): the number of rows.

        If the model isn't a first-class model (like a node),
        perform the query on the parent table with an additional
        filter to retrieve only rows that describe this specific
        class.

        """
        return ModelMetaclass.engine.count_models(cls, query)

    def select(cls, query: SQLRole) -> list["Model"]:
        """Select several model objects from the database.

        The query has to be specified using the SQLAlchemy syntax,
        preferably using the `Model.table` property.

        Args:
            query (query): the SQL query object.

        Returns:
            results (list of models): a list of Model objects.

        Example:

            >>> User.select(User.table.name == "something")
            [...]

        """
        return ModelMetaclass.engine.select_models(cls, query)

    def delete(self, model: "Model"):
        """Delete the specified model."""
        ModelMetaclass.engine.delete(model)

    def get_primary_keys_from_class(
        cls, unique: bool = False
    ) -> dict[str, Field]:
        """Return the primary key fields in a dictionary.

        Args:
            unique (bool, optional): also return unique fields.

        Returns:
            primary_keys (dict): the primary key fields, with field names
                    as keys and fields as values.

        """
        pkeys = {}
        for field in cls.__fields__.values():
            store = False
            if field.field_info.extra.get("primary_key", False):
                store = True
            elif unique and field.field_info.extra.get("unique", False):
                store = True

            if store:
                pkeys[field.name] = field

        return pkeys

    def get_primary_keys_from_values(cls, *values) -> dict[str, Any]:
        """Return the primary key fields from values in a dictionary.

        Each value is to be speicifed as an additional positional argument.

        Args:
            Values.

        Returns:
            primary_keys (dict): the primary key fields, with field names
                    as keys and matching values as values.

        """
        pkeys = {}
        primary_fields = cls.get_primary_keys_from_class()
        values = iter(list(values))
        for key, field in primary_fields.items():
            value = next(values)
            pkeys[key] = value

        return pkeys

    def get_primary_keys_from_attrs(
        cls, attrs: dict[str, Any], sanitize: bool = True
    ) -> dict[str, Any]:
        """Return the primary key fields from attributes.

        Args:
            attrs (dict): the attributes.
            sanitize (bool): if set to True (the default),
                    attribute values will be "sanitized", converted
                    to their database value if necessary.

        Returns:
            primary_keys (dict): the primary key fields, with field names
                    as keys and values as values.

        """
        if sanitize:
            attrs = ModelMetaclass.engine.as_fields(cls, attrs)

        pkeys = {}
        primary_fields = cls.get_primary_keys_from_class()
        for key, field in primary_fields.items():
            value = attrs.get(key, ...)
            if value is not ...:
                pkeys[key] = value

        return pkeys

    def get_primary_keys_and_uniques_from_attrs(
        cls, attrs: dict[str, Any], sanitize: bool = True
    ) -> dict[str, Any]:
        """Return the primary key and unique fields from attributes.

        Args:
            attrs (dict): the attributes.
            sanitize (bool): if set to True (the default),
                    attribute values will be "sanitized", converted
                    to their database value if necessary.

        Returns:
            primary_keys (dict): the primary key and unique fields,
                    with field names as keys and values as values.

        """
        if sanitize:
            attrs = ModelMetaclass.engine.as_fields(cls, attrs)

        keys = {}
        for key, value in attrs.items():
            field = cls.__fields__[key]
            pk = field.field_info.extra.get("primary_key", False)
            unique = field.field_info.extra.get("unique", False)
            if pk or unique:
                keys[key] = value

        return keys

    def get_primary_keys_from_model(
        cls,
        model: "Model",
        as_tuple: bool = False,
        sanitize: bool = False,
        unique: bool = False,
    ) -> tuple[Any] | dict[str, Any]:
        """Return the primary key values from a model.

        If `as_tuple` is set to `True`, return a flattened tuple of
        `(key1, value1, key2, value2, ...)`.  Otherwise, return a dictionary.

        Args:
            model (Model): the model.
            as_tuple (bool, optional): should a tuple be returned?
            sanitize (bool): get ready to store.
            unique (bool): also return unique fields.

        Returns:
            primary_keys (dict or tuple): the primary keys, with field names
                    as keys and model values as values.  If `as_tuple`
                    is set to `True`, return a flattened tuple instead.

        """
        pkeys = {}
        for key in cls.get_primary_keys_from_class(unique=unique).keys():
            value = getattr(model, key)
            pkeys[key] = value

        if sanitize:
            pkeys = ModelMetaclass.engine.as_fields(cls, pkeys)

        if as_tuple:
            pkeys = sorted([(key, value) for key, value in pkeys.items()])
            pkeys = tuple(chain.from_iterable(pkeys))

        return pkeys

    def get_primary_key_from_model(
        cls, model: "Model", sanitize: bool = False
    ) -> Any:
        """Return the only primary key for this model.

        If this model has more than one primary key, an exception is raised.

        Args:
            model (Model): the model.
            sanitize (bool): return as ready to store.

        Returns:
            key (Any): the primary key value for this model.

        Raises:
            ValueError if the model has more than one primary keys.

        """
        pkeys = cls.get_primary_keys_from_model(model, sanitize=sanitize)
        if len(pkeys) != 1:
            raise ValueError(
                f"there is {len(pkeys)} primary key attributes "
                f"on {cls}, only one is supported"
            )

        return list(pkeys.values())[0]

    def search_attributes(cls, name: str, value: Any) -> tuple[Any]:
        """Search objects with an attribute with this value.

        This will return a list of primary keys.
        If this is a node (most common), then `search_attributes`
        will return a list of IDs.

        Args:
            name (str: the attribute name.
            value (Any): the attribute value to match.

        The search is performed in the table's attributes (nattr).
        If this table has no such matching attribute tables,
        it will fail.  In other words, classes inheriting from `Model`
        must have at least one external attribute to qualify.
        Classes inheriting indirectly from `Node` store all
        their attributes in a `nattr` table.

        Returns:
            list: a list of primary keys of objects with a matching attribute.

        """
        nattr = cls.nattr
        query = (nattr.name == name) & (nattr.value == pickle.dumps(value))
        return cls.engine.select_values(cls, nattr.model, query=query)

    def get_attributes(
        cls, name: str, query: SQLRole | None = None
    ) -> list[Any]:
        """Return the attribute values matching a specific query.

        Args:
            name (str): the attribute name.
            query (SQLRole): the query to match.

        Returns:
            values (list): the values.

        """
        nattr = cls.nattr
        if query is None:
            query = nattr.name == name
        else:
            query &= nattr.name == name

        raw = cls.engine.select_values(cls, nattr.value, query)
        values = []
        for value in raw:
            value = pickle.loads(value)
            values.append(value)

        return values

    @staticmethod
    def get_class_from_path(
        class_path: str, raise_error: bool = True
    ) -> Type["Model"]:
        """Return, if found, the class matching this class path."""
        cls = ModelMetaclass.paths.get(class_path)
        if cls is None and raise_error:
            raise ValueError(
                f"cannot find the class matching the path: {class_path!r}"
            )

        return cls
