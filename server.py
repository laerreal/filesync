from os import (
    listdir
)
from os.path import (
    isfile,
    isdir,
    join,
    sep
)
from queue import (
    Empty
)
from six.moves.cPickle import (
    dumps,
    loads
)
from struct import (
    unpack,
    pack
)

_stat_io_bytes = 0
_stat_io_ops = 0

_globals = globals()
for io_op in [
    "listdir",
    "isdir",
    "isfile",
]:

    def gen_io_op(op):

        def io_op(*a, **kw):
            global _stat_io_ops
            _stat_io_ops += 1
            # print(op.__name__)
            return op(*a, **kw)

        return io_op

    _globals[io_op] = gen_io_op(_globals[io_op])


def proc_build_root_tree(q, root_path):
    queue = [(sep.join(root_path), 0)]

    dir_count = 1

    while queue:
        _path, _dir = queue.pop()

        q.put((0, (_path, _dir)))

        nodes = listdir(_path)

        q.put((1, nodes))

        folders = []

        for node_name in nodes:
            full_path = join(_path, node_name)
            if isdir(full_path):
                q.put((2, (node_name,)))

                folders.append((full_path, dir_count))
                dir_count += 1
            elif isfile(full_path):
                q.put((3, (node_name,)))
            else:
                print("Node of unknown kind: %s" % full_path)

        # TODO: first analyze folders which do exists in much of trees
        queue[:0] = folders

        q.put((4, None))

    q.put((None, None))


def get_global(outq, name):
    val = globals()[name]
    outq.put(val)


class Finalize(Exception): pass

def finalize(*_):
    raise Finalize


io_callbacks = [
    get_global,
    finalize,
]

GET_IO_OPS = (io_callbacks.index(get_global), ("_stat_io_ops",))
GET_IO_BYTES = (io_callbacks.index(get_global), ("_stat_io_bytes",))
FINALIZE_IO_PROC = (io_callbacks.index(finalize), tuple())

PROC_IO_TIMEOUT = 1.0


def proc_io(inq, outq):
    while True:
        try:
            cb, args = inq.get(True, PROC_IO_TIMEOUT)
        except Empty:
            continue

        cb = io_callbacks[cb]
        try:
            cb(outq, *args)
        except Finalize:
            break


def send(s, obj):
    data = dumps(obj)
    s.send(pack("!I", len(data)))
    s.send(data)


def recv(s):
    raw_len = s.recv(4)
    assert len(raw_len) == 4
    rest = unpack("!I", raw_len)[0]
    data = b""
    while rest:
        chunk = s.recv(rest)
        if not chunk:
            raise RuntimeError("Unexpected connection shutdown")
        rest -= len(chunk)
        data += chunk
    return loads(data)
