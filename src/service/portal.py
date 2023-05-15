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

"""Portal service."""

import asyncio
import base64
from uuid import UUID

from async_timeout import timeout as async_timeout

from process.base import Process
from service.base import BaseService
from service.origin import Origin


class Service(BaseService):

    """Portal service."""

    name = "portal"
    sub_services = ("crux", "telnet")

    @property
    def hosts(self):
        """Return the hosts of the CRUX service."""
        service = self.services.get("crux")
        if service:
            return service.readers

    async def init(self):
        """Asynchronously initialize the service.

        This method should be overridden in subclasses.  It is called by
        `start`` before sub-services are created.  It plays the role of
        an asynchronous constructor for the service, and service attributes
        often are created there for consistency.

        """
        self.game_id = None
        self.game_pid = None
        self.game_process = None
        self.game_reader = None
        self.game_writer = None
        self.return_code_task = None

    async def setup(self):
        """Set the portal up."""
        pass

    async def start_watch_return_code(self):
        """Start the task to watch the return code."""
        self.return_code_task = asyncio.create_task(self.watch_return_code())

    async def cleanup(self):
        """Clean the service up before shutting down."""
        await self.cleanup_watch_return_code()

    async def cleanup_watch_return_code(self):
        """Stop watching the process' return code."""
        if self.return_code_task:
            self.return_code_task.cancel()

    async def error_read(self, writer):
        """Can't read from the connection."""
        if self.game_writer is writer:
            self.game_id = None
            self.game_reader = None
            self.game_writer = None
            self.logger.debug("The connection to the game is lost.")
            crux = self.services["crux"]
            for writer in list(crux.readers.values()):
                await crux.send_cmd(writer, "game_stopped")

    error_write = error_read

    async def check_eof(self, reader):
        """Check if EOF has been sent."""
        if reader.at_eof():
            if reader is self.game_reader:
                await self.error_read(self.game_writer)

    async def watch_return_code(self):
        """Asynchronously watch for the game process' return code."""
        try:
            while True:
                await asyncio.sleep(0.2)
                if self.game_process:
                    return_code = self.game_process.poll()
                    if return_code is None:
                        continue
                    elif return_code != 0:
                        error = self.game_process.communicate()[1]
                        error = error.decode("utf-8", errors="replace")
                        error = error.replace("\r\n", "\n")
                        error = error.replace("\r", "\n").rstrip()
                        crux = self.services["crux"]
                        for writer in crux.readers.values():
                            await crux.send_cmd(
                                writer, "cannot_start_game", dict(error=error)
                            )
                        break
        except asyncio.CancelledError:
            pass

    def forward(cmd_name: str):
        """Forward the command and its reply.

        This is useful to perform a very common task: forwarding a command
        from a launcher to the game, and the game's response
        back to the same launcher.

        Args:
            cmd_name (str): the command name.

        """

        async def just_reply(self, origin: Origin, **kwargs):
            """Forward the request."""
            crux = self.services["crux"]
            result = await crux.wait_for_answer(
                self.game_writer, cmd_name, kwargs, timeout=4
            )
            await crux.answer(origin, result)

        name = f"handle_{cmd_name}"
        just_reply.__name__ = name
        just_reply.__qualname__ = name
        return just_reply

    async def handle_register_game(
        self, origin: Origin, pid: int, has_admin: bool = False
    ):
        """A new game process wants to be registered.

        Args:
            origin (Origin): origin of the request.
            pid (int): the game's Process ID.
            has_admin (bool, optional): whether an admin character exists.

        On receiving this command, the portal will try to create a
        unique identifier for the game, based on network information.
        It will then broadcast a `registered_game` to all, with this ID.

        """
        writer = origin.writer
        peer_name = writer.get_extra_info("peername")
        game_id = "UNKNOWN"
        if peer_name:
            peer_name = b":".join([str(name).encode() for name in peer_name])
            game_id = base64.b64encode(peer_name).decode()

        self.logger.debug(f"Receive register_game for ID={game_id}, PID={pid}")
        self.game_id = game_id
        self.game_pid = pid
        self.game_reader = origin.reader
        self.game_writer = writer
        await self.cleanup_watch_return_code()

        crux = self.services["crux"]
        cnx_id = crux.reader_ids.get(origin.reader)
        crux.type_cnx[cnx_id] = "G"
        sessions = []
        info = dict(
            game_id=game_id, sessions=sessions, pid=pid, has_admin=has_admin
        )
        await crux.broadcast("registered_game", info)

    async def handle_what_game_id(self, origin: Origin, name: str):
        """Return the game ID to the one querying for it."""
        crux = self.services["crux"]
        await crux.answer(origin, dict(game_id=self.game_id))
        cnx_id = crux.reader_ids.get(origin.reader)
        crux.type_cnx[cnx_id] = name[0].upper()

    async def handle_start_game(self, origin: Origin):
        """Handle the start_game command."""
        if self.game_pid and self.game_process:
            # The game is already running.
            self.logger.debug(
                f"The game process (PID={self.game_pid}) hasn't "
                "stopped yet.  Wait..."
            )

            # Note: this will block instead of running asynchronously.
            # Not ideal, but it's hard to tell how much time this will
            # take, as the game might have a lot of data to save on shutdown.
            self.game_process.communicate()
            self.game_pid = None
            self.game_process = None
            await self.cleanup_watch_return_code()

        self.game_process = self.process.start_process("game")
        await self.start_watch_return_code()

    async def handle_stop_game(self, origin: Origin):
        """Handle the stop_game command."""
        crux = self.services["crux"]
        if self.game_writer:
            self.logger.debug(
                f"Sending 'stop_game' to game ID {self.game_id}..."
            )
            await crux.send_cmd(
                self.game_writer, "stop_game", dict(game_id=self.game_id)
            )
        else:
            self.logger.warning(
                "Can't stop the game, it's already down it seems."
            )
            crux = self.services["crux"]
            for writer in crux.readers.values():
                await crux.send_cmd(writer, "game_stopped")
            return True

        async with async_timeout(5):
            while self.game_pid and Process.is_running(self.game_pid):
                await crux.wait_for_cmd(self.game_reader, "*", 0.5)
                if self.game_reader:
                    await self.check_eof(self.game_reader)

        if self.game_id:
            self.logger.warning(
                "The game process hasn't stopped, though it should have."
            )
            stopped = False
        else:
            self.logger.debug("The game process has stopped.")
            stopped = True

        return stopped

    async def handle_restart_game(
        self,
        origin: Origin,
        announce: bool = True,
    ):
        """Restart the game."""
        self.logger.debug("Asked to restart the game...")
        if announce and self.game_id:
            # Announce to all contected clients
            telnet = self.services["telnet"]
            for session_id in telnet.sessions.keys():
                await telnet.write_to(session_id, "Restarting the game ...")

        stopped = await self.handle_stop_game(origin.reader)
        if stopped:
            self.logger.debug("The game was stopped, now start it again.")
            await self.handle_start_game(origin.reader)

        # Wait for the game to register again.
        async with async_timeout(5):
            while True:
                if self.game_id:
                    break

                await asyncio.sleep(0.1)

        if not self.game_id:
            self.logger.warning("The game should have started by now.")
            return

        if announce and self.game_id:
            # Announce to all contected clients
            telnet = self.services["telnet"]
            for session_id in telnet.sessions.keys():
                await telnet.write_to(session_id, "... game restarted!")

    async def handle_stop_portal(self, origin: Origin):
        """Handle the stop_portal command."""
        await self.handle_stop_game(origin.reader)
        self.process.should_stop.set()

    async def handle_disconnect_session(
        self,
        origin: Origin,
        session_id: UUID,
    ):
        """Disconnect the given session from Telnet service.

        Args:
            session_id (UUID): the session ID to disconnect.

        If important, the reason should have been given beforehand.

        """
        telnet = self.services["telnet"]
        await telnet.disconnect_session(session_id)

    async def handle_sessions(self, origin: Origin, **kwargs):
        """Reply with the list of sessions."""
        crux = self.services["crux"]
        sessions = {}
        for session in sorted(
            tuple(self.services["telnet"].sessions.values()),
            key=lambda s: s.creation,
        ):
            sessions[session.uuid] = (
                session.ip_address,
                session.ago,
                session.secured,
            )

        await crux.answer(origin, dict(sessions=sessions))

    async def handle_net(self, origin: Origin, **kwargs):
        """Reply with the list of sessions."""
        crux = self.services["crux"]
        net_events = []
        for event in crux.net_events:
            event.type = crux.type_cnx.get(event.destination, "U")
            if args := event.args:
                if args := args.get("args"):
                    if "packets" in args:
                        event.args["args"] = dict(packets="...")

            net_events.append(event)

        await crux.answer(origin, dict(packets=net_events))

    async def handle_brutal_stop_game(self, origin: Origin):
        """Brutally terminate the game process if started."""
        crux = self.services["crux"]
        if self.game_pid:
            from psutil import Process

            game = Process(self.game_pid)
            args = dict(
                cmd_line=str(game.cmdline()), status=str(game.status())
            )
            game.terminate()
            stdout, stderr = self.game_process.communicate()
            args.update(dict(stdout=str(stdout), stderr=str(stderr)))
        else:
            args = dict(status="not started")
        await crux.answer(origin, args)

    async def handle_output(
        self,
        origin: Origin,
        session_id: UUID,
        output: bytes,
        input_id: int,
    ):
        """Handle output, send it to Telnet.

        Args:
            session_id (UUID): the session identifier.
            output (bytes): the output to send.
            input_id (int): the ID of the input that triggered this output.

        """
        telnet = self.services["telnet"]
        await telnet.write_to(session_id, output)

    async def handle_shell(self, origin: Origin, code: str):
        """Send the code to be processed by the game."""
        crux = self.services["crux"]
        result = await crux.wait_for_answer(
            self.game_writer, "shell", dict(code=code), timeout=None
        )
        await crux.answer(origin, result)

    async def handle_blueprints(self, origin: Origin):
        """Forward the request for blueprints."""
        crux = self.services["crux"]
        result = await crux.wait_for_answer(
            self.game_writer, "blueprints", timeout=4
        )
        await crux.answer(origin, result)

    handle_update_document = forward("update_document")
