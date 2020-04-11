from threading import (
    Thread
)
from queue import (
    Empty,
    Queue,
)
from time import (
    sleep,
)
from socket import (
    timeout,
    socket,
    AF_INET,
    SOCK_STREAM
)
from .server import (
    send,
    co_recv,
)
from traceback import (
    print_exc,
)


class Server2Connection(Thread):

    def __init__(self, url, retries = 5):
        super(Server2Connection, self).__init__(
            target = self.main
        )

        self.working = True
        self.url = url
        self.retries = retries
        self.commands = Queue()

    def issue_command(self, co_handler_func, command, *args):
        co_handler = co_handler_func(*args)
        next(co_handler)
        self.commands.put((command, args, co_handler))

    def main(self):
        retries = self.retries
        url = self.url
        commands = self.commands

        s = socket(AF_INET, SOCK_STREAM)

        # Before connection timeout is big
        s.settimeout(1.)

        while self.working and retries:
            print("Connecting to " + str(url))
            try:
                s.connect(url)
            except timeout:
                continue
            except:
                print_exc()
                sleep(1.)
                print("retrying %d" % retries)
                retries -= 1
                continue
            break

        if not retries:
            print("Cannot connect")
            return

        s.settimeout(0.1)

        print("Connected to " + str(url))

        next_id = 1

        handlers = {}

        buf = [None]
        receiver = co_recv(s, buf)

        while self.working:
            try:
                command, args, co_handler = commands.get(
                    block = not bool(handlers),
                    timeout = 0.1
                )
            except Empty:
                if handlers:
                    try:
                        next(receiver)
                    except StopIteration:
                        res = buf[0]
                        buf[0] = None
                        receiver = co_recv(s, buf)
                    else:
                        continue

                    cmd_id = res[0]
                    h = handlers[cmd_id]
                    try:
                        h.send(res[1:])
                    except StopIteration:
                        del handlers[cmd_id]

                continue

            send(s, (next_id, command, args))
            handlers[next_id] = co_handler

            next_id += 1

        print("Disconnecting from " + str(url))
        s.close()

        print("Ending thread for " + str(url))
