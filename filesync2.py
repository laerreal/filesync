from os.path import (
    isfile,
    isdir,
    join,
    sep
)
from os import (
    listdir
)
from argparse import (
    ArgumentParser
)
from six.moves.tkinter import (
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


class node_name(object):

    def __init__(self, name, container, full_path):
        self.name = name
        self.root_flags = 0
        self.roots = 0
        self.full_path = full_path
        self.container = None

        if container is not None:
            container.append(name, self)

class directory(node_name):

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

class file(node_name):

    def __init__(self, *a, **kw):
        super(file, self).__init__(*a, **kw)

        self._ready = False

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


DEBUG_PATHS = True
DEBUG_TREE = False


def build_common_tree(root_dir, roots):
    builders = []
    for root_idx, root in enumerate(roots):
        root_flag = 1 << root_idx
        builders.append(build_root_tree(root, root_dir, root_flag))

    # TODO: CoDispatcher's call mechanics
    while builders:
        yield
        b = builders.pop(0)
        try:
            next(b)
        except StopIteration:
            pass
        else:
            builders.append(b)


def build_root_tree(root_path, root_dir, root_flag):
    queue = [(sep.join(root_path), root_dir)]

    while queue:
        yield # a pause

        _path, _dir = queue.pop()

        nodes = listdir(_path)

        _dir.account_names(nodes)

        folders = []

        for node_name in nodes:
            full_path = join(_path, node_name)
            if isdir(full_path):
                if node_name in _dir:
                    node = _dir[node_name]
                else:
                    node = directory(node_name, _dir, full_path)

                node.root_flags |= root_flag
                node.roots += 1
                folders.append((full_path, node))
            elif isfile(full_path):
                if node_name in _dir:
                    node = _dir[node_name]
                else:
                    node = file(node_name, _dir, full_path)

                node.root_flags |= root_flag
                node.roots += 1
                node.ready = True
            else:
                print("Node of unknown kind: %s" % full_path)

        # first analyze folders which do exists in much of trees
        folders = sorted(folders, key = lambda f: f[1].roots)
        # if len(folders) > 1:
        #     assert folders[0][1].roots <= folders[-1][1].roots
        queue[:0] = folders


COLOR_NODE_ABSENT = "#ffded8"
COLOR_NODE_NOT_READY = "gray"


if __name__ == "__main__":
    ap = ArgumentParser()
    ap.add_argument("-d", action = "append")

    args = ap.parse_args()

    if DEBUG_PATHS:
        print(args)

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

    if DEBUG_PATHS:
        print(roots)

    root_dir = directory("", None, "")

    ALL_ROOTS = (1 << len(roots)) - 1

    tree_builder = build_common_tree(root_dir, roots)

    # GUI

    # TODO: CoTaskManager
    tasks = [tree_builder]

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
        columns = roots_cid
    )

    tv.tag_configure("absent", background = COLOR_NODE_ABSENT)
    tv.tag_configure("notready", foreground = COLOR_NODE_NOT_READY)

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

    def tree_updater():
        if iid2node:
            tv.delete(*iid2node.keys())
            iid2node.clear()
            node2iid.clear()

        queue = list(reversed(list(root_dir.values())))

        while queue:
            yield

            node = queue.pop()

            parent_iid = node2iid.get(node.container, "")

            values = []

            for i in range(len(roots)):
                f = 1 << i
                values.append("+" if f & node.root_flags else "-")

            tags = []

            if node.root_flags != ALL_ROOTS:
                tags.append("absent")
            if not node.ready:
                tags.append("notready")

            iid = tv.insert(parent_iid, "end",
                text = node.name,
                tags = tags,
                values = values
            )
            iid2node[iid] = node
            node2iid[node] = iid

            if isinstance(node, directory):
                for subnode in node.values():
                    queue.insert(0, subnode)

    current_tree_updater = None
    def update_tree():
        global current_tree_updater
        if current_tree_updater is not None:
            try:
                tasks.remove(current_tree_updater)
            except ValueError:
                pass # already finished and removed
        current_tree_updater = tree_updater()
        tasks.append(current_tree_updater)

    bt_updatre_tree = Button(bt_frame,
        text = "Update tree",
        command = update_tree
    )
    bt_updatre_tree.pack(side = RIGHT)

    # Tk main loop
    working = True

    def delete_window():
        global working
        working = False

    tk.protocol("WM_DELETE_WINDOW", delete_window)

    while working:
        tk.update()
        tk.update_idletasks()

        i = 10
        while i:
            life_tasks = []
            for t in tasks:
                try:
                    next(t)
                except StopIteration:
                    print(t.__name__ + " finished")
                else:
                    life_tasks.append(t)
            tasks[:] = life_tasks
            i -= 1

    tk.destroy()

    if DEBUG_TREE:
        print(root_dir)
