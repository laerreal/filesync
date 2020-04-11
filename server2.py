from traceback import (
    print_exc,
    format_exc,
)
from socket import (
    timeout,
    SOL_SOCKET,
    SO_REUSEADDR,
    socket,
    AF_INET,
    SOCK_STREAM
)
from threading import (
    Thread,
    Lock,
)
from fs.server import (
    send,
    co_recv,
)
from fs.folder import (
    LocalFolder
)
from fs.config import (
    load_config
)
from fs.server2 import (
    NoSuchCommand,
    HandlerError,
    HandlerFinished
)
from fs.model import (
    AccessPrivate,
)


class ServerState(object):

    def __init__(self):
        self.working = True


class ClientState(object):

    def __init__(self, server):
        self.server = server


def main():
    try:
        cfg = load_config()
    except:
        print_exc()
        print("Can't load config")
        return 1

    try:
        assert bool(cfg.name)
    except:
        print_exc()
        print("Must have a name")
        return 1

    state = ServerState()

    print(cfg.fs.tree_str())

    s = socket(AF_INET, SOCK_STREAM)
    s.setsockopt(SOL_SOCKET, SO_REUSEADDR, 1)
    s.bind(("localhost", cfg.port))
    s.listen(2)
    s.settimeout(1.)

    print("Listening %s" % cfg.port)

    while state.working:
        try:
            incomming = s.accept()
        except timeout:
            continue

        c, remote = incomming
        remote_s = str(remote)
        print("Client connected: " + remote_s)

        c.settimeout(1.)
        t = Thread(target = client_func, args = (c, state, cfg, remote_s))
        t.name = "Client[%s]" % str(remote_s)
        t.start()

    s.close()

def client_func(c, server, cfg, name):
    state = ClientState(server)

    buf = [None]
    receiver = co_recv(c, buf)
    lock = Lock()

    while state.server.working:
        try:
            next(receiver)
        except StopIteration:
            pass
        else:
            continue

        msg = buf[0]
        if msg is None:
            print("Client %s disconnected" % name)
            break

        receiver = co_recv(c, buf)

        cmd_id, command, args = msg
        try:
            handler = globals()["cmd_" + command]
        except KeyError:
            send(c, (cmd_id, NoSuchCommand))

        t = Thread(
            target = executor_func,
            args = (c, lock, state, cfg, cmd_id, handler, args)
        )
        t.start()

    print("Clent %s thread ending" % name)


def executor_func(c, lock, state, cfg, cmd_id, handler, args):
    co = handler(state, cfg, *args)
    try:
        for ret in co:
            with lock:
                send(c, (cmd_id, ret))
    except:
        exc = format_exc()
        with lock:
            send(c, (cmd_id, HandlerError, exc))
    else:
        with lock:
            send(c, (cmd_id, HandlerFinished))


def cmd_get_nodes(state, cfg, path = tuple()):
    for node, extra in cfg.fs.get_nodes(path).items():
        if isinstance(extra, LocalFolder):
            if type(extra.effective_rule) is AccessPrivate:
                continue
        yield node

def cmd_identify_self(state, cfg):
    yield cfg.name


if __name__ == "__main__":
    exit(main() or 0)
