from os.path import (
    join
)
from collections import (
    defaultdict
)


DIFF_CODE_MOD_TIME = "T" # modification time
DIFF_CODE_CHECKSUM = "C"
DIFF_CODE_NODES = "N"

FileInfo_infos = {
    "mtime" : DIFF_CODE_MOD_TIME,
    "checksum" : DIFF_CODE_CHECKSUM,
}


class node(object):

    def __init__(self, name, container, full_path):
        self.name = name
        self.full_path = full_path
        self.container = None # managed by container

        # Amount of file systems (roots) containing such node.
        self.roots = 0
        # A bit field. A set bit means the corresponding root contains
        # variant of that node. Bit is (1 << root index).
        self._root_flags = 0

        if container is not None:
            container.append(name, self)

        self._consistent_ = False

        # self.infos = { set by child classes }
        # Each info describes that node variant in corresponding root.
        # Keyed by root index.

        # self._prev_diffs = { set by child classes }
        # When a difference is detected between values of corresponding
        # attributes of `infos`, the `container` should be notified of that.
        # That `dict` keyed by attribute name, contains difference status
        # previously reported to the `container`. So, the `container` is only
        # notified when difference status is actually changed.
        # Difference status values:
        # 2 - True (diff between at least 2 variants, some variants may be
        #    unknown),
        # 1 - None (unknown, all known variants are equal but there is
        #    at least 1 unknown variant),
        # 0 - False (all variants are known and all are equal)

        # for GUI
        self._iid = None

    def iter_path_reversed(self):
        n = self
        n_next = n.container
        while n_next:
            yield n.name
            n = n_next
            n_next = n.container

    @property
    def root_path(self):
        rpath = list(self.iter_path_reversed())
        _path = list(reversed(rpath))
        return join(*_path)

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

    def __info_changed__(self, attr):
        "Must be called when `attr` of one of `infos` is changed."
        _variants = set(getattr(inf, attr) for inf in self.infos.values())
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

        pd = self._prev_diffs
        if pd[attr] == diff:
            return
        pd[attr] = diff

        c = self.container
        if c is not None:
            c.__diff_changed__(self, attr, diff)

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

    # Node consistency definition may be different for subclasses.
    # See `consistent` attribute (`property`) `def`initions in subclasses.
    # But it is always a boolean.
    # When consistency of a node changes, its `container`'s
    # `consistent_children` counter must be updated.
    # `consistent_` & `_consistent_` (note "_") keeps previous boolean status
    # of that node consistency to correctly increase/decrease
    # `consistent_children` only when consistency is actually changed.
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

        # Initially a directory is empty, so it's known that *all* its files
        # have no difference (0)
        self._prev_diffs = dict([(k, 0) for k in FileInfo_infos])

        self.node_list = []
        self.node_dict = {} # node name to index in `node_list`
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

    def forget_files_diffs(self):
        if self._total_names:
            self._consider_files_unknown()

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
            if prev_len == 0:
                # it's first time this empty directory is given some files.
                # Now, information of differences in files must be considered
                # unknown (1).
                # Those files will be scanned later and the information becomes
                # known (0 or 2).
                self._consider_files_unknown()
            elif prev_len == len(s):
                return
        elif prev_len != 0:
            return
        # else:
        # if folder is empty it will never be written a `ready_children` value.
        # Because it is done by nodes within.
        # Such a folder is always ready and we should notify the container
        # about this at least once.

        self.ready_internal = self.ready

    def _consider_files_unknown(self):
        self._prev_diffs = dict([(k, 1) for k in FileInfo_infos])

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


class DirInfo(object):

    def __init__(self, d):
        self.dir = d
        self._reset()

    def _reset(self):
        self.full_name = None


class file(node):

    def __init__(self, *a, **kw):
        super(file, self).__init__(*a, **kw)

        # All information of a file is initially unknown (1)
        self._prev_diffs = dict([(k, 1) for k in FileInfo_infos])

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


class FileInfo(object):

    def __init__(self, f):
        self.file = f
        self._reset()

    def __setattr__(self, name, value):
        object.__setattr__(self, name, value)
        # TODO: some of checks are likely redundant now
        if name in FileInfo_infos: # and value != getattr(self, name):
            self.file.__info_changed__(name)

    def _reset(self):
        self.full_name = None
        d = self.__dict__
        for i in FileInfo_infos:
            # XXX: honestly: `object.__setattr__(self, i, None)`
            d[i] = None
