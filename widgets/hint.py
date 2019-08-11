__all__ = [
    "Hint"
]

from six.moves.tkinter import (
    Toplevel
)

HINT_HIDE_DELAY = 200 # ms

class Hint(Toplevel):

    def __init__(self, *a, **kw):
        self.x, self.y = kw.pop("x", 0), kw.pop("y", 0)

        Toplevel.__init__(self, *a, **kw)
        self.overrideredirect(True)

        self._hiding = None
        self.bind("<Enter>", self._on_enter, "+")
        self.bind("<Leave>", self._on_leave, "+")

        # After all layout management is done...
        self.after(10, self._update_position)

    def _update_position(self):
        self.geometry("%dx%d+%d+%d" % (
            self.winfo_width(), self.winfo_height(),
            self.x, self.y
        ))

    def _on_leave(self, _):
        self._hide_cancel()
        self._hiding = self.after(HINT_HIDE_DELAY, self._hide)

    def _on_enter(self, _):
        self._hide_cancel()

    def _hide_cancel(self):
        if self._hiding is not None:
            self.after_cancel(self._hiding)
            self._hiding = None

    def _hide(self):
        self.destroy()
