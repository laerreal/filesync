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
from threading import (
    Thread
)
from six.moves.cPickle import (
    dumps,
    loads
)
from struct import (
    unpack,
    pack
)
from socket import (
    timeout,
    socket,
    AF_INET,
    SOCK_STREAM
)

DEBUG_SEND_RECV = False

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


def proc_build_root_tree(port, root_path):
    s = socket(AF_INET, SOCK_STREAM)
    s.connect(("localhost", port))
    s.setblocking(True)

    queue = [(sep.join(root_path), 0)]

    dir_count = 1

    while queue:
        _path, _dir = queue.pop()

        send(s, (0, (_path, _dir)))

        nodes = listdir(_path)

        send(s, (1, nodes))

        folders = []

        for node_name in nodes:
            full_path = join(_path, node_name)
            if isdir(full_path):
                send(s, (2, (node_name,)))

                folders.append((full_path, dir_count))
                dir_count += 1
            elif isfile(full_path):
                send(s, (3, (node_name,)))
            else:
                print("Node of unknown kind: %s" % full_path)

        # TODO: first analyze folders which do exists in much of trees
        queue[:0] = folders

        send(s, (4, None))

    send(s, (None, None))


def run_global_threaded(_, name, *args):
    Thread(target = globals()[name], args = args).start()


def get_global(outq, name):
    val = globals()[name]
    outq.put(val)


class Finalize(Exception): pass

def finalize(*_):
    raise Finalize


io_callbacks = [
    get_global,
    finalize,
    run_global_threaded,
]

GET_IO_OPS = (io_callbacks.index(get_global), ("_stat_io_ops",))
GET_IO_BYTES = (io_callbacks.index(get_global), ("_stat_io_bytes",))
FINALIZE_IO_PROC = (io_callbacks.index(finalize), tuple())
RUN_GLOBAL_CMD = io_callbacks.index(run_global_threaded)
BUILD_ROOT_TREE_PROC = "proc_build_root_tree"

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


if DEBUG_SEND_RECV:
    serial = 0

    def send(s, obj):
        global serial
        data = dumps((serial, obj))
        serial += 1
        rest = len(data)
        # if rest == 39:
        #     print("!")
        if rest > 10000:
            print("<< %d" % rest)
        s.send(pack("!I", rest))
        while True:
            sent = s.send(data)
            rest -= sent
            if rest == 0:
                break
            print("fragment")
            data = data[sent:]

    def recv(s):
        raw_len = s.recv(4)
        assert len(raw_len) == 4
        rest = unpack("!I", raw_len)[0]
        if rest > 10000:
            print(">> %d %r" % (rest, raw_len))
        data = b""
        while rest:
            # print(rest)
            try:
                chunk = s.recv(rest)
            except timeout:
                continue
            print(len(chunk))
            assert len(chunk) <= rest
            if not chunk:
                raise RuntimeError("Unexpected connection shutdown")
            rest -= len(chunk)
            data += chunk

        serial, obj = loads(data)
        print(serial)
        return obj

else:

    def send(s, obj):
        data = dumps(obj)
        rest = len(data)
        s.send(pack("!I", rest))
        while True:
            sent = s.send(data)
            rest -= sent
            if rest == 0:
                break
            data = data[sent:]

    def recv(s):
        raw_len = s.recv(4)
        rest = unpack("!I", raw_len)[0]
        data = b""
        while rest:
            try:
                chunk = s.recv(rest)
            except timeout:
                continue
            if not chunk:
                raise RuntimeError("Unexpected connection shutdown")
            rest -= len(chunk)
            data += chunk
        return loads(data)
