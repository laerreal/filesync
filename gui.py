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
from server import (
    send,
    co_recv,
)
from server2 import (
    Error,
    HandlerFinished,
)
from bisect import (
    bisect
)


class GUI(Tk):

    def __init__(self, cfg):
        self.cfg = cfg

        Tk.__init__(self)

        self.title("Files")

        self.columnconfigure(0, weight = 1)

        row = 0
        self.rowconfigure(row, weight = 1)

        self.tv_files = tv_files = Treeview(self)

        tv_files.heading("#0", text = "Name")

        tv_files.bind("<Double-1>", self._tv_files_double_1)

        tv_files.grid(row = row, column = 0, sticky = "NESW")
        add_scrollbars_native(self, tv_files, sizegrip = True)

        self._current = None
        self._folders = []
        self._iids = []

        self._gui_lock = Lock()

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
            t = Thread(target = self.server_connection, args = (srv, q))
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

        self.issue_command_all("get_nodes", path)

    def issue_command_all(self, command, *args):
        handler = getattr(self, "co_" + command)

        # one handler per server
        for _, q in self.threads.values():
            co_handler = handler(*args)
            next(co_handler)
            q.put((command, args, co_handler))

    def server_connection(self, srv, commands):
        s = socket(AF_INET, SOCK_STREAM)
        s.settimeout(0.1)

        while self.working:
            print("Connecting to " + str(srv))
            try:
                s.connect(srv)
            except timeout:
                continue
            break

        print("Connected to " + str(srv))

        next_id = 1

        handlers = {}

        buf = [None]
        receiver = co_recv(s, buf)

        while self.working:
            try:
                command, args, co_handler = commands.get(block = False)
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

    def co_get_nodes(self, path):
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
                idx = bisect(folders, code)
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
