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

"""Game service."""

import asyncio
from datetime import datetime
import pickle
from queue import Queue
from typing import Any
from uuid import UUID

from data.delay import Delay as DbDelay
from service.base import BaseService
from service.origin import Origin
from service.shell import Shell
from tools.delay import Delay

# Portal commands.
PORTAL_COMMANDS = Queue()


class Service(BaseService):

    """The game's main service."""

    name = "game"
    sub_services = ("host", "data", "mudio", "world")

    async def init(self):
        """Asynchronously initialize the service.

        This method should be overridden in subclasses.  It is called by
        `start`` before sub-services are created.  It plays the role of
        an asynchronous constructor for the service, and service attributes
        often are created there for consistency.

        """
        self.output_event = asyncio.Event()
        self.game_id = None
        self.console = Shell({})

    async def setup(self):
        """Set the game up."""
        self.data = self.services["data"]
        self.host = self.services["host"]
        self.mudio = self.services["mudio"]
        self.world = self.services["world"]
        self.host.schedule_hook("connected", self.connected_to_CRUX)
        self.data.setup_shell(self.console)

        # Add all services to the Shell.
        services = Queue()
        services.put_nowait(self)
        while not services.empty():
            service = services.get_nowait()
            self.console.locals[service.name.lower()] = service
            for sub_service in service.services.values():
                services.put_nowait(sub_service)

    async def cleanup(self):
        """Clean the service up before shutting down."""

    def restore_delays(self):
        """Schedule all persistent delays."""
        now = datetime.utcnow()
        Delay._game_service = self
        for persistent in DbDelay.all():
            delta = persistent.expire_at - now
            seconds = delta.total_seconds()
            if seconds < 0:
                seconds = 0

            callback, args, kwargs = pickle.loads(persistent.pickled)
            obj = Delay.schedule(seconds, callback, *args, **kwargs)
            obj.persistent = persistent

    def call_delay(self, delay: Delay):
        """Call ths delay."""
        with self.data.engine.session.begin():
            delay._execute()

        loop = asyncio.get_event_loop()
        loop.create_task(self.mudio.send())

    async def connected_to_CRUX(self, writer):
        """The host is connected to the CRUX server."""
        host = self.services["host"]
        self.logger.debug("host: send register_game")
        await host.send_cmd(
            writer, "register_game", dict(pid=self.process.pid, has_admin=True)
        )

    async def error_read(self):
        """Cannot read from CRUX anymore, prepare to shut down."""
        self.logger.warning(
            "A read error happened on the connection to CRUX, "
            "stop the process."
        )

        with self.data.engine.session.begin():
            Delay.persist()

        self.process.should_stop.set()

    async def error_write(self):
        """Cannot write to CRUX anymore, prepare to shut down."""
        self.logger.warning(
            "A write error happened on the connection to CRUX, "
            "stop the process."
        )

        with self.data.engine.session.begin():
            Delay.persist()

        self.process.should_stop.set()

    async def send_portal_commands(self):
        """Send portal commands through CRUX."""
        host = self.services["host"]
        while not PORTAL_COMMANDS.empty():
            command, args = PORTAL_COMMANDS.get_nowait()
            await host.send_cmd(host.writer, command, args)

    # Command handlers
    async def handle_registered_game(
        self,
        origin: Origin,
        game_id: str,
        sessions: list[UUID],
        **kwargs,
    ):
        """A new game process wants to be registered."""
        self.logger.info(f"The game is now registered under ID {game_id}")
        self.game_id = game_id

        with self.data.engine.session.begin():
            self.restore_delays()

    async def handle_stop_game(self, origin: Origin, game_id: str):
        """Stop this game process."""
        self.logger.info(f"The game of ID {game_id} is asked to stop.")
        if self.game_id == game_id:
            self.logger.debug("Shutting down the game...")

            with self.data.engine.session.begin():
                Delay.persist()

            self.process.should_stop.set()

    async def handle_input(
        self,
        origin: Origin,
        session_id: UUID,
        command: bytes,
        input_id: int,
        sent: datetime,
        **kwargs,
    ):
        """Handle input from Telnet clients.

        Telnet clients send commands and expect output
        (not necessarily right away).

        Args:
            session_id (UUID): the session from which this command come.
            command (bytes): the sent bytes.
            input_id (int): the ID of this command.
            sent (datetime): the moment the command was sent.

        This number, generated by the Telnet portal, is unique to
        this input.  Including it in the answer allows to make sure
        the link between input and output is established.  Of course,
        the MUD can contact other sessions as well, or even contact
        them after a few seconds, in which case this new output
        won't be linked to an input.

        Answer:
            When the command is received (not processed yet), send an answer
            right away.  This is useful for stats.  When the command
            is processed, send an 'output' message.

        """
        data = self.data
        try:
            with data.engine.session.begin():
                session = self.data.get_session(session_id)
                command = command.decode(session.encoding, errors="replace")
                self.mudio.handle_input(session, command, sent)
        except Exception:
            self.logger.exception("Cannot process input")
        finally:
            try:
                with data.engine.session.begin():
                    await self.mudio.send_output(input_id)
                    await self.send_portal_commands()
            except Exception:
                self.logger.exception("Cannot send output")

    async def handle_new_session(
        self,
        origin: Origin,
        session_id: UUID,
        creation: datetime,
        ip_address: str,
        secured: bool,
        **kwargs,
    ):
        """Handle a new connection session.

        The session is connected to Telnet (whether Telnet
        or Telnet-SSL).  The portal then contacts the game process
        to let it know a new session has been created.  The portal
        doesn't store the session except in memory, but the game stores it
        in its database.

        Args:
            session_id (UUID): the new session ID (should be unique).
            creation (datetime): the datetime at which this session connected.
            ip_address (str): the session's IP address.
            secured (bool): is it a secured session (SSL)?

        Answer:
            None.

        """
        self.logger.debug(f"Connection of a new session: {session_id}")
        with self.data.engine.session.begin():
            session = await self.data.new_session(
                session_id, creation, ip_address, secured
            )

            session.context.enter()

            await self.mudio.send_output(0)
            await self.send_portal_commands()

    async def handle_disconnect_session(
        self,
        origin: Origin,
        session_id: UUID,
        **kwargs,
    ):
        """Handle a disconnected session.

        Args:
            session_id (UUID): the disconnected session ID.

        Answer:
            None.

        """
        self.logger.debug(f"Deletion of a session: {session_id}")

        with self.data.engine.session.begin():
            deletion = self.data.delete_session(session_id)

        await self.host.answer(origin, dict(deletion=deletion))
        await self.send_portal_commands()

    async def handle_shell(self, origin: Origin, code: str):
        """Execute arbitrary Python code.

        Args:
            code (str): the Python code to execute.

        Response:
            The 'result' command with the output.

        """
        host = self.services["host"]
        data = self.data
        with data.engine.session.begin():
            more = self.console.push(code)
        prompt = "... " if more else ">>> "

        if host.writer:
            display = self.console.output
            await host.answer(origin, dict(display=display, prompt=prompt))

        await self.mudio.send_output(0)
        await self.send_portal_commands()

    async def handle_blueprints(
        self,
        origin: Origin,
        **kwargs,
    ):
        """Send back the list of blueprints.

        Args:
            None.

        Answer:
            blueprints: the list of blueprints.

        """
        blueprints = {}
        for name, blueprint in self.world.blueprints.items():
            blueprints[name] = blueprint.content

        await self.host.answer(origin, dict(blueprints=blueprints))

    async def handle_update_document(
        self,
        origin: Origin,
        blueprint: str,
        document_id: int,
        definition: dict[str, Any],
        **kwargs,
    ):
        """Update a specific object in a blueprint.

        Args:
            blueprint (str): the unique name of the blueprint.
            document_id (int): the unique ID of the document eo edit within it.
            definition (dict): the new document definition.

        Answer:
            (updated, reason): where updated is a boolean and reason is str.

        """
        blueprint = self.world.blueprints.get(blueprint.lower())
        if blueprint is None:
            response = (False, "cannot find this blueprint")
        else:
            if document_id not in blueprint.ids:
                response = (False, "cannot find this document")
            else:
                self.world.update_document(
                    blueprint.unique_name, document_id, definition
                )
                response = (True, "all clear")

        await self.host.answer(origin, dict(status=response))
