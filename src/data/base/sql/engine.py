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

"""Module containing the database engine for TalisMUD.

This engine makes the link between database storage and the data being
stored.

The data is defined in a Pydantic class in Python.  Its table
structure can be automatically generated but this can be overridden.
Two types of data exist:

1.  Data without an in-game location.  Accounts, sessions and some
    world data can fall into that category.  These classes should
    inherit from `data.base.model.Model`.
2.  Data that has an in-game location.  Rooms, characters, in-game objects,
    vehicles, all have an optional location.  These classes
    should inherit from `data.base.node.Node` or
    `data.base.link.Link` (see these modules for details).

Data without any in-game location are usually stored in their specific
database table.  On the contrary, data with a specific in-game
location will be stored in a shared table (node or link).  This system
is used because all in-game objects have to remember where their location
is stored, therefore it is more convenient to have them reference
another row on the same table.

"""

from contextlib import contextmanager
from itertools import count
from pathlib import Path
import pickle
from queue import Queue
from typing import Any, Callable, Type, Union
from warnings import warn

from pydantic import Field
from sqlalchemy import (
    create_engine,
    delete,
    func,
    event,
    insert,
    select,
    update,
)
from sqlalchemy import Column, Index, UniqueConstraint
from sqlalchemy import ForeignKey, Integer, LargeBinary, String
from sqlalchemy.sql.roles import SQLRole
from sqlalchemy.sql.type_api import TypeEngine

from data.base.abc import ModelMetaclass
from data.base.model import Model
from data.base.sql.cache import Cache
from data.base.sql.locator import Locator
from data.base.sql.registry import BASE, REGISTRY
from data.base.sql.session import TalisMUDSession
from data.base.sql.types import SQL_TYPES
from data.decorators import LazyPropertyDescriptor
from data.handler.abc import BaseHandler


