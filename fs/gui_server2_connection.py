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
