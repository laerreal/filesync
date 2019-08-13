from os.path import (
    join,
    sep
)
from os import (
    mkdir,
    remove,
    rmdir,
)
from argparse import (
    ArgumentParser
)
from six.moves.cPickle import (
    load,
    dump
)
from six.moves.tkinter import (
    DISABLED,
    END,
    Text,
    IntVar,
    Menu,
    Label,
    LEFT,
    RIGHT,
    Button,
    Scrollbar,
    VERTICAL,
    HORIZONTAL,
    BOTH,
    Frame,
    Tk
)
from six.moves.tkinter_ttk import (
    Separator,
    Treeview
)
from collections import (
    defaultdict
)
from subprocess import (
    Popen
)
from traceback import (
    print_exc
)
from platform import (
    system
)
from itertools import (
    chain
)
from types import (
    GeneratorType
)
from six import (
    PY3
)
from time import (
    strftime,
    localtime,
    time
)
from multiprocessing import (
    Process
)
from server import (
    UTIME_CMD,
    GETMTIME_CMD,
    COMPUTE_CHECKSUM_CMD,
    CS_BLOCK_SZ as CP_BLOCK_SZ, # file copy block size
    send,
    recv,
    proc_io,
    FINALIZE_IO_PROC,
    GET_IO_OPS,
    GET_IO_BYTES,
    BUILD_ROOT_TREE_PROC,
    RUN_GLOBAL_CMD
)
from socket import (
    timeout,
)
from filemodel import (
    directory,
    file,
    FileInfo_infos
)
from widgets import (
    Hint
)
from common import (
    AnyServer
)


def text2content(text):
    "For Tkinter.Text"
    widget_height = float(text.index(END))
    widget_width = max((len(l) + 1) for l in text.get("1.0", END).split("\n"))

    text.config(width = widget_width, height = widget_height)


IS_WINDOWS = system() == "Windows"


FILE_NAME_ENCODING = "cp1251"

if PY3:
    def f2u(fname):
        return fname
else:
    def f2u(fname):
        return fname.decode(FILE_NAME_ENCODING)

_stat_io_ops = 0
_stat_io_bytes = 0

_io_proc_stat_io_ops = [0, 0] # previously and currently
_io_proc_stat_io_bytes = [0, 0]

_globals = globals()
for io_op in [
    "remove", "rmdir"
]:
    def gen_io_op(op):
        def io_op(*a, **kw):
            global _stat_io_ops
            _stat_io_ops += 1
            # print(op.__name__)
            return op(*a, **kw)
        return io_op
    _globals[io_op] = gen_io_op(_globals[io_op])


def format_checksum(val):
    return "".join("%0x" % ord(c) for c in val)


def format_mtime(val):
    t = localtime(val)
    raw = strftime("%Y.%m.%d %H:%M:%S", t)
    return f2u(raw)


FileInfo_info_formatters = defaultdict(
    lambda : str,
    mtime = format_mtime,
    checksum = format_checksum,
)


def _definitely_diff(_set):
    if None in _set:
        return len(_set) > 2
    else:
        return len(_set) > 1


DEBUG_PATHS = True
DEBUG_TREE = False


class CoRet(StopIteration):
    "Raise this in called coroutine to 'return' a `value` to the caller."

    def __init__(self, value, *a, **kw):
        StopIteration.__init__(self, *a, **kw)
        self.val = value


# TODO: CoTaskManager
tasks = []

def build_common_tree(root_dir, roots):
    global tasks

    for root_idx, root in enumerate(roots):
        # TODO: CoDispatcher's call mechanics
        tasks.insert(0, build_root_tree(root, root_dir, root_idx))

    yield # must be an generator


def by_roots(task):
    return task[1].roots


class ProcessContext(object): pass


def _set_cur_path(ctx, _path, dir_idx):
    ctx.path = _path
    ctx.dir = ctx.dirs[dir_idx]
    ctx.files = []


