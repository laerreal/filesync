from fs.config import (
    load_config,
)
from fs.external import (
    add_scrollbars_native,
)
from fs.server2 import (
    Error,
    HandlerFinished,
)
from fs.gui_server2_connection import (
    GUIServer2Connection,
)
from fs.identity import (
    Identity,
)
from widgets.path_view import (
    PathView
)
from widgets.dialog import (
    DialogContext,
)

from bisect import (
    bisect # used by auto gnerated `sorter`, see `_update_sorter`
)
from six.moves.tkinter import (
    BooleanVar,
    Menu,
    Tk,
)
from six.moves.tkinter_ttk import (
    Treeview,
)
from traceback import (
    print_exc,
)
from threading import (
    Lock,
)


class GUI(Tk):

    def __init__(self, cfg):
        # Initial data
        self.cfg = cfg

        # Properties
        self._caps_insensible_order = True

        # Widgets
        Tk.__init__(self)

        self.title("Files")

        menubar = Menu(self)
        self.config(menu = menubar)

        serversbar = Menu(menubar)
        menubar.add_cascade(label = "Servers", menu = serversbar)

        self._serversbar = serversbar
        self._serversbars = {} # thread -> idx

        viewbar = Menu(menubar)
        menubar.add_cascade(label = "View", menu = viewbar)

        self._var_caps_insensible_order = var = BooleanVar(self)
        var.set(self._caps_insensible_order)
        var.trace_variable("w", self._caps_insensible_order_tracer)
        viewbar.add_checkbutton(label = "Ignore caps", variable = var)

        self.columnconfigure(0, weight = 1)

        row = 0
        self.rowconfigure(row, weight = 0)

        self.pv = pv = PathView(self)
        pv.grid(row = row, column = 0, columnspan = 2, sticky = "NESW")
        pv.bind("<<PathChanged>>", self._pv_path_changed)

        row += 1
        self.rowconfigure(row, weight = 1)

        self.tv_files = tv_files = Treeview(self)

        tv_files.heading("#0", text = "Name")

        tv_files.bind("<Double-1>", self._tv_files_double_1)

        tv_files.grid(row = row, column = 0, sticky = "NESW")
        add_scrollbars_native(self, tv_files, row = row, sizegrip = True)

        # Runtime state
        self._current = None
        self._folders = []
        self._iids = []

        self._gui_lock = Lock()

        self._sorter_cache = []

        self._identity = Identity()

        # Startup
        self._update_sorter()

    @property
    def caps_insensible_order(self):
        return self.caps_insensible_order

    @caps_insensible_order.setter
    def caps_insensible_order(self, b):
        b = bool(b)
        if self._caps_insensible_order is b:
            return
        self._caps_insensible_order = b
        self._var_caps_insensible_order.set(b)

        self._update_sorter()

    def _caps_insensible_order_tracer(self, *__):
        self.caps_insensible_order = self._var_caps_insensible_order.get()

    def _update_sorter(self):
        sorter_code = "def sorter(container, cache = self._sorter_cache):\n"

        if self._caps_insensible_order:
            sorter_code += "    container = container.lower()\n"

        sorter_code += """\
    index = bisect(cache, container)
    cache.insert(index, container)
    return index

self._sorter = sorter
        """

        # print(sorter_code)

        with self._gui_lock:
            exec(sorter_code)
            self._reorder()

    def _reorder(self):
        folders = self._folders
        prev_folders = list(folders)
        del folders[:]

        iids = self._iids
        prev_iids = list(iids)
        del iids[:]

        move = self.tv_files.move

        del self._sorter_cache[:]
        sorter = self._sorter

        for f, iid in zip(prev_folders, prev_iids):
            idx = sorter(f)
            folders.insert(idx, f)
            iids.insert(idx, iid)
            move(iid, "", idx)

        # print("order = %s" % folders)

    def _pv_path_changed(self, e):
        self.current = e.widget.path[1:]

    def _tv_files_double_1(self, e):
        tv = e.widget
        sel = tv.selection()
        if not sel:
            return
        idx = self._iids.index(sel[0])
        name = self._folders[idx]
        self.current = self.current + (name,)

    def mainloop(self, *args, **kwargs):
        cfg = self.cfg
        servers = cfg.servers

        self.threads = threads = {}

        serversbar = self._serversbar
        servers_bars = self._serversbars

        for srv in servers:
            t = GUIServer2Connection(srv, self)
            threads[srv] = t

            serversbar.add_command(
                label = "%s [initialized]" % repr(srv),
            )
            servers_bars[t] = len(servers_bars) + (
                # tearoff line is an entry that has index
                1 if serversbar.cget("tearoff") else 0
            )

            t.start()

        self.after(1, self._startup)

        self.protocol("WM_DELETE_WINDOW", self._wm_delete_window)

        ret = Tk.mainloop(self, *args, **kwargs)

        return ret

    def _startup(self):
        self.after(1, self._open_identity)

    def _open_identity(self):
        dialogs = DialogContext(self, "Authentication")
        if not self._identity.open_ui(
                getpass = dialogs.getpass,
                feedback = dialogs.notify,
                passphrase = self.cfg.passphrase,
            ):
            return

        for t in self.threads.values():
            t.authenticate(self.cfg.name, self._identity)

    def _wm_delete_window(self):
        # TODO: confirmation
        self.after(1, self._finalize)

    def _finalize(self):
        for t in self.threads.values():
            t.working = False

        self.after(1, self._wait_for_threads)

    def _wait_for_threads(self):
        for t in self.threads.values():
            if t.is_alive():
                self.after(100, self._wait_for_threads)
                return

        self.destroy()

    @property
    def current(self):
        return self._current

    @current.setter
    def current(self, path):
        if path == self._current:
            return
        self._current = path

        print(path)

        tv = self.tv_files
        iid2s = self._iids
        if iid2s:
            tv.delete(*iid2s)
            del iid2s[:]

        del self._folders[:]
        del self._sorter_cache[:]

        self.issue_command_all("get_nodes", path)

        self.pv.path = ("",) + path

    def issue_command_all(self, command, *args):
        handler = getattr(self, "_co_handler_" + command)

        # one handler per server
        for t in self.threads.values():
            t.issue_command(handler, command, *args)

    def _co_handler_get_nodes(self, path):
        folders = self._folders
        iids = self._iids
        tv = self.tv_files
        lock = self._gui_lock

        while True:
            res = yield
            code = res[0]
            if isinstance(code, type):
                if code is HandlerFinished:
                    break
                if issubclass(code, Error):
                    break

            with lock:
                idx = self._sorter(code)
                folders.insert(idx, code)

                # print(idx, code)

                iid = tv.insert("", idx, text = code)
                iids.insert(idx, iid)

    def __conn_started__(self, t):
        idx = self._serversbars[t]
        self._serversbar.entryconfig(idx,
            label = "%s [started]" % repr(t.url)
        )

    def __conn_stopped__(self, t):
        idx = self._serversbars[t]
        self._serversbar.entryconfig(idx,
            label = "%s [stopped]" % repr(t.url)
        )

    def __conn_name__(self, t, name):
        idx = self._serversbars[t]
        self._serversbar.entryconfig(idx,
            label = "%s %r [operation]" % (name, t.url)
        )

    def __conn_authorized__(self, t):
        self.current = tuple()


def main():
    try:
        cfg = load_config()
    except:
        print_exc()
        print("Can't load config")
        return 1

    servers = cfg.servers

    local_server = ("localhost", cfg.port)
    if local_server not in servers:
        servers.append(local_server)

    root = GUI(cfg)
    root.mainloop()


if __name__ == "__main__":
    exit(main() or 0)
