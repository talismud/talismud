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

"""Module containing the modified Session class."""

from sqlalchemy.orm import Session, SessionTransaction

from data.log import logger


class TalisMUDSession(Session):

    """TalisMUD-specific session."""

    talismud_engine = None

    def begin(self):
        """Begin a new session."""
        TalisMUDSessionTransaction.talismud_engine = self.talismud_engine
        transaction = TalisMUDSessionTransaction(self)
        self.talismud_engine.current_transaction = next(
            self.talismud_engine.transaction_counter
        )
        return transaction


class TalisMUDSessionTransaction(SessionTransaction):

    """A session transaction for TalisMUD."""

    talismud_engine = None

    def commit(self, *args, **kwargs):
        transaction = self.talismud_engine.current_transaction
        self.talismud_engine.log("COMMIT", (transaction,))
        super().commit(*args, **kwargs)

    def rollback(self, *args, **kwargs):
        transaction = self.talismud_engine.current_transaction
        self.talismud_engine.log("ROLLBACK", (transaction,))
        logger.group(transaction).log_group()
        self.talismud_engine.clear_cache()
        super().rollback(*args, **kwargs)
