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

"""Telnet server."""

import asyncio
from io import BytesIO
from ssl import create_default_context, Purpose
from typing import Union
from uuid import UUID, uuid4

from service.base import BaseService
from service.cmd import CmdMixin
from service.ssl_cert import save_cert


class Service(CmdMixin, BaseService):

    """Telnet server to await for TCP connections from users.

    This should be run from the portal service.  Commands (user input)
    are sent to CRUX (running on the game process) and answers are sent
    from the game process by CRUX to the portal process, and then
    to a Telnet connection.

    By default, this service will create two servers: a SSL-free
    Telnet server (listening on port 4000 by default) and a SSL-encrypted
    Telnet server (listening on port 4001).  Both are handled in
    the same way, since the implementation remains similar in both cases.

    """

    name = "telnet"

    async def init(self):
        """Asynchronously initialize the service."""
        self.serving_task = None
        self.serving_ssl_task = None
        self.sessions = {}
        self.readers = {}
        self.buffers = {}
        self.current_id = 1
        self.CRUX = None

    async def setup(self):
        """Set the Telnet servers up."""
        self.CRUX = self.parent.services["crux"]
        self.serving_task = asyncio.create_task(self.start_serving())
        self.serving_ssl_task = asyncio.create_task(
            self.start_serving(ssl=True)
        )

        # Create the SSL cert and private key
        self.logger.debug(
            f"{' ' * 12} telnet-ssl: creating the SSL certificate..."
        )
        save_cert(
            ".ssl/telnet",
            "localhost",
            country="FR",
            state="None",
            locality="Paris",
            organization="TalisMUD",
        )
        self.logger.debug(f"{' ' * 12} ... certificate created.")

    async def cleanup(self):
        """Clean the service up before shutting down."""
        if self.serving_task:
            self.serving_task.cancel()
        if self.serving_ssl_task:
            self.serving_ssl_task.cancel()

    async def start_serving(self, ssl: bool = False):
        """Start serving on a TCP port.

        Args:
            ssl (bool): if True, specify a SSL context.

        """
        try:
            await self.create_server(ssl=ssl)
        except asyncio.CancelledError:
            pass
        except Exception:
            self.logger.exception(
                "telnet: an error occurred when trying to serve"
            )

    async def create_server(self, ssl: bool = False):
        """Create the Telnet server for SSL or not.

        Args:
            ssl (bool): if True, specify a SSL context.

        """
        interface = "0.0.0.0"
        port = 4001 if ssl else 4000
        self.logger.info(
            f"telnet{' SSL' if ssl else ''}: preparing to listen on "
            f"{interface}, port {port}"
        )

        if ssl:
            ssl_ctx = create_default_context(Purpose.CLIENT_AUTH)
            ssl_ctx.load_cert_chain(".ssl/telnet.cert", ".ssl/telnet.key")
        else:
            ssl_ctx = None

        try:
            server = await asyncio.start_server(
                self.new_ssl_connection if ssl else self.new_connection,
                interface,
                port,
                ssl=ssl_ctx,
            )
        except asyncio.CancelledError:
            pass
        except ConnectionError:
            self.logger.exception(
                "telnet: can't connect to {interface}:{port}"
            )
            return

        addr = server.sockets[0].getsockname()
        self.logger.info(f"telnet: Serving on {addr}")

        async with server:
            try:
                await server.serve_forever()
            except asyncio.CancelledError:
                pass
            except Exception:
                self.logger.exception(
                    "telnet: An exception was raised when serving:"
                )

    async def new_connection(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ):
        """Handle a new connection."""
        try:
            await self.begin_reading_from(reader, writer, ssl=False)
        except asyncio.CancelledError:
            return
        except Exception:
            self.logger.exception(
                "telnet: an error occurred when reading a stream:"
            )

    async def new_ssl_connection(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ):
        """Handle a new secure connection."""
        try:
            await self.begin_reading_from(reader, writer, ssl=True)
        except asyncio.CancelledError:
            return
        except Exception:
            self.logger.exception(
                "telnet: an error occurred when reading a stream:"
            )

    async def begin_reading_from(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
        ssl: bool,
    ):
        """Begin to read from a given connection."""
        addr = writer.get_extra_info("peername")
        session_id = uuid4()
        await self.new_session(session_id, reader, writer)
        self.logger.info(
            f"telnet{'(ssl)' if ssl else ''}: connection "
            f"from {addr}: new session {session_id}"
        )

        try:
            await self.read_input(reader)
        except asyncio.CancelledError:
            pass

    async def read_input(self, reader: asyncio.StreamReader):
        """Enter an asynchronous loop to read input from `reader`."""
        session_id, _ = self.readers.get(reader, (None, None))
        if session_id is None:
            self.logger.warning(
                "Trying to listen on a client with no session ID."
            )
            return

        # Create the buffer for the reader if it doesn't exist:
        buffer = self.buffers.get(reader)
        if buffer is None:
            buffer = BytesIO()
            self.buffers[reader] = buffer

        while True:
            try:
                data = await reader.read(1024)
            except ConnectionError:
                await self.error_read(reader)
                return
            except asyncio.CancelledError:
                return
            except Exception:
                self.logger.exception(
                    "An exception was raised when reading a session"
                )
                await self.error_read(reader)
                return

            if not data:
                # The socket has been disconnected.
                await self.error_read(reader)
                return

            buffer.write(data)

            # Process full lines, placing incomplete lines in the buffer.
            buffer.seek(0)
            unprocessed = b""
            while line := buffer.readline():
                # Windows \r\n are replaced with \n
                line = line.replace(b"\r\n", b"\n")
                # MAC \r are replaced by \n
                line = line.replace(b"\r", b"\n")

                # Now all should be Unix-like simple \n
                if b"\n" in line:
                    for piece in line.splitlines():
                        # It is possible, though unlikely, that this loop
                        # will be called more than once.
                        await self.send_input(session_id, piece)
                else:
                    unprocessed = line

            # Empty the buffer, add only the unprocessed bytes.
            buffer.seek(0)
            buffer.truncate()
            buffer.write(unprocessed)

    async def error_read(self, reader: asyncio.StreamReader):
        """An error occurred when reading from reader."""
        session_id, writer = self.readers.pop(reader, (0, None))
        if writer is None:
            self.logger.error(
                "telnet: connection was lost with a client, but "
                "the associated writer cannot be found."
            )
        else:
            self.logger.info(
                f"telnet: the connection to a client {session_id} was closed."
            )

            try:
                del self.sessions[session_id]
            except KeyError:
                pass
            finally:
                writer = self.parent.game_writer
                if writer:
                    await self.CRUX.send_cmd(
                        writer,
                        "disconnect_session",
                        dict(session_id=session_id),
                    )

    async def new_session(
        self,
        session_id: UUID,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
    ):
        """Process a new session.

        Args:
            session_id (UUID): the session identifier.
            reader (StreamReader): the session reader.
            writer (StreamWriter): the session writer.

        """
        self.sessions[session_id] = (reader, writer)
        self.readers[reader] = (session_id, writer)
        self.logger.debug(f"telnet: new connection, session ID {session_id}")
        writer = self.parent.game_writer
        if writer:
            await self.CRUX.send_cmd(
                writer, "new_session", dict(session_id=session_id)
            )

    async def disconnect_session(self, session_id: UUID):
        """Disconnect the given session.

        Args:
            session_id (UUID): the session to disconnect.

        """
        reader, writer = self.sessions.pop(session_id, (None, None))
        if writer:
            self.logger.debug(f"Diconnection session ID {session_id}.")
            writer.close()
            await writer.wait_closed()

    async def send_input(self, session_id: UUID, command: bytes):
        """Called when an input line was sent by the client."""
        writer = self.parent.game_writer
        if writer:
            await self.CRUX.send_cmd(
                writer, "input", dict(session_id=session_id, command=command)
            )

    async def write_to(self, session_id: UUID, message: Union[str, bytes]):
        """Send a message to this session.

        Args:
            session_id (UUID): the session ID.
            message (str or bytes): the message to send.  If a
                    str, encode it using the default encoding
                    in the settings.

        Should this method fail, the session will be disconnected.

        """
        if isinstance(message, str):
            message = message.replace("\r\n", "\n").replace("\r", "\n")
            message = message.encode("utf-8", errors="replace")
        else:
            message = message.replace(b"\r\n", b"\n").replace(b"\r", b"\n")

        if not message.endswith(b"\n"):
            message += b"\n"

        message = message.replace(b"\n", b"\r\n")

        reader, writer = self.sessions.get(session_id, (None, None))
        if writer:
            try:
                writer.write(message)
                await writer.drain()
            except ConnectionError:
                await self.error_read(reader)
                return
