__all__ = [
    "AnyServer"
]

from socket import (
    socket,
    AF_INET,
    SOCK_STREAM,
    SOL_SOCKET,
    SO_REUSEADDR
)


class AnyServer(socket):

    def __init__(self):
        super(AnyServer, self).__init__(AF_INET, SOCK_STREAM)
        self.setsockopt(SOL_SOCKET, SO_REUSEADDR, 1)
        # https://stackoverflow.com/questions/1365265/on-localhost-how-do-i-pick-a-free-port-number
        self.bind(("", 0))

    @property
    def port(self):
        return self.getsockname()[1]

    def accept_and_close(self):
        self.listen(1)
        ret = self.accept()
        self.close()
        return ret
