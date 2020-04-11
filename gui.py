from six.moves.tkinter import (
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
    Thread,
)
from time import (
    sleep,
)
from queue import (
    Empty,
    Queue,
)
from socket import (
    timeout,
    socket,
    AF_INET,
    SOCK_STREAM
)
from fs.config import (
    load_config,
)
from fs.external import (
    add_scrollbars_native,
)
from fs.server import (
    send,
    co_recv,
)
from fs.server2 import (
    Error,
    HandlerFinished,
)
from widgets.path_view import (
    PathView
)
from bisect import (
    bisect # used by auto gnerated `sorter`, see `_update_sorter`
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

        self._update_sorter()

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

        servers = [
            ("localhost", cfg.port),
        ]

        self.working = True

        self.threads = threads = {}

        for srv in servers:
            q = Queue()
            t = Thread(target = self._server_connection, args = (srv, q))
            t.start()
            threads[srv] = (t, q)

        self.after(1, self._startup)

        ret = Tk.mainloop(self, *args, **kwargs)

        self.working = False

        for t in threads.values():
            t[0].join()

        return ret

    def _startup(self):
        self.current = tuple()

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
        for _, q in self.threads.values():
            co_handler = handler(*args)
            next(co_handler)
            q.put((command, args, co_handler))

    def _server_connection(self, srv, commands, retries = 5):
        s = socket(AF_INET, SOCK_STREAM)

        # Before connection timeout is big
        s.settimeout(1.)

        while self.working and retries:
            print("Connecting to " + str(srv))
            try:
                s.connect(srv)
            except timeout:
                continue
            except:
                print_exc()
                sleep(1.)
                print("retrying %d" % retries)
                retries -= 1
                continue
            break

        s.settimeout(0.1)

        print("Connected to " + str(srv))

        next_id = 1

        handlers = {}

        buf = [None]
        receiver = co_recv(s, buf)

        while self.working:
            try:
                command, args, co_handler = commands.get(
                    block = not bool(handlers),
                    timeout = 0.1
                )
            except Empty:
                if handlers:
                    try:
                        next(receiver)
                    except StopIteration:
                        res = buf[0]
                        buf[0] = None
                        receiver = co_recv(s, buf)
                    else:
                        continue

                    cmd_id = res[0]
                    h = handlers[cmd_id]
                    try:
                        h.send(res[1:])
                    except StopIteration:
                        del handlers[cmd_id]

                continue

            send(s, (next_id, command, args))
            handlers[next_id] = co_handler

            next_id += 1

        print("Disconnecting from " + str(srv))
        s.close()

        print("Ending thread for " + str(srv))

    def _co_handler_get_nodes(self, path):
        folders = self._folders
        iids = self._iids
        tv = self.tv_files
        lock = self._gui_lock

        while True:
            res = yield
            code = res[0]
            if code is HandlerFinished:
                break
            if code is Error:
                break

            with lock:
                idx = self._sorter(code)
                folders.insert(idx, code)

                iid = tv.insert("", idx, text = code)
                iids.insert(idx, iid)


def main():
    try:
        cfg = load_config()
    except:
        print_exc()
        print("Can't load config")
        return 1

    root = GUI(cfg)
    root.mainloop()


if __name__ == "__main__":
    exit(main() or 0)
