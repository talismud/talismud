# Copyright (c) 2020-20201, LE GOFF Vincent
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

"""Launcher service."""

import argparse
import asyncio
from enum import Enum, Flag, auto
from pathlib import Path
import time
from uuid import UUID

from alembic.config import CommandLine as AlembicCommandLine
from async_timeout import timeout as async_timeout
from beautifultable import BeautifulTable

from service.base import BaseService
from service.origin import Origin


class MUDOp(Flag):

    """Cumulative MUD operations."""

    OFFLINE = 0
    PORTAL_ONLINE = auto()
    GAME_ONLINE = auto()
    STOPPING = auto()
    STARTING = auto()
    RELOADING = auto()
    NEED_ADMIN = auto()


class MUDStatus(Enum):

    """Mud status."""

    OFFLINE = 0
    PORTAL_ONLINE = 1
    ALL_ONLINE = 2
    GAME_ERROR = 3


class Service(BaseService):

    """Launcher main service."""

    name = "launcher"
    sub_services = ("host",)

    async def init(self):
        """Asynchronously initialize the service.

        This method should be overridden in subclasses.  It is called by
        `start`` before sub-services are created.  It plays the role of
        an asynchronous constructor for the service, and service attributes
        often are created there for consistency.

        """
        self.has_admin = True
        self.operations = MUDOp.OFFLINE
        self.status = MUDStatus.OFFLINE

    async def setup(self):
        """Set the game up."""
        self.services["host"].connect_on_startup = False

    async def cleanup(self):
        """Clean the service up before shutting down."""
        pass

    async def error_read(self):
        """Cannot read from CRUX anymore, prepare to shut down."""
        pass

    async def check_status(self):
        """Check the MUD status."""
        need_admin = MUDOp.NEED_ADMIN in self.operations
        host = self.services["host"]
        max_attempts = host.max_attempts
        timeout = host.timeout
        host.max_attempts = 2
        host.timeout = 0.2
        await host.connect_to_CRUX()

        if not host.connected:
            self.operations = MUDOp.OFFLINE
            self.status = MUDStatus.OFFLINE
            host.max_attempts = max_attempts
            host.timeout = timeout
            return

        # Otherwise, check that the game is also running.
        self.services["host"].read_secret_key()
        self.operations = MUDOp.PORTAL_ONLINE
        self.status = MUDStatus.PORTAL_ONLINE
        result = await host.wait_for_answer(
            host.writer, "what_game_id", dict(name="launcher")
        )

        if result is None:
            host.max_attempts = max_attempts
            host.timeout = timeout
            return False

        host.max_attempts = max_attempts
        host.timeout = timeout
        if result.get("game_id"):
            self.operations |= MUDOp.GAME_ONLINE
            if need_admin:
                self.operations |= MUDOp.NEED_ADMIN

            self.status = MUDStatus.ALL_ONLINE

    # Command handlers
    async def handle_registered_game(
        self,
        origin: Origin,
        game_id: str,
        sessions: list[UUID],
        **kwargs,
    ):
        """The game service has been registered by CRUX."""
        pass

    async def handle_game_id(self, origi9n: Origin, game_id: str):
        """A game ID has been sent by the portal, do nothing."""
        pass

    async def handle_game_stopped(self, origin: Origin):
        """The game service has been registered by CRUX."""
        pass

    async def handle_cannot_start_game(self, reader, error):
        """Cannot start the game."""
        self.logger.error(error)
        self.status = MUDStatus.GAME_ERROR

    # User actions
    async def action_start(self, args: argparse.ArgumentParser) -> bool:
        """Start the game.

        Return whether the game was correctly started.

        Order of operations:
            1.  Connect to CRUX.  It should not work, since the portal
                shouldn't be running.  If it works, however, skip to step 4.
            2.  Launch the `poral` process.  This should also create a
                CRUX server.
            3.  Attempt to connect to CRUX again.  This time it should work,
                possibly after some retries.  If it doesn't, the start
                process is broken, report and stop.
            4.  Start the `game` process.  The game will attempt to
                connect to the portal and send a command to it to register.
            5.  On receiving the 'register_game' command, the portal will
                check that no other game has been registered, assign an
                ID for clarity to it, send the 'registered_game' command
                with the new game ID to all hosts.  This includes the
                launcher at this point.
            6.  Wait for the `registered_game` command to be issued.  If it
                is, report success to the user.

        """
        # 1. Connect to CRUX.  Failure is expected.
        host = self.services["host"]
        host.max_attempts = 2
        host.timeout = 0.2
        await host.connect_to_CRUX()

        if not host.connected:
            # 2. 'host' is not connected.  Start the portal.
            self.operations = MUDOp.OFFLINE
            self.status = MUDStatus.OFFLINE
            self.logger.info("Starting the portal ...")
            self.process.start_process("portal")
            self.operations = MUDOp.STARTING

            # 3. Try to connect to CRUX again.
            # is time if it fails, it's an error.
            host.max_attempts = 20
            host.timeout = 1
            await host.connect_to_CRUX()

            if not host.connected:
                self.operations = MUDOp.OFFLINE
                self.status = MUDStatus.OFFLINE
                self.logger.error(
                    "The portal should have been started.  For some "
                    "reason, it hasn't.  Check the logs in "
                    "logs/portal.log for errors."
                )
                return False

            # The portal has started.
            host.read_secret_key(override=True)
            self.operations = MUDOp.STARTING | MUDOp.PORTAL_ONLINE
            self.operations |= MUDOp.PORTAL_ONLINE
            self.logger.info("... portal started.")
        else:
            host.read_secret_key()
            self.operations |= MUDOp.PORTAL_ONLINE
            self.status = MUDStatus.PORTAL_ONLINE
            self.logger.info("The portal is already running.")

            # Make sure the game needs to be started.
            result = await host.wait_for_answer(
                host.writer, "what_game_id", dict(name="launcher"), timeout=2
            )
            game_id = result.get("game_id")
            if game_id:
                self.logger.info(
                    "The game is also running, no need to start it."
                )
                return

        # 4. Start the game process.
        self.logger.info("Starting the game ...")
        await host.send_cmd(host.writer, "start_game")

        # 5. The game process will send a 'register_game' command to CRUX.
        # 6. ... so wait for the 'registered_game' command to be received.
        begin = time.time()
        while time.time() - begin < 10:
            success, result = await host.wait_for_cmd(
                host.reader, "registered_game", timeout=0.5
            )
            if self.status is MUDStatus.GAME_ERROR:
                return

            if success:
                break

        if success:
            self.operations = MUDOp.PORTAL_ONLINE | MUDOp.GAME_ONLINE
            self.status = MUDStatus.ALL_ONLINE
            game_id = result.get("game_id", "UNKNOWN")
            pid = result.get("pid", "UNKNOWN")
            self.has_admin = has_admin = result.get("has_admin", False)
            if not has_admin:
                self.operations |= MUDOp.NEED_ADMIN
            self.logger.info(
                f"... game started (id={game_id}, pid={pid}, "
                f"has_admin={has_admin})."
            )
            return True
        else:
            self.operations = MUDOp.PORTAL_ONLINE
            self.status = MUDStatus.PORTAL_ONLINE
            self.logger.error(
                "The game hasn't started.  See logs/game.log "
                "for more information."
            )
            return False

    async def action_stop(self, args: argparse.ArgumentParser):
        """Stop the game and portal process.

        Order of operations:
            1.  Connect to CRUX.  It should succeed.
            2.  Send the 'stop_portal' command to CRUX.
            3.  CRUX will send a 'stop_game' command to the game host.
            4.  Wait for CRUX to shut down.

        """
        # 1. Connect to CRUX.  Success is expected.
        host = self.services["host"]
        if not host.connected:
            host.max_attempts = 10
            host.timeout = 2
            await host.connect_to_CRUX()

            if not host.connected:
                self.operations = MUDOp.OFFLINE
                self.status = MUDStatus.OFFLINE
                self.logger.warning(
                    "The portal seems to be off, the game isn't running."
                )
                return

        # 2. Send the 'stop_portal' command.
        self.operations = (
            MUDOp.STOPPING | MUDOp.PORTAL_ONLINE | MUDOp.GAME_ONLINE
        )
        self.status = MUDStatus.ALL_ONLINE
        self.logger.info("Portal and game stopping ...")
        await host.send_cmd(host.writer, "stop_portal")

        # 4. Wait for any command to be received.  None should.
        async with async_timeout(20):
            while host.connected:
                await host.wait_for_cmd(host.reader, "*", timeout=0.2)
                await asyncio.sleep(0.5)

        if host.connected:
            self.operations = MUDOp.PORTAL_ONLINE | MUDOp.GAME_ONLINE
            self.status = MUDStatus.ALL_ONLINE
            self.logger.error(
                "The portal is still running, although asked to shudown."
            )
        else:
            self.operations = MUDOp.OFFLINE
            self.status = MUDStatus.OFFLINE
            self.logger.info("... portal and game stopped.")

    async def action_restart(self, args: argparse.ArgumentParser):
        """Restart the game, maintains the portal.

        Order of operations:
            1.  Connect to CRUX.  It should succeed.
            2.  Send the 'restart_game' command to CRUX.
            3.  CRUX will send a 'restart_game' command to the game host.
            4.  Listen for the `stopped_game` command, that will
                be sent when the game has disconnected.
            5.  The portal will start the `game` process.  The game will
                attempt to connect to the portal and send a command to it
                to register.
            6.  On receiving the 'register_game' command, the portal will
                check that no other game has been registered, assign an
                ID for clarity to it, send the 'registered_game' command
                with the new game ID to all hosts.  This includes the
                launcher at this point.
            7.  Wait for the `registered_game` command to be issued.  If it
                is, report success to the user.

        """
        # 1. Connect to CRUX.  Success is expected.
        host = self.services["host"]
        host.max_attempts = 10
        host.timeout = 2
        await host.connect_to_CRUX()

        if not host.connected:
            self.operations = MUDOp.OFFLINE
            self.status = MUDStatus.OFFLINE
            self.logger.warning(
                "The portal seems to be off, the game isn't running."
            )
            return

        # 2. Send the 'restart_game' command.
        self.logger.info("Game stopping ...")
        self.operations = (
            MUDOp.RELOADING | MUDOp.PORTAL_ONLINE | MUDOp.GAME_ONLINE
        )
        self.status = MUDStatus.ALL_ONLINE
        await host.send_cmd(host.writer, "restart_game", dict(announce=True))

        # 3. The portal should stop the game process...
        # ... and restart it.
        # 4. Listen for the 'stopped_game' command.
        success, _ = await host.wait_for_cmd(
            host.reader, "game_stopped", timeout=10
        )
        if not success:
            self.operations = MUDOp.PORTAL_ONLINE | MUDOp.GAME_ONLINE
            self.status = MUDStatus.ALL_ONLINE
            self.logger.warning("The game is still running.")
            return

        self.operations = MUDOp.RELOADING | MUDOp.PORTAL_ONLINE
        self.status = MUDStatus.PORTAL_ONLINE
        self.logger.info("... game stopped.")
        self.logger.info("Start game ...")
        # 6. The game process will send a 'register_game' command to CRUX.
        # 7. ... so wait for the 'registered_game' command to be received.
        begin = time.time()
        while time.time() - begin < 10:
            success, result = await host.wait_for_cmd(
                host.reader, "registered_game", timeout=0.5
            )
            if self.status is MUDStatus.GAME_ERROR:
                return

            if success:
                break

        if success:
            self.operations = MUDOp.PORTAL_ONLINE | MUDOp.GAME_ONLINE
            self.status = MUDStatus.ALL_ONLINE
            game_id = result.get("game_id", "UNKNOWN")
            self.logger.info(f"... game started (id={game_id}).")
        else:
            self.operations = MUDOp.PORTAL_ONLINE
            self.status = MUDStatus.PORTAL_ONLINE
            self.logger.error(
                "The game hasn't started.  See logs/game.log "
                "for more information."
            )

    async def action_status(self, args: argparse.ArgumentParser):
        """Print the portal and game status."""
        await self.check_status()
        if self.status is MUDStatus.OFFLINE:
            self.logger.info(
                "The MUD isn't running, neither portal nor game have started."
            )
        elif self.status is MUDStatus.PORTAL_ONLINE:
            self.logger.info(
                "The portal is running, but the game isn't running yet."
            )
        elif self.status is MUDStatus.ALL_ONLINE:
            self.logger.info("Portal and game are both running.")

    async def action_sessions(self, args: argparse.ArgumentParser):
        """Display the list of sessions."""
        host = self.services["host"]
        await self.check_status()
        if not host.connected:
            print("The portal doesn't seem to be connected at the moment.")
            return

        result = await host.wait_for_answer(host.writer, "sessions")
        sessions = result.get("sessions", {})

        if len(sessions) == 0:
            print("No session is currently connected to the Telnet portal.")
            return

        # Display sessions in an ASCII table.
        table = BeautifulTable()
        table.columns.header = ("Session ID", "IP", "Connection", "Secured")
        table.columns.header.alignment = BeautifulTable.ALIGN_LEFT
        table.columns.alignment["Session ID"] = BeautifulTable.ALIGN_LEFT
        table.columns.alignment["IP"] = BeautifulTable.ALIGN_LEFT
        table.columns.alignment["Connection"] = BeautifulTable.ALIGN_RIGHT
        table.columns.alignment["Secured"] = BeautifulTable.ALIGN_LEFT
        table.set_style(BeautifulTable.STYLE_NONE)

        for session_id, (ip, creation, secured) in sessions.items():
            secured = "Yes" if secured else "No"
            table.rows.append((session_id.hex, ip, creation, secured))
        print(table)

    async def action_net(self, args: argparse.ArgumentParser):
        """Display the list of network packets."""
        host = self.services["host"]
        await self.check_status()
        if not host.connected:
            print("The portal doesn't seem to be connected at the moment.")
            return

        result = await host.wait_for_answer(host.writer, "net")
        packets = result.get("packets", {})

        if len(packets) == 0:
            print("No packet was received... that's most odd.")
            return

        # Display packets in an ASCII table.
        table = BeautifulTable()
        table.columns.header = ("Destination", "Name", "Msg")
        table.columns.header.alignment = BeautifulTable.ALIGN_LEFT
        table.columns.alignment["Destination"] = BeautifulTable.ALIGN_RIGHT
        table.columns.alignment["Name"] = BeautifulTable.ALIGN_LEFT
        table.columns.alignment["Msg"] = BeautifulTable.ALIGN_LEFT
        table.set_style(BeautifulTable.STYLE_NONE)

        for packet in packets:
            destination = f"{packet.destination}({packet.type})"
            msg = packet.hint
            if packet.args:
                msg = str(packet.args)

            table.rows.append((destination, packet.name, msg))
        print(table)

    async def action_force_kill(self, args: argparse.ArgumentParser):
        """Force the game to abrupty stop."""
        host = self.services["host"]
        await self.check_status()
        if not host.connected:
            print("The portal doesn't seem to be connected at the moment.")
            return

        result = await host.wait_for_answer(host.writer, "brutal_stop_game")
        print(result)

    async def action_shell(self, args: argparse.ArgumentParser):
        """Open a Python-like shell and send command to the portal.

        These commands are then sent to the game where they
        are interpreted.

        """
        host = self.services["host"]
        await self.check_status()
        init_started = self.status == MUDStatus.ALL_ONLINE
        if not init_started:
            await self.action_start(args)

        # In a loop, ask user input and send the Python command
        # to the portal, which will forward it to the game, which
        # will evaluate and answer in the same way.
        prompt = ">>> "
        while True:
            try:
                code = input(prompt)
            except KeyboardInterrupt:
                print()
                break

            result = await host.wait_for_answer(
                host.writer, "shell", dict(code=code), timeout=None
            )
            if result:
                prompt = result.get("prompt", "??? ")
                display = result.get("display", "")
                if display:
                    print(display.rstrip("\n"))

        # If the game wasn't started before executing code, stop it.
        if not init_started:
            await self.action_stop(args)

    async def action_migrate(self, args: argparse.ArgumentParser):
        """Migrate the database."""
        db_path = Path("talismud.db")
        if db_path.exists():
            # Migrate the database.
            AlembicCommandLine("alembic").main(["upgrade", "head"])
        else:
            # Create the database file.
            AlembicCommandLine("alembic").main(["stamp", "head"])

    async def action_migration(self, args: argparse.ArgumentParser):
        """Create a migration file."""
        message = args.message
        message = message.replace(" ", "_")
        AlembicCommandLine("alembic").main(
            ["revision", "--autogenerate", "-m", message]
        )
