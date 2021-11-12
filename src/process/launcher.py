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

"""The launcher process, should send commands portal and game.

Internally, the launcher process is a very short-lived process most of
the times: it connects to the CRUX server (hosted on the portal process)
and run one command (usually just one) before shutting down.  The launcher
process is the one behind the `talismud` command, handling specific
actions.  Hence, when running `talismud start`, or `talismud stop`,
the launcher process is executed.

"""

import argparse

from process.base import Process

parser = argparse.ArgumentParser()
parser.set_defaults(action="help")
subparsers = parser.add_subparsers()
sub_start = subparsers.add_parser(
    "start", help="start the game and portal processes"
)
sub_start.set_defaults(action="start")
sub_stop = subparsers.add_parser(
    "stop", help="stop the game and portal processes"
)
sub_stop.set_defaults(action="stop")
sub_restart = subparsers.add_parser("restart", help="restart the game process")
sub_restart.set_defaults(action="restart")


class Launcher(Process):

    """Launcher process, running the launcher service.

    The launcher process should only have a connection to the CRUX server.
    This host service can be expected to be unavailable altogether.

    """

    name = "launcher"
    services = ("launcher",)

    def __init__(self):
        super().__init__()
        self.stream_handler.format_string = "{record.message}"
        self.window_task = None

    async def setup(self):
        """Called when services have all been started."""
        args = parser.parse_args()

        launcher = self.services["launcher"]
        if args.action == "start":
            await launcher.action_start()
        elif args.action == "stop":
            await launcher.action_stop()
        elif args.action == "restart":
            await launcher.action_restart()
        else:
            parser.print_help()

        self.should_stop.set()

    async def cleanup(self):
        """Called when the process is about to be stopped."""
        if self.window_task:
            self.window_task.cancel()