def _account_names(ctx, *nodes):
    ctx.dir.account_names(nodes)


def _it_is_dir(ctx, node_name):
    full_path = join(ctx.path, node_name)
    _dir = ctx.dir
    if node_name in _dir:
        node = _dir[node_name]
    else:
        node = directory(node_name, _dir, full_path)

    node.root_flags |= ctx.root_flag
    node.roots += 1

    node.infos[ctx.root_idx].full_name = full_path

    ctx.dirs.append(node)


def _it_is_file(ctx, node_name):
    full_path = join(ctx.path, node_name)
    _dir = ctx.dir
    if node_name in _dir:
        node = _dir[node_name]
    else:
        node = file(node_name, _dir, full_path)

    node.root_flags |= ctx.root_flag
    node.roots += 1
    node.ready = True

    ctx.files.append((full_path, node, ctx.root_idx))


def _dir_scaned(ctx):
    global files_queue

    files_by_roots = sorted(ctx.files, key = by_roots)
    files_queue[:0] = files_by_roots


proc_build_root_tree_cbs = [
    _set_cur_path,
    _account_names,
    _it_is_dir,
    _it_is_file,
    _dir_scaned,
]


def build_root_tree(root_path, root_dir, root_idx):
    global scanned_roots

    ss = AnyServer()
    yield co_io_proc_req(
        (RUN_GLOBAL_CMD, (BUILD_ROOT_TREE_PROC, ss.port, root_path))
    )
    s, _ = ss.accept_and_close()
    yield
    s.settimeout(0.01)

    ctx = ProcessContext()
    ctx.root_idx = root_idx
    ctx.root_flag = 1 << root_idx
    ctx.dirs = [root_dir]

    i = 0

    while not i:
        yield

        i = 100

        while i:
            i -= 1

            try:
                call, args = recv(s)
            except timeout:
                i = 0
                break
            if call is None:
                i = 1 # definitely exit upper `while`
                break
            cb = proc_build_root_tree_cbs[call]
            if args is None:
                cb(ctx)
            else:
                cb(ctx, *args)

    scanned_roots |= ctx.root_flag


def co_io_proc_req(*a, **kw):
    raise RuntimeError("I/O process is not ready yet, see co_io_proc")

def co_io_proc():
    global io_proc_sock
    global co_io_proc_req

    ss = AnyServer()
    p = Process(target = proc_io, args = (ss.port,))
    p.start()

    io_proc_sock, _ = ss.accept_and_close()
    io_proc_sock.settimeout(0.01)

    lock = [False]

    def co_io_proc_req(req):
        while lock[0]:
            yield
        lock[0] = True
        send(io_proc_sock, req)
        while True:
            yield
            try:
                res = recv(io_proc_sock)
                break
            except timeout:
                continue
            except:
                lock[0] = False
                raise

        lock[0] = False

        raise CoRet(res)

    while True:
        _io_proc_stat_io_ops[1] = yield co_io_proc_req(GET_IO_OPS)
        _io_proc_stat_io_bytes[1] = yield co_io_proc_req(GET_IO_BYTES)


files_queue = []
scanned_roots = 0


def get_mod_time(full_name):
    return co_io_proc_req((GETMTIME_CMD, (full_name,)))


def compute_checksum(full_name):
    return co_io_proc_req((COMPUTE_CHECKSUM_CMD, (full_name,)))


def set_mod_time(full_name, timestamp):
    return co_io_proc_req((UTIME_CMD, (full_name, timestamp)))


def file_scaner():
    global files_queue
    global scanned_roots
    global ALL_ROOTS

    while files_queue or ALL_ROOTS ^ scanned_roots:
        yield

        if not files_queue:
            continue

        full_name, node, root_idx = files_queue.pop()

        fi = node.infos[root_idx]

        fi.full_name = full_name
        fi.mtime = yield get_mod_time(full_name)

        fi.checksum = yield compute_checksum(full_name)


