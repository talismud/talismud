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

"""Data service."""

from datetime import datetime
import pickle
from typing import Optional
from uuid import UUID

from dynaconf import settings

from data.base import handle_data
from data.log import logger
from data.session import Session
from service.base import BaseService
from service.shell import Shell


class Service(BaseService):

    """Data service, to connect a storage engine."""

    name = "data"

    async def init(self):
        """Asynchronously initialize the service.

        This method should be overridden in subclasses.  It is called by
        `start`` before sub-services are created.  It plays the role of
        an asynchronous constructor for the service, and service attributes
        often are created there for consistency.

        """
        self.engine = handle_data(logging=self.log_query)

    async def setup(self):
        """Set the portal up."""

    async def cleanup(self):
        """Clean the service up before shutting down."""
        self.engine.close()

    def setup_shell(self, shell: Shell):
        """Setup the shell,a dding variables."""
        # Add every data model as locals.
        for model in self.engine.models.values():
            shell.locals[model.__name__] = model

    async def new_session(
        self,
        session_id: UUID,
        creation: datetime,
        ip_address: str,
        secured: bool,
    ) -> Session:
        """Create a session in the storage engine.

        Args:
            session_id (UUID): the session's unique identifier.
            creation (datetime): when was the session created on the portal?
            ip_address (str): this session's IP address.
            secured (bool): is it a secure (SSL) connection?

        This method returns a new Session object.

        """
        session = Session.repository.create(
            uuid=session_id,
            creation=creation,
            ip_address=ip_address,
            secured=secured,
            encoding=settings.DEFAULT_ENCODING,
            context_path="connection.motd",
            context_options=pickle.dumps({}),
        )
        return session

    def get_session(self, session_id: UUID) -> Optional[Session]:
        """Return, if found, the stored session with this UUID."""
        return Session.repository.get(uuid=session_id)

    def delete_session(self, session_id: UUID) -> Optional[Session]:
        """Delete, if found, the stored session with this UUID."""
        if session := self.get_session(session_id):
            logger.debug(f"The session {session_id} is to be deleted.")
            session.logout()
            Session.repository.delete(session)
            return True

        return False

    def log_query(self, statement: str, args: tuple[str]):
        """Log the specified query."""
        statement = statement.replace("\t", " " * 4)
        statement = ("\n" + " " * 4).join(
            [line for line in statement.splitlines()]
        )
        if args:
            statement += f"\n{' ' * 4}{args}"
        logger.debug(f"\n{' ' * 4}{statement}")