class SqliteEngine:

    """A data storage engine using Sqlite."""

    def __init__(self):
        self.file_name = ""
        self.tables = {}
        self.models = {}
        self.engine = None
        self.metadata = REGISTRY.metadata
        self.cache = Cache()
        self.locator = Locator(self)
        self.session = None
        self.loading = 0
        self.transaction_counter = count(1)
        self.current_transaction = None

    def init(
        self,
        file_name: str | Path | None = None,
        memory: bool = False,
        logging: bool | Callable[[str, tuple[Any]], None] = True,
    ) -> None:
        """Initialize the data engine.

        Args:
            file_name (str or Path): the file_name in which the database
                    is stored, or will be stored.  It can be a relative
                    or absolute file name.  If you want to just store
                    in memory, don't specify a file name and just set
                    the `memory` argument to `True`.
            memory (bool): whether to store this database in memory or
                    not?  If `True`, the file name is ignored.
            logging (bool or callable): if True (the default), log SQL queries.
                    A callable can also be specified: in this case,
                    the callable will be called whenever a query is
                    being sent, with two arguments: the query itself
                    as a string and the tuple of optional arguments (any type).

        """
        self.file_name = file_name if not memory else None
        self.logging = logging

        # Connect to the database.
        if memory:
            sql_file_name = ":memory:"
        else:
            if isinstance(file_name, str):
                file_name = Path(file_name)

            if file_name.absolute():
                sql_file_name = str(file_name)
            else:
                sql_file_name = str(file_name.resolve())
            self.file_name = file_name
        self.engine = create_engine(
            f"sqlite+pysqlite:///{sql_file_name}", future=True
        )
        self.session = TalisMUDSession(self.engine)
        self.session.talismud_engine = self

        # Add a function to override lower, as it only supports
        # ASCII in sqlite3.
        @event.listens_for(self.engine, "connect")
        def setup_lower(dbapi_connection, conn_rec):
            dbapi_connection.create_function("pylower", 1, str.lower)

        # Intercept requests to log them, if set.
        @event.listens_for(self.engine, "before_cursor_execute")
        def log_query(conn, cr, statement, parameters, *_):
            log = self.logging
            log = log if callable(log) else print
            if self.logging:
                log(statement.strip(), parameters)

        self.connection = self.engine.connect()
        self.tables = {}
        self.attr_tables = {}
        self.iattr_tables = {}

    def close(self):
        """Close the connection to the storage engine."""
        pass

    def destroy(self):
        """Close and destroy the storage engine."""
        tables = list(self.tables.values())
        tables += list(self.attr_tables.values())
        tables += list(self.iattr_tables.values())
        tables = [
            table for table in tables if table.__tablename__[0].isupper()
        ]

        for table in tables:
            instance = self.metadata.tables.get(table.__tablename__)
            if instance is not None:
                self.metadata.remove(instance)
                REGISTRY._dispose_cls(table)
        self.close()
        if self.file_name:
            self.file_name.unlink()

    def bind(self, models: set[Model] | None = None) -> None:
        """Bind the models to this engine.

        Args:
            models (set, optional): the set of models.

        """
        ModelMetaclass.engine = self
        to_bind = ModelMetaclass.models if models is None else models

        # Force models without a clear base model to be set as first-class
        # models.
        models = []
        names = {}
        for model in to_bind:
            names[model.__name__] = model
            if getattr(model.__config__, "external_attrs", False):
                for field in model.__fields__.values():
                    if model.is_base_field(field):
                        continue

                    if not model.is_primary_key(field):
                        field.field_info.extra["external"] = True
            else:
                for field in model.__fields__.values():
                    if model.is_primary_key(field):
                        continue

                    if not model.is_base_field(field):
                        field.field_info.extra["external"] = True

            base_model = getattr(model.__config__, "base_model", "")
            path = model.class_path
            self.models[path] = model
            first_class = base_model != path
            if table := getattr(model.__config__, "table", None):
                self._record_table(model, table)
            if attr_table := getattr(model.__config__, "attr_table", None):
                self._record_nattr(model, attr_table)
            if iattr_table := getattr(model.__config__, "iattr_table", None):
                self._record_inattr(model, iattr_table)

            if path in self.tables:
                continue

            setattr(model.__config__, "first_class", first_class)
            models.append(model)

        # Place first class models before
        models.sort(key=lambda model: 0 if model.is_first_class else 1)
        for model in models:
            self.bind_model(model)

        self.metadata.create_all(self.engine)

        for model in names.values():
            model.update_forward_refs(**names)

    def bind_model(self, model: Type[Model]) -> None:
        """Bind a new model, creating one or several tables.

        Models are Pydantic classes.  Each Pydantic field will match
        a SQL column in a table, unless this field is a specific attribute.
        Attributes are kept in a different table.  A third table can also
        be created to store indexed attributes with unique values
        for this model.

        Args:
            model (subclass of Model): the model class.

        """
        fields = {}
        external = indexed = False
        for key, field in model.__fields__.items():
            if model.is_external(field):
                external = True
                if field.field_info.extra.get("unique", False):
                    indexed = True
            else:
                column, kwargs = self.get_model_column(model, field)
                if model.is_primary_key(field):
                    pkey_name = key
                    pkey_column = column
                    kwargs["primary_key"] = True
                    if field.type_ is int:
                        kwargs["autoincrement"] = True

                if (
                    model.is_first_class
                    and field.type_ not in SQL_TYPES
                    and not model.is_safe(field)
                ):
                    warn(
                        f"the field {field.name} in model {model.class_path} "
                        "is not external, yet its type requires it to store "
                        "a pickled attribute.  While this might be "
                        "the desired behavior, if this field contains "
                        "references to external models, there might "
                        "very easily be a situation in which getting "
                        "a model raises a RecursionError.  It might be "
                        "wiser to set this field as external, like this:\n"
                        f"class {model.__name__}:\n\n"
                        f"    {field.name} = Field(..., external=True)\n"
                        "Alternatively, you can silence this warning by "
                        "specifying the 'safe' field value:\n"
                        f"class {model.__name__}:\n\n"
                        f"    {field.name} = Field(..., safe=True)"
                    )

                fields[key] = Column(column, **kwargs)

        model_name = model.__name__
        if model.is_first_class:
            if model.__config__.children:
                column, kwargs = self.get_model_column(model, str)
                fields["class_path"] = Column(column, **kwargs)
            fields["__tablename__"] = model_name
            table = type(model_name, (BASE,), fields)
            table.metadata = self.metadata
        else:
            table, *_ = self._get_three_tables(model.base_model)
        self._record_table(model, table)

        # If necessary, create the table to store external attributes.
        if external:
            table_name = f"{model_name}_attr"
            fields = {
                "__tablename__": table_name,
                "id": Column(Integer, primary_key=True),
                "name": Column(String),
                "value": Column(LargeBinary),
                "model": Column(
                    pkey_column,
                    ForeignKey(f"{table.__tablename__}.{pkey_name}"),
                ),
                "uix_nn": UniqueConstraint("name", "model", name="uix_nn"),
                "un_nn": Index("un_nn", "name", "model", unique=True),
            }
            nattr = type(table_name, (BASE,), fields)
            nattr.metadata = self.metadata
            self._record_nattr(model, nattr)

            # If there are external attributes to index.
            if indexed:
                table_name = f"{model_name}_iattr"
                fields = {
                    "__tablename__": table_name,
                    "id": Column(Integer, primary_key=True),
                    "name": Column(String),
                    "value": Column(LargeBinary),
                    "class_path": Column(String),
                    "model": Column(
                        pkey_column,
                        ForeignKey(f"{table.__tablename__}.{pkey_name}"),
                    ),
                    "uix_inn": UniqueConstraint(
                        "name", "value", "class_path", name="uix_inn"
                    ),
                    "un_inn": Index(
                        "un_inn", "name", "value", "class_path", unique=True
                    ),
                }
                inattr = type(table_name, (BASE,), fields)
                inattr.metadata = self.metadata
                self._record_inattr(model, inattr)

    def clear_cache(self):
        """Clear all the engine's cache."""
        self.cache.clear()
        self.locator.clear()
        LazyPropertyDescriptor.memory.clear()

    def log(self, message: str, arguments: list[Any] | None = None):
        """Log the message, if appropriate.

        Args:
            message (str): the message.
            arguments (list, optional): the list of arguments.

        """
        if log := self.logging:
            log(message, arguments)

    def get_model_column(
        self, model: Type[Model], field: Union[str, Field]
    ) -> tuple[TypeEngine, dict[str, Any]]:
        """Retrieve the column type for a given field.

        This method is called to determine the column type (and keyword
        arguments) of an internal field.

        Args:
            model (subclass of Model): the model object.
            field (str or Field): the field.

        Returns:
            (column, kwargs): where `column` is a column type used in
                SQLAlchemy and `kwargs` is a dictionary of strings
                to options.

        """
        type_ = getattr(field, "type_", field)
        if column_data := SQL_TYPES.get(type_):
            column, kwargs, *_ = column_data
            return (column, dict(kwargs))

        return (LargeBinary, {})

    def create_model(self, model_class: Type[Model], **kwargs) -> Model:
        """Create a new model object, storing it in the database.

        Args:
            model_class (Model subclass): the model class.

        Returns:
            model (Model): the newly-created model.

        """
        path = model_class.class_path
        table, nattr, inattr = self._get_three_tables(model_class)
        if model_class.is_first_class:
            fields = self.as_fields(model_class, kwargs)
        else:
            if "class_path" in kwargs:
                raise ValueError(
                    "the field 'class_path' is reserved.  "
                    "This name cannot be used"
                )

            fields = {"class_path": path}

            for key, value in kwargs.items():
                field = model_class.__fields__[key]
                if model_class.is_base_field(field):
                    fields.update(self.as_fields(model_class, {key: value}))

        # Save in the database.
        statement = insert(table).values(**fields)
        result = self.session.execute(statement)

        # Iterate over primary key fields.
        values = iter(tuple(result.inserted_primary_key))
        pkey = None
        pkeys = {}
        for field in model_class.__fields__.values():
            is_pk = field.field_info.extra.get("primary_key", False)
            if field.name not in kwargs and is_pk:
                value = next(values)
                pkeys[field.name] = value
                pkey = value

        # Save the model external attributes.
        if nattr:
            for key, value in kwargs.items():
                field = model_class.__fields__[key]
                is_pk = model_class.is_primary_key(field)
                is_external = model_class.is_external(field)
                if is_pk or not is_external:
                    continue

                statement = insert(nattr).values(
                    name=key,
                    value=pickle.dumps(value),
                    model=pkey,
                )
                self.session.execute(statement)

        # Save the indexed node attributes (INattr.
        if inattr:
            for key, value in kwargs.items():
                field = model_class.__fields__[key]
                is_pk = model_class.is_primary_key(field)
                is_external = model_class.is_external(field)
                is_unique = field.field_info.extra.get("unique", False)
                if is_pk or not is_external or not is_unique:
                    continue
                value = kwargs[key]
                statement = insert(inattr).values(
                    name=key,
                    value=pickle.dumps(value),
                    class_path=path,
                    model=pkey,
                )
                self.session.execute(statement)

        # Build and return the model.
        kwargs.update(pkeys)
        kwargs.pop("class_path", None)

        with self._load_model():
            model = model_class(**kwargs)
        self.cache.put(model)

        # Write the optional fields.
        if nattr:
            for key, value in model.__dict__.items():
                field = model_class.__fields__[key]
                is_pk = model_class.is_primary_key(field)
                is_external = model_class.is_external(field)
                if not is_pk and is_external and key not in kwargs:
                    statement = insert(nattr).values(
                        name=key,
                        value=pickle.dumps(value),
                        model=pkey,
                    )
                    self.session.execute(statement)

        self._prepare_model(model)
        return model

    def get_model(
        self, model_class: Type[Model], raise_not_found: bool = True, **kwargs
    ) -> Model | None:
        """Return the model with this class and ID.

        Args:
            model_class (Model subclass): the class.
            raise_not_found (bool, optional): if True (the default),
                    raise a NotFound exception if the model cannot be found.
                    Otherwise, return None.

        Additional keyword arguments are supported and should
        filter the result.

        Returns:
            model (instance of model class): if found, the model.
            None: the model couldn't be found and raise_not_found is False.

        Raises:
            NotFound if the model is not found and raise_not_found is True.

        """
        model = self.cache.get(model_class, **kwargs)
        if model is None:
            table, nattr, inattr = self._get_three_tables(model_class)
            pkeys = model_class.get_primary_keys_from_attrs(kwargs)
            keys = model_class.get_primary_keys_and_uniques_from_attrs(kwargs)
            if not pkeys and inattr:
                statement = (
                    select(table, nattr)
                    .join_from(table, nattr)
                    .join_from(table, inattr)
                )

                for name, value in kwargs.items():
                    statement = statement.where(
                        (inattr.name == name)
                        & (inattr.value == pickle.dumps(value))
                    )
            elif nattr:
                where = [
                    getattr(table, key) == value for key, value in keys.items()
                ]
                statement = (
                    select(table, nattr).join_from(table, nattr).where(*where)
                )
            else:
                where = [
                    getattr(table, key) == value for key, value in keys.items()
                ]
                statement = select(table).where(*where)

            if not model_class.is_first_class:
                statement = statement.where(
                    table.class_path == model_class.class_path
                )

            with self._load_model():
                rows = self.session.execute(statement).all()

            if len(rows) == 0:
                if raise_not_found:
                    raise ValueError("not found")

                return None

            obj = rows[0][0]
            if not model_class.is_first_class:
                model_class = ModelMetaclass.get_class_from_path(
                    obj.class_path
                )

            # Build and cache the object immediately.
            # No external attributes are read at this point.
            attrs = {
                column.name: getattr(obj, column.name)
                for column in obj.__table__.columns
                if getattr(obj, column.name, None) is not None
            }
            attrs.pop("class_path", ...)
            attrs = self.as_attributes(model_class, attrs)

            with self._load_model():
                model = model_class(**attrs)

            self.cache.put(model)

            # Build attributes.
            for row in rows:
                try:
                    attr = row[1]
                except IndexError:
                    pass
                else:
                    with self._load_model():
                        object.__setattr__(
                            model, attr.name, pickle.loads(attr.value)
                        )

            self._prepare_model(model)
            return model

        return model

    def count_models(
        self, model_class: Type[Model], query: SQLRole | None = None
    ) -> int:
        """Retrieve the number of models, optionally following a filter.

        Args:
            model_class (subclass of Model): the model to retrieve.
            query (SQLRole, optional): the query to filter with.

        Returns:
            number (int): the number of rows.

        If the model isn't a first-class model (like a node),
        perform the query on the parent table with an additional
        filter to retrieve only rows that describe this specific
        class.

        """
        table, nattr, inattr = self._get_three_tables(model_class)
        if not model_class.is_first_class:
            additional_filter = table.class_path == model_class.class_path
            if query is not None:
                query &= additional_filter
            else:
                query = additional_filter

        pkeys = model_class.get_primary_keys_from_class()
        pkey_name = tuple(pkeys.keys())[0]
        pkey = getattr(table, pkey_name)
        statement = select(func.count(pkey))
        if query is not None:
            statement = statement.where(query)

        return self.session.execute(statement).scalar_one()

    def select_models(
        self, model_class: Type[Model], query: SQLRole | None = None
    ) -> list[Model]:
        """Select several model objects with an optional query.

        The query has to be specified using the SQLAlchemy syntax,
        preferably using the `Model.table` property.

        Args:
            mode_class (subclass of Model): the model class.
            query (query, optional): the SQL query object.

        Returns:
            results (list of models): a list of Model objects.

        Example:

            >>> User.select(User.table.name == "something")
            [...]

        """
        table, nattr, inattr = self._get_three_tables(model_class)

        if not model_class.is_first_class:
            additional_filter = table.class_path == model_class.class_path
            if query is not None:
                query &= additional_filter
            else:
                query = additional_filter

        if nattr:
            statement = select(table, nattr).join_from(table, nattr)
        else:
            statement = select(table)

        if query is not None:
            statement = statement.where(query)

        with self._load_model():
            rows = self.session.execute(statement).all()

        already = set()
        models = []
        for row in rows:
            if path := getattr(row[0], "class_path", None):
                model_class = ModelMetaclass.get_class_from_path(path)

            if len(row) > 1:
                external = row[1:]
                row = row[0]
            else:
                external = ()
                row = row[0]

            # Check whether the object is cached.
            attrs = {
                column.name: getattr(row, column.name)
                for column in row.__table__.columns
                if getattr(row, column.name, None) is not None
            }
            attrs.pop("class_path", False)
            pkeys = model_class.get_primary_keys_from_attrs(attrs)
            model = self.cache.get(model_class, **pkeys)
            if model is None:
                attrs = self.as_attributes(model_class, attrs)

                with self._load_model():
                    model = model_class(**attrs)

                self.cache.put(model)

                # Build attributes.
                for attr in external:
                    with self._load_model():
                        object.__setattr__(
                            model, attr.name, pickle.loads(attr.value)
                        )

            self._prepare_model(model)
            pkeys = tuple(pkeys.items())
            if pkeys not in already:
                models.append(model)
                already.add(pkeys)

        return models

    def select_values(
        self, model_class: Type[Model], origin: SQLRole, query: SQLRole
    ) -> list[Any]:
        """Search values from a specified column.

        Args:
            origin (SQLRole): the column to return.
            query (SQLRole): the filter to use.

        Returns:
            values (list): the results.

        """
        table, nattr, inattr = self._get_three_tables(model_class)
        if not model_class.is_first_class:
            additional_filter = table.class_path == model_class.class_path
            if query is not None:
                query &= additional_filter
            else:
                query = additional_filter

        if nattr:
            statement = select(origin).join_from(table, nattr)
        else:
            statement = select(origin)

        if query is not None:
            statement = statement.where(query)

        values = self.session.execute(statement).all()
        values = [value[0] for value in values]

        return values

    def update(self, model: Model, key: str, value: Any):
        """Update the object.

        Args:
            model (Model): the model object.
            key (str): the key.
            value (Any): the new value.

        """
        if not self.loading:
            cls = type(model)
            field = cls.__fields__[key]
            info = field.field_info
            path = cls.class_path
            table, nattr, inattr = self._get_three_tables(cls)
            is_external = cls.is_external(field)
            pkey = cls.get_primary_key_from_model(model, sanitize=True)
            if nattr and is_external:
                statement = select(func.count(nattr.id)).where(
                    (nattr.name == key) & (nattr.model == pkey)
                )
                number = self.session.execute(statement).scalar_one()
                if number == 0:
                    statement = insert(nattr).values(
                        name=key, model=pkey, value=pickle.dumps(value)
                    )
                else:
                    statement = (
                        update(nattr)
                        .where((nattr.name == key) & (nattr.model == pkey))
                        .values(value=pickle.dumps(value))
                    )
            else:
                pkeys = self.as_fields(
                    cls, cls.get_primary_keys_from_model(model)
                )
                pkey_column = getattr(table, list(pkeys.keys())[0])
                pkey_value = list(pkeys.values())[0]
                attrs = self.as_fields(type(model), {key: value})
                statement = (
                    update(table)
                    .where(pkey_column == pkey_value)
                    .values(**attrs)
                )
            self.session.execute(statement)

            # Update unique indexes.
            if inattr and info.extra.get("unique", False):
                statement = (
                    update(inattr)
                    .where(
                        (inattr.name == key)
                        & (inattr.class_path == path)
                        & (inattr.model == pkey)
                    )
                    .values(value=pickle.dumps(value))
                )

                self.session.execute(statement)

        self.cache.put(model)

    def delete(self, model: Model):
        """Delete the specified model.

        Args:
            model (Model): the model object.

        The model will be removed from the database.  Using the linked cache,
        the references to the now-deleted object will be updated.

        """
        cls = type(model)
        table, nattr, inattr = self._get_three_tables(cls)
        pkeys = cls.get_primary_keys_from_model(model)
        pkey_column = getattr(table, list(pkeys.keys())[0])
        pkey_value = list(self.as_fields(type(model), pkeys).values())[0]
        statement = delete(table).where(pkey_column == pkey_value)
        self.session.execute(statement)

        # Remove attributes, if need be.
        if nattr:
            statement = delete(nattr).where(nattr.model == pkey_value)
            self.session.execute(statement)

        # Remove indexesd attributes, if need be.
        if inattr:
            statement = delete(inattr).where(inattr.model == pkey_value)
            self.session.execute(statement)

        # Remove from cache.
        self.cache.delete(model, self.refresh_field_for)

    def refresh_field_for(self, model: Model, key: str):
        """Refresh the model field from database."""
        cls = type(model)
        table, nattr, inattr = self._get_three_tables(cls)
        pkey = cls.get_primary_key_from_model(model)
        field = cls.__fields__[key]
        is_external = cls.is_external(field)
        if is_external:
            statement = select(nattr.value).where(
                (nattr.name == key) & (nattr.model == pkey)
            )
        else:
            column = list(cls.get_primary_keys_from_class().keys())[0]
            pkey_column = getattr(table, column)
            statement = select(getattr(table, key)).where(pkey_column == pkey)
        self.session.execute(statement)

        with self._load_model():
            values = self.session.execute(statement).one()
            if not values:
                return

        value = values[0]
        old_value = getattr(model, key, ...)
        new_value = pickle.loads(value)
        if old_value is not new_value:
            # Update the model.
            object.__setattr__(model, key, new_value)

    @contextmanager
    def _load_model(self):
        self.loading += 1
        try:
            yield
        finally:
            self.loading -= 1

    def _get_three_tables(
        self, model_class: Type[Model]
    ) -> tuple[BASE, BASE | None, BASE | None]:
        """Return table, attr, iattr tables."""
        path = model_class.class_path
        table = self.tables[path]
        attr_table = self.attr_tables.get(path)
        iattr_table = self.iattr_tables.get(path)
        return table, attr_table, iattr_table

    def _record_table(self, model_class: Type[Model], table: BASE) -> None:
        model_classes = Queue()
        model_classes.put(model_class)
        base = model_class.base_model
        while not model_classes.empty():
            model_class = model_classes.get()
            path = model_class.class_path
            if path not in self.tables:
                self.tables[path] = table

            if model_class is base:
                continue

            for parent in model_class.__bases__:
                if issubclass(parent, Model):
                    model_classes.put(parent)

    def _record_nattr(self, model_class: Type[Model], table: BASE) -> None:
        model_classes = Queue()
        model_classes.put(model_class)
        base = model_class.base_model
        while not model_classes.empty():
            model_class = model_classes.get()
            path = model_class.class_path
            if path not in self.attr_tables:
                self.attr_tables[path] = table

            if model_class is base:
                continue

            for parent in model_class.__bases__:
                if issubclass(parent, Model):
                    model_classes.put(parent)

    def _record_inattr(self, model_class: Type[Model], table: BASE) -> None:
        model_classes = Queue()
        model_classes.put(model_class)
        base = model_class.base_model
        while not model_classes.empty():
            model_class = model_classes.get()
            path = model_class.class_path
            if path not in self.iattr_tables:
                self.iattr_tables[path] = table

            if model_class is base:
                continue

            for parent in model_class.__bases__:
                if issubclass(parent, Model):
                    model_classes.put(parent)

    @staticmethod
    def as_fields(
        model_class: Type[Model], attributes: dict[str, Any]
    ) -> dict[str, Any]:
        """Return a dictionary of values ready to be stored.

        The returned dictionary is of the same length as
        the given dictionary, but its value are converted (if necessary),
        so that they can be directly stored in database.

        Args:
            model_class (subclass of Model): the model class.
            attributes (dict): the attributes.

        Returns:
            fields (dict): the field keys and values.

        """
        fields = {}
        default = (..., ..., pickle.dumps, ...)
        for key, value in attributes.items():
            field = model_class.__fields__[key]
            if model_class.is_external(field):
                continue

            _, _, convert, _ = SQL_TYPES.get(field.type_, default)
            if convert is not ...:
                value = convert(value)
            fields[key] = value

        return fields

    @staticmethod
    def as_attributes(
        model_class: Type[Model], fields: dict[str, Any]
    ) -> dict[str, Any]:
        """Convert a dictionary of stored attributes to model fields.

        The returned dictionary is of the same length as
        the given dictionary, but its value are converted (if necessary),
        so that they can be directly placed in a Pydantic model.

        Args:
            model_class (subclass of Model): the model class.
            fields (dict): the fields as stored.

        Returns:
            attributes (dict): the attribute keys and values.

        """
        attributes = {}
        default = (...,) * 3 + (pickle.loads,)
        for key, value in fields.items():
            field = model_class.__fields__[key]
            _, _, _, convert = SQL_TYPES.get(field.type_, default)
            if convert is not ...:
                value = convert(value)
            attributes[key] = value

        return attributes

    @staticmethod
    def _prepare_model(model: Type[Model]) -> None:
        for key, value in model.__dict__.items():
            if isinstance(value, BaseHandler):
                value.model = (model, key)
