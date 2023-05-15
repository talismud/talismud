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

"""The abstract process class."""

from abc import ABCMeta, abstractmethod
import asyncio
from importlib import import_module
import os
import platform
from shlex import split
from subprocess import Popen, PIPE, run
import sys
from typing import Tuple

from psutil import pid_exists

from tools.logging.frequent import FrequentLogger


class Process(metaclass=ABCMeta):

    """Abstract class for a process.

    This class both contains code that will be called in the main process,
    and code to be called when the child process has been created.

    """

    name: str
    services: Tuple[str] = ()

    def __init__(self):
        self.started = False
        self.services = {}
        self.pid = os.getpid()
        self.logger = FrequentLogger(self.name)
        self.logger.setup()

    def __repr__(self):
        desc = f"<Process {self.name}, "
        if self.started:
            desc += f"running on PID={self.pid}"
        else:
            desc += "not running"
        desc += ">"
        return desc

    async def start(self, wait_event: bool = True):
        """Called when the process starts."""
        self.should_stop = asyncio.Event()
        self.logger.debug(f"Starting process (PID={self.pid}...")
        for name in type(self).services:
            module_name = f"service.{name}"
            module = import_module(module_name)
            cls = getattr(module, "Service")
            service = cls(process=self)
            self.services[name] = service
            await service.start()

        self.logger.debug("... process started.")
        self.started = True
        await self.setup()

        if wait_event:
            await self.should_stop.wait()

    async def stop(self):
        """Called when the process stop."""
        self.logger.debug("Stopping process...")
        for name, service in tuple(self.services.items()):
            await service.stop()
            del self.services[name]

        self.started = False
        await self.cleanup()
        self.logger.debug("... process stopped.")

    @abstractmethod
    async def setup(self):
        """Called when services have all been started."""
        pass

    @abstractmethod
    async def cleanup(self):
        """Called when the process is about to be stopped."""
        pass

    @staticmethod
    def is_running(pid: int) -> bool:
        """Is the given process running?

        Args:
            Process ID (int): the process identifier (PID).

        Returns:
            running (bool): whether the process is running or not.

        """
        return pid_exists(pid)

    def run_command(self, command: str) -> int:
        """Run the specified command, reutning its status.

        Args:
            command (str): the command to run.

        """
        if platform.system() != "Windows":
            command = split(command)

        self.logger.debug(f"Calling the {command!r} command")

        return run(command).returncode

    def start_process(self, process_name: str):
        """Start a task in a separate process.

        This simply is a helper to create processes.  This is most useful
        for the launcher and portal process.  The created process will
        execute in a separate process and synchronization will have to
        be done through the CRUX/host system.

        Args:
            process_name (str): the name of the process to start.

        The name should be the script or executable name without extension.
        If the Python script is frozen (`sys.frozen` set to True), then
        the command is called as is.  In other word, if the process
        name is "portal":

          1.  If not frozen, executes 'python portal.py'.
          2.  If frozen, executes 'portal'.

        """
        # Under Windows, specify a different creation flag
        creationflags = 0x08000000 if platform.system() == "Windows" else 0
        command = f"{sys.executable} {process_name}.py"
        frozen = getattr(sys, "frozen", False)
        if frozen:
            command = process_name
            command += ".exe" if platform.system() == "Windows" else ""

        stdout = stderr = PIPE
        if platform.system() == "Windows":
            if frozen:
                stdout = stderr = None
        elif platform.system() == "Linux":
            if frozen:
                command = "./" + command
            command = split(command)

        self.logger.debug(
            f"Starting the {process_name!r} process: {command!r}, "
            f"(frozen={frozen}, stdout={stdout}, stderr={stderr})"
        )
        process = Popen(
            command, stdout=stdout, stderr=stderr, creationflags=creationflags
        )

        return process

    def run(self):
        """Run the process in a synchronous loop."""
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        task = loop.create_task(self.start())
        try:
            loop.run_until_complete(task)
        except asyncio.CancelledError:
            pass
        except KeyboardInterrupt:
            self.should_stop.set()
        finally:
            loop.run_until_complete(self.stop())