COLOR_NODE_ABSENT = "#ffded8"
COLOR_NODE_NOT_READY = "gray"
COLOR_NODE_INCONSISTENT = "#ffdd93"


SETTINGS_FILE = ".fs2.dat"


if __name__ == "__main__":
    ap = ArgumentParser()
    ap.add_argument("-d", action = "append", default = [])
    ap.add_argument("--forget",
        action = "store_true",
        help = "Forget root list"
    )

    args = ap.parse_args()

    if DEBUG_PATHS:
        print(args)

    try:
        with open(SETTINGS_FILE, "rb") as f:
            settings = load(f)
    except:
        print_exc()
        settings = {}

    roots = list([d] for d in args.d)

    # normalize paths
    for d in roots:
        for s in ["\\", "/"]:
            for i, part in enumerate(list(d)):
                subparts = part.split(s)
                if len(subparts) == 1:
                    continue
                del d[i]
                d[i:i] = subparts

            if DEBUG_PATHS:
                print(d)

        for i, part in reversed(list(enumerate(list(d)))):
            if not part:
                del d[i]

    if args.forget:
        try:
            del settings["roots"]
        except:
            pass
    else:
        for r in settings.get("roots", []):
            if r not in roots:
                roots.insert(0, r)

    if DEBUG_PATHS:
        print(roots)

    root_dir = directory("", None, "")

    TOTAL_ROOTS = len(roots)
    ALL_ROOTS = (1 << TOTAL_ROOTS) - 1

    root_dir.root_flags = ALL_ROOTS

    tree_builder = build_common_tree(root_dir, roots)
    tasks.append(tree_builder)

    tasks.append(file_scaner())

    tasks.append(co_io_proc())

    # GUI

    tk = Tk()
    tk.title("FileSync v2")
    tree_w = Frame(tk)

    tree_w.rowconfigure(0, weight = 1)
    tree_w.rowconfigure(1, weight = 0)
    tree_w.columnconfigure(0, weight = 1)
    tree_w.columnconfigure(1, weight = 0)

    # columns for node presence marks
    roots_cid = ["root%d" % i for i in range(TOTAL_ROOTS)]

    tv = Treeview(tree_w,
        columns = roots_cid + [
            "diffs"
        ]
    )

    tv.tag_configure("absent", background = COLOR_NODE_ABSENT)
    tv.tag_configure("notready", foreground = COLOR_NODE_NOT_READY)
    tv.tag_configure("inconsistent", background = COLOR_NODE_INCONSISTENT)

    for rcid in roots_cid:
        tv.column(rcid, stretch = False, width = 20)

    tv.grid(row = 0, column = 0, sticky = "NESW")

    h_sb = Scrollbar(tree_w,
        orient = HORIZONTAL,
        command = tv.xview
    )
    h_sb.grid(row = 1, column = 0, sticky = "EW")

    v_sb = Scrollbar(tree_w,
        orient = VERTICAL,
        command = tv.yview
    )
    v_sb.grid(row = 0, column = 1, sticky = "NS")

    tv.configure(xscrollcommand = h_sb.set, yscrollcommand = v_sb.set)

    tree_w.rowconfigure(2, weight = 0)
    bt_frame = Frame(tree_w)
    bt_frame.grid(row = 2, column = 0, columnspan = 2, sticky = "NESW")

    tree_w.pack(fill = BOTH, expand = True)

    # TODO: bidict
    iid2node = {}
    node2iid = {}

    # Root item is never explicitly created. But corresponding data must be
    # consistent.
    root_dir._iid = ""
    iid2node[""] = root_dir
    node2iid[root_dir] = ""

    # Root is always open. Option "open" has no effect. But setting it to
    # `True` simplifies tree update algorithm
    tv.item("", open = True)

    def tree_updater(_dir):
        if isinstance(_dir, directory):
            queue = list(reversed(list(_dir.values())))
        else:
            queue = [_dir]

        while queue:
            yield

            node = queue.pop()

            refresh_node(node)

            if isinstance(node, directory):
                # Not that nodes of a closed directories must be updated too.
                # It's required for [+] sign (expandable mark) to be shown if
                # the directory has nodes.
                c = node.container
                if c is None or tv.item(c._iid, "open"):
                    for subnode in node.values():
                        queue.insert(0, subnode)


    def refresh_node(node):
        parent_iid = node2iid.get(node.container, "")

        values = []

        for i in range(TOTAL_ROOTS):
            f = 1 << i
            values.append("+" if f & node.root_flags else "-")

        values.append(node.diffs)

        tags = []

        if node.root_flags != ALL_ROOTS:
            tags.append("absent")
        else:
            if not node.consistent:
                tags.append("inconsistent")
        if not node.ready:
            tags.append("notready")

        iid = node._iid
        if iid is None:
            iid = tv.insert(parent_iid, "end",
                text = f2u(node.name),
                tags = tags,
                values = values
            )
            iid2node[iid] = node
            node2iid[node] = iid
            node._iid = iid
        else:
            tv.item(iid, tags = tags, values = values)

    def rescan_files(tree):
        global tv

        queue = [tree]
        second_pass = []

        # forget all
        while queue:
            yield

            n = queue.pop()
            if isinstance(n, file):
                for fi in n.infos.values():
                    fi.mtime = fi.checksum = None
                if n._iid is not None:
                    refresh_node(n)
                second_pass.append(n)
            elif isinstance(n, directory):
                n.forget_files_diffs()
                queue[:0] = n.node_list

        for n in second_pass:
            yield

            for fi in n.infos.values():
                full_name = fi.full_name

                # It's impossible now
                # if full_name is None:
                #     continue

                fi.mtime = yield get_mod_time(full_name)

                fi.checksum = yield compute_checksum(full_name)

                if n._iid is not None:
                    refresh_node(n)

    def _replace_file(src, dst):
        global _stat_io_bytes

        with open(src.full_name, "rb") as fsrc:
            with open(dst.full_name, "wb") as fdst:
                while True:
                    yield
                    block = fsrc.read(CP_BLOCK_SZ)
                    if not block:
                        break
                    _stat_io_bytes += len(block)
                    yield
                    fdst.write(block)
                    _stat_io_bytes += len(block)

        yield
        dst.checksum = src.checksum

        yield set_mod_time(dst.full_name, (src.mtime, src.mtime))

    def sync_files(tree):
        global tv

        queue = [tree]

        # forget all
        while queue:
            yield

            n = queue.pop()
            presence = n.root_flags

            if isinstance(n, file):
                changed = False
                if n.diff("checksum"):
                    fis = sorted(n.infos.values(), key = lambda fi :-fi.mtime)

                    if None not in fis:
                        newest_checksum = fis[0].checksum
                        for i, fi in enumerate(fis):
                            if fi.checksum != newest_checksum:
                                elder_of_newest = fis[i - 1]
                                break
                        else:
                            print("!: all checksums equal while a diff is detected")

                        ts = (elder_of_newest.mtime, elder_of_newest.mtime)

                        for fi in fis:
                            if fi is elder_of_newest:
                                continue
                            if fi.checksum != elder_of_newest.checksum:
                                yield _replace_file(elder_of_newest, fi)
                            elif fi.mtime != elder_of_newest:
                                yield set_mod_time(fi.full_name, ts)

                        changed = True
                else:
                    # If files have no differences then modification time is
                    # set to elder one.
                    fis = list(n.infos.values())
                    mtimes = set(fi.mtime for fi in fis)

                    if _definitely_diff(mtimes):
                        min_time = min(mtimes)

                        ts = (min_time, min_time)

                        for fi in fis:
                            yield set_mod_time(fi.full_name, ts)

                        changed = True

                if changed:
                    for fi in fis:
                        fi.mtime = yield get_mod_time(fi.full_name)

                    if n._iid:
                        refresh_node(n)
            elif isinstance(n, directory):
                if presence != ALL_ROOTS:
                    root_path = n.root_path
                    for i in range(TOTAL_ROOTS):
                        root_flag = 1 << i
                        if root_flag & presence:
                            continue

                        yield
                        absent = join(sep.join(roots[i]), root_path)
                        mkdir(absent)
                        n.root_flags |= root_flag
                        n.roots += 1

                    if n._iid:
                        refresh_node(n)

                queue[:0] = n.node_list

    def delete_tree(tree, root_idx):
        global tasks

        queue = [tree]
        dirs = []

        root_clear_mask = ALL_ROOTS - (1 << root_idx)

        while queue:
            yield

            n = queue.pop()
            info = n.infos[root_idx]
            full_name = info.full_name

            if full_name is None:
                continue

            if isinstance(n, file):
                remove(full_name)
                del n.infos[root_idx]
                for name in FileInfo_infos:
                    n.__info_changed__(name)
                n.root_flags &= root_clear_mask
            elif isinstance(n, directory):
                queue[:0] = n.node_list
                dirs.insert(0, n)

        for n in dirs:
            yield
            rmdir(n.infos.pop(root_idx).full_name)
            n.root_flags &= root_clear_mask

        tasks.insert(0, tree_updater(tree))


    def cancel_task(t):
        try:
            tasks.remove(t)
        except ValueError:
            pass # already finished and removed

    current_tree_updater = None
    def update_tree():
        global current_tree_updater
        if current_tree_updater is not None:
            cancel_task(current_tree_updater)
        current_tree_updater = tree_updater(root_dir)
        tasks.insert(0, current_tree_updater)

    tk.after(100, update_tree)

    target_tree_updater = None
    def on_treeview_open(*_):
        global target_tree_updater

        # targeted update
        iid = tv.focus()
        if not iid:
            return

        node = iid2node[iid]
        if isinstance(node, directory):
            if target_tree_updater is not None:
                cancel_task(target_tree_updater)

            target_tree_updater = tree_updater(node)
            tasks.insert(0, target_tree_updater)
        elif isinstance(node, file):
            if node.diff("checksum"):
                paths = list(i.full_name for i in node.infos.values())
                try:
                    Popen(["meld"] + paths[:2])
                except:
                    print_exc()

    tv.bind("<<TreeviewOpen>>", on_treeview_open)

    def acc_print_event(e):
        "Print key event parameters"
        print(e.keycode)

    accels = defaultdict(lambda : acc_print_event)

    def acc_rescan_files(e):
        "Rescan files in selected folders"
        global tasks
        sel = tv.selection()
        for iid in sel:
            tasks.insert(0, rescan_files(iid2node[iid]))

    accels[82] = acc_rescan_files

    def acc_sync_files(_):
        "Synchronize files in selected folders"

        global tasks
        sel = tv.selection()
        for iid in sel:
            tasks.insert(0, sync_files(iid2node[iid]))

    accels[83] = acc_sync_files

    def on_ctrl_key(e):
        f = accels[e.keycode]
        # print(f.__doc__)
        f(e)

    tv.bind("<Control-Key>", on_ctrl_key)

    dir_menu = Menu(tv, tearoff = False)
    file_menu = Menu(tv, tearoff = False)

    def menu_set_node_specific(m, n):
        del_menu = m._del_menu

        # clear first
        del_menu.delete(0, "end")

        infos = n.infos
        for idx in range(TOTAL_ROOTS):
            i = infos[idx]
            if i.full_name is None:
                continue

            label = str(idx) + ": " + f2u(i.full_name)

            def do_delete(n = n, idx = idx):
                global tasks
                print("del " + n.infos[idx].full_name)
                tasks.insert(0, delete_tree(n, idx))

            del_menu.add_command(label = label, command = do_delete)

    def on_b3(e):
        row_iid = tv.identify_row(e.y)
        if not row_iid:
            return

        n = iid2node[row_iid]

        tv.selection_set(row_iid)

        global popup_menu_point
        global popup_menu_node
        popup_menu_point = e.x_root, e.y_root, e.x, e.y
        popup_menu_node = n

        menu = dir_menu if isinstance(n, directory) else file_menu

        menu_set_node_specific(menu, n)

        try:
            menu.tk_popup(e.x_root, e.y_root)
        finally:
            menu.grab_release()

    tv.bind("<Button-3>", on_b3, "+")

    hint = None

    def on_hint_destroyed(self):
        global hint
        hint = None

    last_b1_n = None

    def show_info(n, x, y):
        global hint
        global last_b1_n

        if hint is not None:
            hint.destroy()

        hint = Hint(x = x, y = y)
        hint.bind("<Destroy>", on_hint_destroyed, "+")

        for i, fi in sorted(n.infos.items()):
            if fi.full_name is None:
                continue
            t = Text(hint)
            t.tag_config("diff", background = COLOR_NODE_ABSENT)
            t.insert(END, f2u(fi.full_name))

            for attr in FileInfo_infos:
                v = getattr(fi, attr)
                pretty = FileInfo_info_formatters[attr](v)
                line = attr + ": " + pretty

                t.insert(END, "\n")
                if FileInfo_infos[attr] in n.diffs:
                    t.insert(END, line, "diff")
                else:
                    t.insert(END, line)

            t.config(state = DISABLED)
            t.pack(expand = True, padx = 3, pady = 3)
            text2content(t)

    def open_dir():
        global popup_menu_point
        global popup_menu_node

        try:
            col = tv.identify_column(popup_menu_point[2])
            col_idx = int(col[1:])
        except:
            print_exc()
            return

        root_idx = min(max(0, col_idx - 1), TOTAL_ROOTS - 1)
        # Reminder, root columns (with  "+"/"-" signs) are after column #0.

        for idx in chain(range(root_idx, TOTAL_ROOTS), range(0, root_idx)):
            di = popup_menu_node.infos[idx]
            if di.full_name is None:
                continue

            if IS_WINDOWS:
                Popen(["explorer", di.full_name])
            else:
                print("TODO: open %s" % di.full_name)

            break

    dir_menu.add_command(label = "Open", command = open_dir)

    def sync_files_menu():
        global popup_menu_node
        tasks.insert(0, sync_files(popup_menu_node))

    def show_info_menu():
        global popup_menu_node
        global popup_menu_point
        x, y = popup_menu_point[:2]
        show_info(popup_menu_node, x - 5, y - 5)

    file_menu.add_command(
        label = "Info",
        command = show_info_menu
    )

    for m in (dir_menu, file_menu):
        m.add_command(label = "Sync",
            command = sync_files_menu,
            accel = "Ctrl+S"
        )
        m.add_separator()
        m._del_menu = del_menu = Menu(m, tearoff = False)
        m.add_cascade(label = "Delete", menu = del_menu)

    bt_updatre_tree = Button(bt_frame,
        text = "Update tree",
        command = update_tree
    )
    bt_updatre_tree.pack(side = RIGHT)

    lb_tasks = Label(bt_frame)
    lb_tasks.pack(side = LEFT)
    Label(bt_frame, text = "Tasks").pack(side = LEFT)
    Separator(bt_frame, orient = VERTICAL).pack(side = LEFT, fill = "y")

    lb_iops = Label(bt_frame, text = "0")
    lb_iops.pack(side = LEFT)
    Label(bt_frame, text = "IO/s").pack(side = LEFT)
    Separator(bt_frame, orient = VERTICAL).pack(side = LEFT, fill = "y")

    lb_iobs = Label(bt_frame, text = "0")
    lb_iobs.pack(side = LEFT)
    Label(bt_frame, text = "MiB/s").pack(side = LEFT)
    Separator(bt_frame, orient = VERTICAL).pack(side = LEFT, fill = "y")

    # Task executions per Tk main loop iteration
    var_tpi = IntVar(value = 0)
    lb_tpi = Label(bt_frame, textvariable = var_tpi)
    lb_tpi.pack(side = LEFT)
    Label(bt_frame, text = "T/I").pack(side = LEFT)
    Separator(bt_frame, orient = VERTICAL).pack(side = LEFT, fill = "y")

    # Tk main loop
    working = True

    def delete_window():
        global settings
        settings["geometry"] = tk.geometry()

        global working
        working = False

    tk.protocol("WM_DELETE_WINDOW", delete_window)

    tv.focus_set()

    def set_geometry():
        yield
        tk.geometry(settings.setdefault("geometry", tk.geometry()))

    tasks.append(set_geometry())

    def update_stats():
        global _stat_io_ops
        global _stat_io_bytes

        tk.after(1000, update_stats)

        io_ops = _io_proc_stat_io_ops[1] - _io_proc_stat_io_ops[0]
        _io_proc_stat_io_ops[0] += io_ops
        _stat_io_ops += io_ops

        io_bytes = _io_proc_stat_io_bytes[1] - _io_proc_stat_io_bytes[0]
        _io_proc_stat_io_bytes[0] += io_bytes
        _stat_io_bytes += io_bytes

        iostat.write(str(_stat_io_ops) + ";" + str(_stat_io_bytes) + "\n")

        lb_iops.config(text = str(_stat_io_ops))
        _stat_io_ops = 0

        lb_iobs.config(text = str(_stat_io_bytes >> 20))
        _stat_io_bytes = 0

    iostat = open("iostat_%f.csv" % time(), "w")

    tk.after_idle(update_stats)

    callers = {} # task yielded key task

    task_iterations = 64
    var_tpi.set(task_iterations)

    while working:
        tk.update()
        tk.update_idletasks()

        i = task_iterations
        t1 = time()
        while i:
            if tasks:
                t = tasks.pop()
                try:
                    if type(t) is tuple:
                        t, callee_ret = t
                        res = t.send(callee_ret)
                    else:
                        res = next(t)
                except StopIteration as ret:
                    try:
                        caller = callers.pop(t)
                    except KeyError:
                        print(t.__name__ + " finished")
                        if not tasks:
                            break
                    else:
                        if type(ret) is StopIteration:
                            # simple return
                            tasks.insert(0, caller)
                        else: # CoRet or subclasses
                            # returning a value
                            # print(t.__name__ + " returns " + repr(ret.val) +
                            #         " to " + caller.__name__
                            # )
                            tasks.insert(0, (caller, ret.val))
                else:
                    if res is None:
                        tasks.insert(0, t)
                    elif type(res) is GeneratorType:
#                         print(t.__name__ + " calls " + res.__name__)
                        callers[res] = t
                        tasks.insert(0, res)
                    else:
                        print(t.__name__ + " yielded %r" % res)
            i -= 1

        t2 = time()

        tot_tasks = len(tasks)
        task_iter_limit = max(1, tot_tasks) << 5

        if t2 - t1 > 0.2 and task_iterations > 2:
            task_iterations >>= 1
            var_tpi.set(task_iterations)
        elif t2 - t1 < 0.05 and task_iterations < (task_iter_limit << 1):
            task_iterations <<= 1
            var_tpi.set(task_iterations)

        if task_iterations > task_iter_limit:
            task_iterations = task_iter_limit
            var_tpi.set(task_iterations)

        lb_tasks.config(text = str(tot_tasks))

    tk.destroy()

    # XXX: server may fail after that because a `co_io_proc_req` call is
    # interrupted.
    send(io_proc_sock, FINALIZE_IO_PROC)
    io_proc_sock.close()

    if DEBUG_TREE:
        print(root_dir)

    settings["roots"] = roots

    with open(SETTINGS_FILE, "wb") as f:
        dump(settings, f)

    iostat.close()
