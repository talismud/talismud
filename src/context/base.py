# Copyright (c) 2022, LE GOFF Vincent
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

"""Base class of all contexts.

A context is a "step" in the session process.  A context displays some
information and handles user input.  A simple context, the
message-of-the-day, is created whenever a session is createed.  This
context will greet the new session and display instructions to login.
From there, depending on user input, the session will move
to a different context (say, the creation of the username, for instance,
or the password).

In short, a context represents the "step" of a connected session.
It handles user input (text entered by the user connected to this session).
When "logged in" to the game, a character can be connected to
one or more contexts.  By default, a logged-in user is connected to
a single context: the one that interprets commands.

"""

import inspect
from textwrap import dedent
import traceback
from typing import Any, Optional, TYPE_CHECKING

from context.log import logger
from data.decorators import lazy_property
from tools.delay import Delay

if TYPE_CHECKING:
    from data.character import Character
    from data.session import Session

CONTEXTS = {}


class Context:

    """Class defining a context.

    Class attributes:
        text: a text that doesn't require further processing.  In case
              you want the text to change depending on session information,
              override the `greet` method instead.  Don't hesitate
              to use multiline strings, they will be dedent-ed
              (see `textwrap.dedent`).
        prompt: the prompt as a string.  A prompt is sent
                below the text of the context, or any call to
                `msg`.  The method `get_prompt`, if overridden,
                can handle additional operation and return
                a different prompt based on
                the session's information.

    Instance attributes:
        session (Session): the session object.  You can use
                          `session.options` to access the session's
                          option handler which can be handy to store
                          information on the session itself.
                          This information will be available as long
                          as the session exists (that is, even if the
                          game stops and starts again, as long as the
                           session is maintained by the user).

    Methods:
        greet()            greet the user with some text.  The text
                           to be displayed should be returned (return
                           `None` to not send any text at all).
        enter()            The session first enters this context.  By
                           default, this method just calls `greet` and
                           sends its returned text to the session.  This
                           method is not called if the session already
                           is on this context without moving to another.
                           That's why you should always have a `text`
                           class variable or `greet` method that does return
                           some text, overriding `enter` isn't that
                           frequent, except to perform memory
                           operations on the session for instance.
        leave()            Called when the session is about to leave
                           this context to go to another.  By default,
                           this method does nothing.
        move(new_context)  Move the session to a new context.  The
                           current context's `leave` method will be called,
                           then the new context will be created with
                           the same session and its `greet` method will
                           be called.  You shouldn't override this method,
                           just use it.
        msg(text)          Send some text to the session.  This is just
                           a shortcut for `self.session.msg(text)`.
        refresh()          Called when the user asks for a refresh.  By
                           default, calls `greet` and send the result to
                           the session.  This method will also be called
                           by `enter` if not overridden.

    Contexts have a simple in-built command system.  Contexts can
    define methods that will be called when a user enters text that
    matches the method name.  For instance, if you want to react
    when the user enters "help", define a method called
    `input_help` in your context.  This method will be called
    ONLY if the user enters "help" or possibly "help something".
    In the second case, the argument ("something") will be passed
    to the `input_help` method.  So your `input_help` can be
    defined in two ways:

        def input_help(self):

    OR

        def input_help(self, args: str):

    Arguments will be passed to the method only if it asks for them
    (has a positional argument after `self`).  If the context can't
    find an `input_...` method matching user input, it will then
    call `other_input` and send the entire user input as argument.

    Don't override `handle_input`, just create `input_...` and
    `other_input` methods on the context.

    """

    pyname = None
    prompt = ""
    text = ""
    inputs = {
        "": "press_return",
    }
    hide_input = False

    def __init__(
        self,
        session: Optional["Session"] = None,
        character: Optional["Character"] = None,
        options: dict[str, Any] = None,
    ):
        if session is None and character is None:
            raise ValueError(
                "a context must have either a session or a character"
            )
        elif session is not None and character is not None:
            raise ValueError(
                "a context cannot have both session and character"
            )

        self._session = session
        self._character = character
        self.options = options if isinstance(options, dict) else {}

    def __repr__(self):
        name = self.pyname
        if session := self._session:
            name += f"({session!r})"
        elif character := self._character:
            name += f"({character!r})"
        else:
            name += "(?)"

        return name

    @lazy_property
    def character(self):
        """Return the character or the session's character."""
        if (character := self._character) is None:
            character = self._session and self._session.character or None

        return character

    @lazy_property
    def session(self):
        """Return the session or the character's session."""
        if (session := self._session) is None:
            session = self._character and self._character.session or None

        return session

    @session.setter
    def session(self, session: Optional["Session"]) -> None:
        """Update the context's session."""
        if self._session is not None:
            self._session = session
        elif self._character is not None:
            self._character.session = session

    def greet(self) -> Optional[str]:
        """Greet the session or character.

        This method is called when the session first connects to this
        context or when it calls for a "refresh".  If the context
        is simple, you don't need to override this method, just specify
        the `text` class variable.  If, however, you want to change
        the text based on session information, you can override
        this method.  Be sure to return the text to be sent to the
        session.  If you return `None`, no text will be sent, which
        might be confusing to the user.

        """
        return self.text

    def refresh(self):
        """Refresh the context view."""
        text = self.greet()
        if text is not None:
            if isinstance(text, str):
                text = dedent(text.strip("\n"))
            self.msg(text)

    def enter(self):
        """The session or character first enters in this context.

        You can ovverride this method to do something when the session
        or character enters the context for the first time.

        """
        self.refresh()

    def leave(self):
        """The session or character is about to leave this context.

        Override this method to perform some operations on the session
        or character when it leaves the context.

        """
        pass

    def press_return(self):
        """Return is pressed without any input."""
        self.refresh()

    def get_prompt(self):
        """Return the prompt to be displayed for this context."""
        return self.prompt

    def other_input(self, command: str):
        """What to do when no user input matches in this context.

        Args:
            command (str): the full user input.

        """
        self.msg("What to do?")

    def handle_input(self, user_input: str):
        """What to do when the user enters text in the context?

        Contexts have a simple in-built command system.  Contexts can
        define methods that will be called when a user enters text that
        matches the method name.  For instance, if you want to react
        when the user enters "help", define a method called
        `input_help` in your context.  This method will be called
        ONLY if the user enters "help" or possibly "help something".
        In the second case, the argument ("something") will be passed
        to the `input_help` method.  So your `input_help` can be
        defined in two ways:

            def input_help(self):

        OR

            def input_help(self, args: str):

        Arguments will be passed to the method only if it asks for them
        (has a positional argument after `self`).  If the context can't
        find an `input_...` method matching user input, it will then
        call `other_input` and send the entire user input as argument.

        Don't override `handle_input`, just create `input_...` and
        `other_input` methods on the context, except if you have
        a specific need to intercept all inputs.

        Args:
            user_input (str): the user input.

        """
        if " " in user_input:
            command, args = user_input.split(" ", 1)
        else:
            command, args = user_input, ""

        # Look for an input methods.
        method = None
        if user_input:
            method_name = type(self).inputs.get(command or user_input)
            if method_name:
                method = getattr(self, method_name, None)
        else:
            method = self.press_return

        if method is None:
            # Try to find an input_{command} method
            method = getattr(self, f"input_{command.lower()}", None)

        if method:
            # Pass the command argument if the method signature asks for it.
            signature = inspect.signature(method)
            if len(signature.parameters) == 0:
                method_args = ()
            else:
                method_args = (args,)
        else:
            method = self.other_input
            method_args = (user_input,)

        try:
            res = method(*method_args)
        except Exception:
            self.msg(traceback.format_exc())
            logger.exception("An error occurred while running the context:")
            raise

        return res

    def msg(self, text: str | bytes, prompt: bool = True):
        """Send some text to the context session.

        Args:
            text (str or bytes): text to send.
            prompt (bool, optional): display the prompt.  Set this to
                    `False` to not display a prompt below the message.
                    Note that messages are grouped, therefore, if one
                    of them deactive the prompt, it will be deactivated
                    for all the group.

        """
        self.session.msg(text, prompt=prompt)

    def move(self, context_path: str):
        """Move to a new context.

        You have to specify the new context as a Python path, like
        "connection.motd".  This path is a shortcut to the
        "context.connection.motd" module (unless it has been replaced
        by a plugin).

        Args:
            context_path (str): path to the module where the new context is.

        Note:
            Character contexts cannot be moved with this method.
            Explicitly use the sub-context methods `add` or `replace`.

        """
        NewContext = CONTEXTS[context_path]
        new_context = NewContext(self._session, self._character)
        self.leave()
        self.session.context = new_context
        new_context.enter()

    def call_in(self, *args, **kwargs):
        """Schedule a callback to run in X seconds.

        Args:
            delay (int or float or timedelta): the delay (in seconds).
            callback (Callable): the callback (usually an instance method).

        Additional positional or keyword arguments will be sent to the
        callback when it's time to execute it.

        """
        return Delay.schedule(*args, **kwargs)
