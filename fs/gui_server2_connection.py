from .session import (
    Session,
)
from .server2 import (
    HandlerError,
)
from .server2_connection import (
    Server2Connection,
)


class GUIServer2Connection(Server2Connection):

    def __init__(self, uri, gui, *a, **kw):
        self.gui = gui

        super(GUIServer2Connection, self).__init__(uri, *a, **kw)

        self.server_name = None

        self.issue("identify_self")

    def main(self, *a, **kw):
        self._notify_gui("started")
        try:
            super(GUIServer2Connection, self).main(*a, **kw)
        finally:
            self._notify_gui("stopped")

    def _notify_gui(self, event, *a, **kw):
        try:
            h = getattr(self.gui, "__conn_" + event + "__")
        except AttributeError:
            return
        h(self, *a, **kw)

    def _co_handler_identify_self(self):
        name = (yield)[0]
        self.server_name = name
        self._notify_gui("name", name)

    def authenticate(self, name, identity):
        self.identity = identity
        self.issue("auth1", name, identity.pub_key_data)

    def _co_handler_auth1(self, *__):
        challenge_message = yield

        if challenge_message[0] is HandlerError:
            # print(challenge_message[1])
            return

        challenge, server_pub_key_data = challenge_message[0]

        self.session = session = Session(self.identity, server_pub_key_data)

        challenge_solution = session.solve_challenge(challenge)

        self.issue("auth2", challenge_solution)

    def _co_handler_auth2(self, *__):
        if (yield):
            self._notify_gui("authorized")
        else:
            self._notify_gui("not_authorized")
