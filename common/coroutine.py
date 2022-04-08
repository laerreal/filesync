"""
Coroutine API
"""


__all__ = [
    "DEFAULT_CO_LIMIT",
    "set_co_limit",
    "get_co_limit",
    "CoDisp",
]


from collections import (
    deque,
)
from select import (
    select,
)
from types import (
    GeneratorType,
)


DEFAULT_CO_LIMIT = 40
_CO_LIMIT = DEFAULT_CO_LIMIT


def set_co_limit(limit = DEFAULT_CO_LIMIT):
    global _CO_LIMIT
    _CO_LIMIT = limit


def get_co_limit():
    return _CO_LIMIT


class CoDisp(object):

    def __init__(self):
        self.gotten = 0
        self.queue = deque()
        self.ready = deque()
        self.waiting = deque()
        self.callers = set()
        self.references = {}
        self.socketsToRead = {}
        self.socketsToWrite = {}
        self.readySockets = deque()
        self.current = None

        # extra self-declaring coroutine information
        self.desc = {}
        self.progress = {}
        self.goal = {}

    def coGoal(self, v):
        self.goal[self.current] = v

    def coProgress(self, v = None):
        "Add `v` to progress counter. `None` resets the counter."

        c = self.current

        if v is None:
            v = 0
        else:
            v += self.progress.get(c, 0)

        self.progress[c] = v

    def wake(self, co):
        self.waiting.remove(co)
        self.ready.append(co)

    def enqueue(self, co):
        self.queue.append(co)

    def select(self, timeout):
        s2r = self.socketsToRead
        s2w = self.socketsToWrite
        rs = self.readySockets

        if not (s2r or s2w):
            return False

        # Ready To Read(Write)
        r2r, r2w = select(s2r.keys(), s2w.keys(), [], timeout)[:2]

        for r in r2r:
            rs.append((s2r.pop(r), False))

        for w in r2w:
            rs.append((s2w.pop(w), False))

        if s2r:
            exceptions = select([], [], s2r.keys(), 0)[2]
            for r in exceptions:
                rs.append((s2r.pop(r), True))

        if s2w:
            exceptions = select([], [], s2w.keys(), 0)[2]
            for w in exceptions:
                rs.append((s2w.pop(w), True))

        return True

    """ An iteration contains
    - either 1 ready task
    - or 1 ready socket
    - or 1 new task from queue
    - or polling of all waiting tasks at the beginning of the iteration until
      a waiting task becomes ready (execution of this ready task is part of the
      iteration too).
    """
    def iteration(self):
        r = self.ready
        try:
            yield r.popleft(), None
        except IndexError:
            rs = self.readySockets
            try:
                yield rs.popleft()
            except IndexError:
                g = self.gotten
                if g < _CO_LIMIT:
                    try:
                        res = self.queue.popleft(), None
                    except IndexError:
                        pass
                    else:
                        g += 1
                        self.gotten = g
                        yield res
                        return

                w = self.waiting
                l = len(w)
                while l:
                    l -= 1

                    yield w.popleft(), None

                    # a task can be waked up
                    if len(r):
                        break

    def iterate(self):
        r = self.ready
        q = self.queue
        w = self.waiting
        c = self.callers
        refs = self.references
        s2r = self.socketsToRead
        s2w = self.socketsToWrite

        for co, sockErr in self.iteration():
            self.current = co
            try:
                try:
                    ret = co.send(sockErr)
                finally:
                    self.current = None
            except StopIteration:
                self.desc.pop(co, None)

                coRefs = refs.pop(co, tuple())

                g = self.gotten - 1
                for caller in coRefs:
                    c.remove(caller)
                    if g < _CO_LIMIT:
                        g += 1
                        r.appendleft(caller)
                    else:
                        q.appendleft(caller)
                self.gotten = g

                return True

            if isinstance(ret, GeneratorType):
                c.add(co)

                try:
                    coRefs = refs[ret]
                except KeyError:
                    coRefs = deque()
                    refs[ret] = coRefs

                coRefs.append(co)

                if ret in c:
                    self.gotten -= 1
                else:
                    r.append(ret)

                return True
            elif isinstance(ret, tuple):
                sock = ret[0]
                waitList = s2w if ret[1] else s2r

                waitList[sock] = co

                return True
            elif ret:
                r.append(co)
                return True

            w.append(co)

        return False
