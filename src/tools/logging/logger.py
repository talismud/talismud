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

"""Logger module."""

from pathlib import Path
import traceback
from typing import Any, Type

from tools.logging.abc import LoggerMetaclass
from tools.logging.batch.abc import BaseBatch
from tools.logging.handler.abc import BaseHandler
from tools.logging.level import Level, LEVELS
from tools.logging.message import Message


class Logger(metaclass=LoggerMetaclass):

    """A logger class, containing handlers."""

    def __init__(self, name: str, directory: str | Path | None = None):
        self.name = name
        self.handlers = []
        self.sub_loggers = {}
        self.cap_level = None
        self.delayed = []
        self.init(directory=directory)

    def init(self, directory: str | Path | None = None):
        """Initialize a logger."""
        if directory is not None:
            if isinstance(directory, str):
                directory = Path(directory)
        self.directory = directory

    def add_handler(
        self,
        cls_handler: Type[BaseHandler],
        level: Level | str,
        cls_batch: Type[BaseBatch] | None = None,
        format: str | None = None,
        **kwargs,
    ) -> BaseHandler:
        """Add a handler for this logger.

        Args:
            cls_handler (subclass of BaseHandler): the handler class to create.
            level (Level or str): the handler's new level.  The level name
                    can be given as a string (like "warning" or "INFO",
                    case doesn't matter).
            cls_batch (subclass of BaseBatch or None): the class containing
                    the batch processor, if any.
            format (str): the format string for this handler.  If `None`
                    (te default), a default format is selected
                    for this handler.

        Additional keyword arguments are sent to the handler's `setup` method.

        Returns:
            handler (BaseHandler): the newly-created handler.

        """
        if isinstance(level, str):
            try:
                level = Level.__members__[level.upper()]
            except KeyError:
                raise KeyError(f"invalid level: {level!r}") from None

        handler = cls_handler(self, level=level, format=format)

        if cls_batch:
            batch = cls_batch(handler)
            handler.batch = batch

        handler.setup(**kwargs)
        self.handlers.append(handler)
        return handler

    def setup(self):
        """Set the logger up."""
        if directory := self.directory:
            directory.mkdir(parents=True, exist_ok=True)

    def log(self, level: Level, message: str):
        """Log the message if a handler is found."""
        message = Message.create_for(self, level, message)
        for handler in self.handlers:
            if handler.can_process(level, message):
                handler.process(level, message)

    def exception(self, message: str | None = None) -> None:
        """Log an error message with the traceback.

        Args:
            message (str or None): the message to log.  If not set,
                    just log the traceback.

        """
        message = "" if message is None else message
        message += "\n" + traceback.format_exc().strip()
        self.log(Level.ERROR, message)

    def group(
        self, identifier: Any, cap_level: Level = Level.WARNING
    ) -> "Logger":
        """Create or return a sub-logger for this identifier.

        This is useful to group messages but not log them, unless the group
        ends with an error.

        Args:
            identifier (any): the identifier.
            cap_level (level, optional): the level at which messages
                    should be logged and not grouped anymore.

        Returns:
            sub_logger (Logger): a sub-logger.

        """
        if (sub := self.sub_loggers.get(identifier)) is None:
            sub = Logger(f"{self.name}:{identifier}", self.directory)
            sub.cap_level = cap_level
            sub.handlers = self.handlers
            sub.log = sub.delay_log
            self.sub_loggers[identifier] = sub

        return sub

    def delay_log(self, level: Level, message: str) -> None:
        """Delay log unless the message is WARNING or greater.

        Args:
            level (Level): the message level.
            message (str): the message itself.

        """
        message = Message.create_for(self, level, message)
        self.delayed.append(message)
        if level >= self.cap_level:
            # Log everything.
            self.log_group()

    def log_group(self):
        """Log all the messages in the group."""
        for message in self.delayed:
            for handler in self.handlers:
                level = LEVELS[message.level]
                if handler.can_process(level, message):
                    handler.process(level, message)
        self.delayed.clear()
