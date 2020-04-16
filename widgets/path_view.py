from six.moves.tkinter import (
    Frame,
    Entry,
    Button,
    Label,
    StringVar,
    SUNKEN,
    END,
    FLAT,
)
from six.moves import (
    zip_longest as izip_longest,
)
from os.path import (
    sep
)


class PathView(Frame):

    def __init__(self, *a, **kw):
        full_path = kw.pop("full_path", tuple())
        path = kw.pop("full_path", tuple())
        editable = kw.pop("editable", False)

        Frame.__init__(self, *a, **kw)

        # properties
        self._full_path = tuple()
        self._path = tuple()
        self._editable = None

        # widgets
        self.rowconfigure(0, weight = 0)
        self._columns = 1
        # self.columnconfigure(0, weight = 0) # by editable.setter

        bt = self._button(0)
        self._buttons = [bt]

        pady = bt.cget("pady")

        self._label = Label(self,
            relief = SUNKEN,
            # Label replaces button when its path entry is selected.
            # Where we adjusts sizes.
            padx = bt.cget("padx"),
            pady = pady,
        )

        self._var = var = StringVar(self)
        self._entry = e = Entry(self,
            textvariable = var,
            borderwidth = pady,
            relief = FLAT,
        )

        self.winfo_toplevel().bind("<Control-Key>", self._top_control_key, "+")
        e.bind("<Control-Key>", self._entry_control_key, "+")
        e.bind("<Escape>", self._entry_escape, "+")
        e.bind("<Return>", self._entry_return, "+") # Enter

        # Entering to editable mode on mouse click on empty space
        self.bind("<Button-1>", self._button_1, "+")

        # initialize
        self.editable = editable
        self.full_path = full_path
        self.path = path

    @property
    def editable(self):
        return self._editable

    @editable.setter
    def editable(self, editable):
        editable = bool(editable)
        if self._editable is editable:
            return
        self._editable = editable

        bts = self._buttons
        if editable:
            for bt in bts:
                bt.grid_forget()
            self._label.grid_forget()

            self._entry.grid(
                row = 0,
                column = 0,
                columnspan = len(bts),
                sticky = "NESW",
            )
            self.columnconfigure(0, weight = 1)
        else:
            self.columnconfigure(0, weight = 0)
            self._entry.grid_forget()

            l = len(self._path) - 1
            for i, bt in enumerate(bts[:l]):
                bt.grid(row = 0, column = i, sticky = "NWS")
            self._label.grid(row = 0, column = l + 1, sticky = "NWS")

    @property
    def full_path(self):
        return self._full_path

    @full_path.setter
    def full_path(self, full_path):
        prev_full_path = self._full_path
        self._full_path = full_path

        show_buttons = not self._editable

        bts = self._buttons

        update_path = False
        changed = False

        for i, (bt, prev_name, name) in enumerate(izip_longest(
            list(bts), prev_full_path, full_path
        )):
            if bt is None:
                # full_path is longer than any previous full_path
                assert name is not None

                # prev_full_path is shotter than full_path
                assert prev_name is None

                bt = self._button(i)
                bt.config(text = name or "   ")
                bts.append(bt)
                self.columnconfigure(i, weight = 0)
                if show_buttons:
                    bt.grid(row = 0, column = i, sticky = "NWS")

                changed = True
            elif name is None:
                if prev_name is not None:
                    # prev_full_path is longer than full_path
                    update_path = True

                if show_buttons:
                    bt.grid_forget()
                # else: # already forgotten
            elif prev_name is None: # name is not None
                # prev_full_path is shotter than full_path
                changed = True

                bt.config(text = name or "   ")
                if show_buttons:
                    bt.grid(row = 0, column = i, sticky = "NWS")
            elif prev_name != name:
                bt.config(text = name or "   ")
                update_path = True

        self._columns = i + 1

        if update_path or changed:
            self.event_generate("<<FullPathChanged>>")

        if update_path:
            self.path = full_path

    @property
    def path(self):
        return self._path

    @path.setter
    def path(self, path):
        prev_path = self._path
        for i, (prev, name) in enumerate(izip_longest(prev_path, path)):
            if prev is None:
                # new path is longer but same as previous in common prefix
                assert name is not None

                for fp, name in izip_longest(self._full_path[i:], path[i:]):
                    if name is None:
                        break
                    elif fp is None or fp != name:
                        self.full_path = path
                        break

                i = len(path) - 1
                break
            elif name is None:
                # new path is shoter but same as previous in common prefix
                assert prev is not None
                i -= 1
                break
            elif prev != name:
                # Full_path setter will recursively call this function again.
                self._path = prev_path[:i]
                for bt in self._buttons[i:len(prev_path)]:
                    bt.grid_forget()

                self.full_path = path
                return
        else:
            # new path is identical
            return

        self._path = path

        self._var.set(sep.join(path))

        lb = self._label

        lb.config(text = path[-1] or "   ")

        self.event_generate("<<PathChanged>>")

        if self._editable:
            return
        # else: # show buttons

        lb.grid_forget()

        bts = self._buttons

        prev_i = len(prev_path) - 1
        if prev_i >= 0:
            bts[prev_i].grid(row = 0, column = prev_i, sticky = "NWS")

        if i >= 0:
            bts[i].grid_forget()
            lb.grid(row = 0, column = i, sticky = "NWS")

    def _button(self, i):
        bt = Button(self, command = lambda : self._on_bt(i))
        return bt

    def _on_bt(self, i):
        self.path = self.full_path[:i + 1]

    def _top_control_key(self, e):
        code = e.keycode

        if code == 46: # L
            ed = not self._editable
            self.editable = ed
            if ed:
                e = self._entry
                e.focus_set()
                e.icursor(END)
            return "break"
        #elif code == 28: # T, test
        #    path = self._path
        #    self.path = path[:-3] + (path[-3][:-1],)

    def _entry_control_key(self, e):
        code = e.keycode

        if code == 38: # A
            e = e.widget
            e.selection_range(0, END)
            e.icursor(END)
            return "break"

    def _entry_escape(self, __):
        self.editable = False

    def _entry_return(self, __):
        text = self._var.get()

        # Empty names are only alowed at first position (a root).
        niter = iter(text.split(sep))
        path = [next(niter)]
        for name in niter:
            if name:
                path.append(name)

        self.path = tuple(path)

        self.editable = False

    def _button_1(self, __):
        self.editable = True

        e = self._entry
        e.selection_range(0, END)
        e.icursor(END)
        e.focus_set()

        return "break"
