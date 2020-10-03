from os import (
    utime,
    listdir
)
from os.path import (
    getmtime,
    isfile,
    isdir,
    join,
    sep
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
from hashlib import (
    sha1
)


DEBUG_SEND_RECV = False

_stat_io_bytes = 0
_stat_io_ops = 0

_globals = globals()
for io_op in [
    "utime",
    "listdir",
    "isdir",
    "isfile",
    "getmtime",
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

        try:
            nodes = listdir(_path)
        except PermissionError:
            # TODO: some information to the user
            nodes = []

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


def run_global_threaded(name, *args):
    Thread(target = globals()[name], args = args).start()


def get_global(name):
    val = globals()[name]
    return val


# CheckSum Block Size
CS_BLOCK_SZ = 1 << 20


def compute_checksum(full_name):
    global _stat_io_bytes

    cs = sha1()

    with open(full_name, "rb") as f:
        while True:
            block = f.read(CS_BLOCK_SZ)
            if not block:
                break
            _stat_io_bytes += len(block)
            cs.update(block)

    return cs.digest()


class Finalize(Exception): pass

def finalize():
    raise Finalize


io_callbacks = [
    get_global,
    finalize,
    run_global_threaded,
    compute_checksum,
    getmtime,
    utime,
]

GET_IO_OPS = (io_callbacks.index(get_global), ("_stat_io_ops",))
GET_IO_BYTES = (io_callbacks.index(get_global), ("_stat_io_bytes",))
FINALIZE_IO_PROC = (io_callbacks.index(finalize), tuple())
RUN_GLOBAL_CMD = io_callbacks.index(run_global_threaded)
BUILD_ROOT_TREE_PROC = "proc_build_root_tree"
COMPUTE_CHECKSUM_CMD = io_callbacks.index(compute_checksum)
GETMTIME_CMD = io_callbacks.index(getmtime)
UTIME_CMD = io_callbacks.index(utime)

PROC_IO_TIMEOUT = 1.0


def proc_io(port):
    s = socket(AF_INET, SOCK_STREAM)
    s.connect(("localhost", port))
    s.settimeout(PROC_IO_TIMEOUT)

    while True:
        try:
            cb, args = recv(s)
        except timeout:
            continue

        cb = io_callbacks[cb]
        try:
            res = cb(*args)
        except Finalize:
            break
        send(s, res)


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
        # note, `recv` does not catch `timeout` here
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
        # note, `recv` does not catch `timeout` here
        raw_len = b""
        while len(raw_len) < 4:
            try:
                chunk = s.recv(4 - len(raw_len))
            except timeout:
                if raw_len:
                    raise RuntimeError("Unexpected connection shutdown")
                raise
            if not chunk:
                raise RuntimeError("Unexpected connection shutdown")
            raw_len += chunk

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

    def co_recv_data(s, out, rest):
        recv = s.recv
        data = b""
        while rest:
            try:
                chunk = recv(rest)
            except timeout:
                yield
                continue
            if not chunk:
                if data:
                    raise RuntimeError("Unexpected connection shutdown")
                else:
                    return
            rest -= len(chunk)
            data += chunk
        out[0] = data

    def co_recv(s, out):
        out[0] = None
        for _ in co_recv_data(s, out, 4):
            yield

        raw_len = out[0]
        if raw_len is None:
            return
        rest = unpack("!I", raw_len)[0]

        out[0] = None
        for _ in co_recv_data(s, out, rest):
            yield

        data = out[0]
        if data is None:
            raise RuntimeError("Unexpected connection shutdown")

        out[0] = loads(data)
