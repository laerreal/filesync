from six.moves.tkinter import (
    Toplevel,
    Button,
    Label,
    Frame,
    RIGHT,
    Y,
    Entry,
    StringVar,
)


class Dialog(Toplevel):

    def __init__(self, master, title, *a, **kw):
        Toplevel.__init__(self, master, *a, **kw)

        self.title(title)

        self.transient(self.master.winfo_toplevel())

        self._result = None
        self._alive = True

        self.bind("<Destroy>", self._on_destroy, "+")
        self.bind("<Escape>", self._on_escape, "+")

        # window needs to be visible for the grab
        # See: https://stackoverflow.com/questions/40861638/python-tkinter-treeview-not-allowing-modal-window-with-direct-binding-like-on-ri
        self.wait_visibility()
        self.grab_set()

    def _on_escape(self, __):
        self.destroy()

    def _on_destroy(self, e):
        if e.widget is self:
            self._alive = False

    def wait(self):
        "Grabs control until the dialog destroyed. Returns a value."

        while self._alive:
            self.update()
            self.update_idletasks()

        return self._result


class MB_NO_ENTRY: pass
class MB_ENTRY_TEXT: pass
class EM_ENTRY_PASSWORD: pass


class MessageBox(Dialog):

    def __init__(self, master, title, message, entry_type = MB_NO_ENTRY):
        self.entry_type = entry_type

        Dialog.__init__(self, master, title = title)

        self.columnconfigure(0, weight = 1)

        row = 0; self.rowconfigure(row, weight = 0)
        Label(self, text = str(message)).grid(
            row = row,
            column = 0,
            sticky = "NEW",
        )

        if entry_type is not MB_NO_ENTRY:
            row += 1; self.rowconfigure(row, weight = 1)

            self._var = var = StringVar(self)

            opts = dict(
                textvariable = var,
            )
            if entry_type is EM_ENTRY_PASSWORD:
                opts["show"] = "*"

            e = Entry(self, **opts)
            e.grid(
                row = row,
                column = 0,
                sticky = "NEW",
            )
            e.focus()

        self.bind("<Return>", self._on_return, "+")

        row += 1; self.rowconfigure(row, weight = 0)
        f_buttons = Frame(self)
        f_buttons.grid(row = row, column = 0, sticky = "ES")

        Button(f_buttons, text = "Ok", command = self._on_ok).pack(
            side = RIGHT,
            fill = Y
        )

    def _on_return(self, __):
        self._on_ok()

    def _on_ok(self):
        if self.entry_type is not MB_NO_ENTRY:
            self._result = self._var.get()
        self.destroy()


class DialogContext(object):

    def __init__(self, master, title):
        self.master = master
        self.title = title

    def getpass(self, prompt):
        return MessageBox(self.master, self.title,
            message = prompt,
            entry_type = EM_ENTRY_PASSWORD
        ).wait()

    def notify(self, message):
        return MessageBox(self.master, self.title,
            message = message,
            entry_type = MB_NO_ENTRY
        ).wait()

