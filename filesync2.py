from os.path import (
    getmtime,
    isfile,
    isdir,
    join,
    sep
)
from os import (
    utime,
    listdir
)
from argparse import (
    ArgumentParser
)
from six.moves.cPickle import (
    load,
    dump
)
from six.moves.tkinter import (
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
    Treeview
)
from collections import (
    defaultdict
)
from hashlib import (
    sha1
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


IS_WINDOWS = system() == "Windows"


FILE_NAME_ENCODING = "cp1251"


DIFF_CODE_NODES = "N"
DIFF_CODE_MOD_TIME = "T"
DIFF_CODE_CHECKSUM = "C"


class node(object):

    def __init__(self, name, container, full_path):
        self.name = name
        self._root_flags = 0
        self.roots = 0
        self.full_path = full_path
        self.container = None

        if container is not None:
            container.append(name, self)

        self._consistent_ = False
        self._prev_diffs = dict([(k, 1) for k in FileInfo_infos])

        self._iid = None

    def _get_file_diffs(self):
        pd = self._prev_diffs

        for name, code in FileInfo_infos.items():
            status = pd[name]
            if status == 1:
                diff = code + "?"
            elif status == 2:
                diff = code
            else:
                continue
            yield diff

    def diff(self, attr):
        return self._prev_diffs[attr] == 2

    def __info_changed__(self, name):
        _variants = set(getattr(inf, name) for inf in self.infos.values())
        if None in _variants:
            # `None` means some values are unknown for now.
            # But, if there is at least two different values except
            # `None` then the difference definitely takes place.
            if len(_variants) > 2:
                diff = 2 # there is difference
            else:
                diff = 1 # difference presence is unknown
        else:
            diff = 2 if len(_variants) > 1 else 0
            # 0 - no difference

        self.__diff__(name, diff)

    def __diff__(self, name, status):
        pd = self._prev_diffs
        if pd[name] == status:
            return
        pd[name] = status

        c = self.container
        if c is not None:
            c.__diff_changed__(self, name, status)

    @property
    def root_flags(self):
        return self._root_flags

    @root_flags.setter
    def root_flags(self, bits):
        if bits == self._root_flags:
            return

        self._root_flags = bits

        # update consistency
        self._update_consistency()

    @property
    def consistent_(self):
        raise RuntimeWarning("Must not be read")

    @consistent_.setter
    def consistent_(self, val):
        if val == self._consistent_:
            return
        self._consistent_ = val

        c = self.container
        if c is None:
            return

        if val:
            c.consistent_children += 1
        else:
            c.consistent_children -= 1

class directory(node):

    def __init__(self, *a, **kw):
        super(directory, self).__init__(*a, **kw)
        self.node_list = []
        self.node_dict = {}
        self._ready_children = 0

        # name set allows to estimate number of items within before they will
        # be analyzed.
        self._total_names = set()

        # Readiness of a directory may be changed because of multiple
        # reasons.
        # This intermediate, bottleneck value (a `property`) ensures that the
        # `container` is notified about last readiness state and this is done
        # *only once* for current state.
        self._ready_internal = False

        self._consistent_children = 0

        # root_idx -> DirInfo
        self.infos = defaultdict(lambda : DirInfo(self))

        self._update_consistency()

    def __diff_changed__(self, node, name, status):
        pd = self._prev_diffs
        cur = pd[name]

        if cur == status:
            return
        if cur > status:
            # diff status of a node become less. Is there a node with greater
            # status?
            status = max(n._prev_diffs[name] for n in self.node_list)
            if cur == status:
                return

        pd[name] = status

        c = self.container
        if c is not None:
            c.__diff_changed__(self, name, status)

        """
        cur = nd[name]
        XXX: alt impl: 2 = True (diff), 1 = None (unknow), 0 - False (no diff)

        if cur is status:
            return

        if status is True:
            # at least one node differs, so the directory does too
            nd[name] = True
        elif status is None:
            # Status of a node become unknown. If all nodes have not have diffs
            # then now the state of the directory is unknown. If at least one
            # has have diffs, we have to check does it now have.

            if cur is True:
                for n in self.node_list:
                    if n is node:
                        continue
                    if n._prev_diffs[name] is True:
                        # other node has diffs
                        return
                # else:
                # the node has have diffs before but now its status is unknown.

            nd[name] = None
        else: # status is False
            for n in self.node_list:
                if n is node:
                    continue
                if n._prev_diffs[name] is not False:
                    # a node has difference or its state is unknown
                    return
            nd[name] = False
        """

    @property
    def diffs(self):
        if len(self.node_list) > 0:
            res = list(self._get_file_diffs())
        else:
            res = []

        if not self.consistent:
            res.insert(0, DIFF_CODE_NODES)
        return " ".join(res)

    @property
    def consistent_children(self):
        return self._consistent_children

    @consistent_children.setter
    def consistent_children(self, value):
        if value == self._consistent_children:
            return
        self._consistent_children = value
        self.consistent_ = self.consistent

    @property
    def consistent(self):
        """
A directory is consistent if:
    & all its nodes are consistent
    & it presents in all trees
        """

        if self.consistent_children != self.total_items:
            return False
        c = self.container
        if c is None:
            return True
        return c._root_flags == self._root_flags

    def _update_consistency(self):
        for n in self.node_list:
            n._update_consistency()
        self.consistent_ = self.consistent

    @property
    def ready(self):
        return self._ready_children >= self.total_items

    @property
    def total_items(self):
        return len(self._total_names)

    @property
    def ready_children(self):
        return self._ready_children

    @ready_children.setter
    def ready_children(self, value):
        if value == self._ready_children:
            return

        self._ready_children = value
        self.ready_internal = self.ready

    @property
    def ready_internal(self):
        raise RuntimeWarning("Must not be read")

    @ready_internal.setter
    def ready_internal(self, value):
        if value == self._ready_internal:
            return

        self._ready_internal = value

        c = self.container

        if c is None:
            return

        if value:
            c.ready_children += 1
        else:
            c.ready_children -= 1

    def account_names(self, names):
        s = self._total_names
        prev_len = len(s)
        if names:
            s.update(names)
            if prev_len == len(s):
                return
        elif prev_len != 0:
            return
        # else:
        # if folder is empty it will never be written a `ready_children` value.
        # Because it is done by nodes within.
        # Such a folder is always ready and we should notify the container
        # about this at least once.

        self.ready_internal = self.ready

    def append(self, name, node):
        if name in self.node_dict:
            raise RuntimeError("Node %s already exists" % name)
        if node.container is not None:
            raise RuntimeError("Node %s already in a container" % name)

        self.node_dict[name] = len(self.node_list)
        self.node_list.append(node)
        node.container = self

    def __contains__(self, name):
        return name in self.node_dict

    def __getitem__(self, name):
        return self.node_list[self.node_dict[name]]

    def __setitem__(self, name, value):
        self.append(name, value)

    def items(self):
        l = self.node_list
        for name, idx in self.node_dict.items():
            yield name, l[idx]

    def values(self):
        return iter(self.node_list)

    def print_subdirs(self, indent = ""):
        for name, item in self.items():
            yield indent + "- " + name
            if isinstance(item, directory):
                for l in item.print_subdirs(indent + "   |"):
                    yield l

    def __str__(self):
        return "\n".join(self.print_subdirs())


FileInfo_infos = {
    "mtime" : DIFF_CODE_MOD_TIME, # modification time
    "checksum" : DIFF_CODE_CHECKSUM,
}


class FileInfo(object):

    def __init__(self, f):
        self.file = f
        self.full_name = None
        d = self.__dict__
        for i in FileInfo_infos:
            # XXX: honestly: `object.__setattr__(self, i, None)`
            d[i] = None

    def __setattr__(self, name, value):
        object.__setattr__(self, name, value)
        # TODO: some of checks are likely redundant now
        if name in FileInfo_infos: # and value != getattr(self, name):
            self.file.__info_changed__(name)


class DirInfo(object):

    def __init__(self, d):
        self.dir = d
        self.full_name = None


def _definitely_diff(_set):
    if None in _set:
        return len(_set) > 2
    else:
        return len(_set) > 1


class file(node):

    def __init__(self, *a, **kw):
        super(file, self).__init__(*a, **kw)

        # root_idx -> FileInfo
        self.infos = defaultdict(lambda : FileInfo(self))

        self._ready = False

        self._update_consistency()

    def __str__(self):
        return self.name + " (" + self.full_path + ")"

    @property
    def diffs(self):
        return " ".join(self._get_file_diffs())

    @property
    def ready(self):
        return self._ready

    @ready.setter
    def ready(self, value):
        if value == self._ready:
            return

        self._ready = value
        if value:
            self.container.ready_children += 1
        else:
            self.container.ready_children -= 1

    @property
    def consistent(self):
        """
A file is consistent if:
    & it presents in all trees
    & TODO
        """

        c = self.container
        if c is None:
            return True
        return self._root_flags == c._root_flags

    def _update_consistency(self):
        self.consistent_ = self.consistent


DEBUG_PATHS = True
DEBUG_TREE = False


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


def build_root_tree(root_path, root_dir, root_idx):
    global files_queue
    global scanned_roots

    root_flag = 1 << root_idx

    queue = [(sep.join(root_path), root_dir)]

    while queue:
        yield # a pause

        _path, _dir = queue.pop()

        nodes = listdir(_path)

        _dir.account_names(nodes)

        folders = []
        files = []

        for node_name in nodes:
            full_path = join(_path, node_name)
            if isdir(full_path):
                if node_name in _dir:
                    node = _dir[node_name]
                else:
                    node = directory(node_name, _dir, full_path)

                node.root_flags |= root_flag
                node.roots += 1

                node.infos[root_idx].full_name = full_path

                folders.append((full_path, node))
            elif isfile(full_path):
                if node_name in _dir:
                    node = _dir[node_name]
                else:
                    node = file(node_name, _dir, full_path)

                node.root_flags |= root_flag
                node.roots += 1
                node.ready = True

                files.append((full_path, node, root_idx))
            else:
                print("Node of unknown kind: %s" % full_path)

        # first analyze folders which do exists in much of trees
        folders = sorted(folders, key = by_roots)
        # if len(folders) > 1:
        #     assert folders[0][1].roots <= folders[-1][1].roots
        queue[:0] = folders

        files_by_roots = sorted(files, key = by_roots)
        files_queue[:0] = files_by_roots

    scanned_roots |= root_flag


files_queue = []
scanned_roots = 0


# CheckSum Block Size
CS_BLOCK_SZ = 1 << 20


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
        fi.mtime = getmtime(full_name)

        cs = sha1()

        with open(full_name, "rb") as f:
            while True:
                yield
                block = f.read(CS_BLOCK_SZ)
                if not block:
                    break
                cs.update(block)

        fi.checksum = cs.digest()


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

    ALL_ROOTS = (1 << len(roots)) - 1

    root_dir.root_flags = ALL_ROOTS

    tree_builder = build_common_tree(root_dir, roots)
    tasks.append(tree_builder)

    tasks.append(file_scaner())

    # GUI

    tk = Tk()
    tk.title("FileSync v2")
    tree_w = Frame(tk)

    tree_w.rowconfigure(0, weight = 1)
    tree_w.rowconfigure(1, weight = 0)
    tree_w.columnconfigure(0, weight = 1)
    tree_w.columnconfigure(1, weight = 0)

    # columns for node presence marks
    roots_cid = ["root%d" % i for i in range(len(roots))]

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

    def tree_updater(_dir):
        queue = list(reversed(list(_dir.values())))

        while queue:
            yield

            node = queue.pop()

            refresh_node(node)

            if isinstance(node, directory):
                for subnode in node.values():
                    queue.insert(0, subnode)


    def refresh_node(node):
        parent_iid = node2iid.get(node.container, "")

        values = []

        for i in range(len(roots)):
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
                text = node.name.decode(FILE_NAME_ENCODING),
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
                queue[:0] = n.node_list

        for n in second_pass:
            yield

            for fi in n.infos.values():
                full_name = fi.full_name

                # It's impossible now
                # if full_name is None:
                #     continue

                fi.mtime = getmtime(full_name)

                cs = sha1()

                with open(full_name, "rb") as f:
                    while True:
                        yield
                        block = f.read(CS_BLOCK_SZ)
                        if not block:
                            break
                        cs.update(block)

                fi.checksum = cs.digest()

                if n._iid is not None:
                    refresh_node(n)

    def sync_files(tree):
        global tv

        queue = [tree]

        # forget all
        while queue:
            yield

            n = queue.pop()
            if isinstance(n, file):
                if n.diff("checksum"):
                    pass # TODO
                else:
                    # If files have no differences then modification time is
                    # set to elder one.
                    fis = list(n.infos.values())
                    mtimes = set(fi.mtime for fi in fis)

                    if _definitely_diff(mtimes):
                        min_time = min(mtimes)

                        for fi in fis:
                            utime(fi.full_name, (min_time, min_time))

                        for fi in fis:
                            fi.mtime = getmtime(fi.full_name)

                        if n._iid:
                            refresh_node(n)
            elif isinstance(n, directory):
                queue[:0] = n.node_list

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

    def on_b3(e):
        row_iid = tv.identify_row(e.y)
        if not row_iid:
            return

        n = iid2node[row_iid]
        if not isinstance(n, directory):
            return

        tv.selection_set(row_iid)

        global popup_menu_point
        global popup_menu_node
        popup_menu_point = e.x, e.y
        popup_menu_node = n

        try:
            dir_menu.tk_popup(e.x_root, e.y_root)
        finally:
            dir_menu.grab_release()

    tv.bind("<Button-3>", on_b3, "+")

    def open_dir():
        global popup_menu_point
        global popup_menu_node

        try:
            col = tv.identify_column(popup_menu_point[0])
            col_idx = int(col[1:])
        except:
            print_exc()
            return

        root_idx = min(max(0, col_idx - 1), len(roots) - 1)
        # Reminder, root columns (with  "+"/"-" signs) are after column #0.

        for idx in chain(range(root_idx, len(roots)), range(0, root_idx)):
            di = popup_menu_node.infos[idx]
            if di.full_name is None:
                continue

            if IS_WINDOWS:
                Popen(["explorer", di.full_name])
            else:
                print("TODO: open %s" % di.full_name)

            break

    dir_menu.add_command(label = "Open", command = open_dir)


    bt_updatre_tree = Button(bt_frame,
        text = "Update tree",
        command = update_tree
    )
    bt_updatre_tree.pack(side = RIGHT)

    lb_tasks = Label(bt_frame)
    lb_tasks.pack(side = LEFT)

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

    while working:
        tk.update()
        tk.update_idletasks()

        i = 10
        while i:
            if tasks:
                t = tasks.pop()
                try:
                    next(t)
                except StopIteration:
                    print(t.__name__ + " finished")
                else:
                    tasks.insert(0, t)
            i -= 1

        lb_tasks.config(text = str(len(tasks)))

    tk.destroy()

    if DEBUG_TREE:
        print(root_dir)

    settings["roots"] = roots

    with open(SETTINGS_FILE, "wb") as f:
        dump(settings, f)
