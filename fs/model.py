from os.path import (
    sep
)
from re import (
    compile
)
from .folder import (
    NameNotExists,
    folder
)
from six import (
    binary_type,
)


re_path_sep = compile(r"[/\\]")

def fs_path(string):
    if isinstance(string, tuple):
        ret = tuple()
        for e in string:
            ret += fs_path(e)
    else:
        if isinstance(string, binary_type):
            string = string.decode("utf-8")
        ret = tuple(re_path_sep.split(string))
    return ret

class AccessRule(object):

    def __new__(cls, *a, **kw):
        if cls is AccessRule:
            raise TypeError("Can only instantiate concrete access rule")

        return object.__new__(cls)

    def __init__(self, relative_path):
        self.relative_path = relative_path

class AccessPrivate(AccessRule):
    pass

class AccessReadOnly(AccessRule):
    pass

class AccessFull(AccessRule):
    pass


DEFAULT_ACCESS_RULE = AccessFull(tuple())
DEFAULT_ACCESS_RULES = (DEFAULT_ACCESS_RULE,)

class MountPoint(object):

    def __init__(self, local_path, network_path,
        rules = DEFAULT_ACCESS_RULES,
        salt = 0
    ):
        """
@param salt: for ID unicity
        """
        local_path = fs_path(local_path)
        network_path = fs_path(network_path)

        self.local_path = local_path
        self.network_path = network_path
        self.rules = list(rules)
        self.salt = salt

        self.id = hash((local_path, network_path, salt))

    @property
    def folder(self):
        return folder(self.local_path, tuple(self.rules))

    def __str__(self):
        return sep.join(self.local_path) + " -> %s" % self.network_path


class FileSystem(object):

    def __init__(self, mount_points = tuple()):
        # All mount points must have unique IDs
        self.id2mp = id2mp = {}
        for mp in mount_points:
            if id2mp.setdefault(mp.id, mp) is not mp:
                raise ValueError(
                    "Mount point '%s' has same ID as '%s'" % (mp, id2mp[mp.id])
                )

        self.mount_points = list(mount_points)

    def get_nodes(self, network_path = tuple()):
        mps = self.mount_points

        mp_iters = enumerate(map(iter, (mp.network_path for mp in mps)))
        host_folders = []

        for name in network_path:
            next_mp_iters = list()
            for mp_idx, mp_iter in mp_iters:
                try:
                    mp_name = next(mp_iter)
                except StopIteration:
                    mp = mps[mp_idx]
                    host_folders.append(mp.folder)
                else:
                    if mp_name == name:
                        next_mp_iters.append((mp_idx, mp_iter))
            mp_iters = next_mp_iters

            next_host_folders = []
            for f in host_folders:
                try:
                    sub_f = f(name)
                except (NameNotExists, NotImplementedError):
                    continue
                next_host_folders.append(sub_f)
            host_folders = next_host_folders

        nodes = {}
        for mp_idx, mp_iter in mp_iters:
            try:
                name = next(mp_iter)
            except StopIteration:
                host_folders.append(mps[mp_idx].folder)
            else:
                nodes.setdefault(name, []).append(mps[mp_idx])

        for f in host_folders:
            for node in f:
                nodes.setdefault(node, []).append(f)

        return nodes

    def tree_str(self, depth = 3):
        ret = ""
        get_nodes = self.get_nodes

        stack = list((f,) for f in get_nodes())

        while stack:
            f = stack.pop()

            pfx = "  " * (len(f) - 1)
            ret += pfx + f[-1] + "\n"

            children = list((f + (n,)) for n in get_nodes(f))

            if len(f) >= depth:
                if children:
                    ret += pfx + "  [...]" + "\n"
                continue

            stack.extend(children)

        return ret
