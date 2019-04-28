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
        self.full_path = full_path
        self.container = None

        if container is not None:
            container.append(name, self)

class directory(node_name):

    def __init__(self, *a, **kw):
        super(directory, self).__init__(*a, **kw)
        self.node_list = []
        self.node_dict = {}

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
    pass


DEBUG_PATHS = True
DEBUG_TREE = False


def build_common_tree(root_dir, roots):
    for root_idx, root in enumerate(roots):
        root_flag = 1 << root_idx
        queue = [(sep.join(root), root_dir)]

        while queue:
            yield # a pause

            _path, _dir = queue.pop()

            for node_name in listdir(_path):
                full_path = join(_path, node_name)
                if isdir(full_path):
                    if node_name in _dir:
                        node = _dir[node_name]
                    else:
                        node = directory(node_name, _dir, full_path)

                    node.root_flags |= root_flag
                    queue.insert(0, (full_path, node))

                elif isfile(full_path):
                    if node_name in _dir:
                        node = _dir[node_name]
                    else:
                        node = file(node_name, _dir, full_path)

                    node.root_flags |= root_flag
                else:
                    print("Node of unknown kind: %s" % full_path)


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

    tv = Treeview(tree_w)
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

            iid = tv.insert(parent_iid, "end", text = node.name)
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
