__all__ = [
    "LocalsCatcher"
]

from sys import (
    _getframe,
)


class LocalsCatcher(object):
    """ Catches local names defined during `with` statement and assigns them
to `self`.
    """

    @property
    def nosteal(self):
        "Do not remove locals after catching."
        self._steal = False
        return self

    @property
    def steal(self):
        "Remove caught locals. Default behavior, it's for code readability."
        self._steal = True
        return self

    def __enter__(self):
        self._locals = set(_getframe(1).f_locals)
        self.__dict__.setdefault("_steal", True)
        return self

    def __exit__(self, exc, *_):
        _d = self.__dict__

        if exc is not None:
            _d.pop("_locals")
            _d.pop("_steal")
            return

        locs = _getframe(1).f_locals
        new_locs = set(locs.keys()) - _d.pop("_locals")
        if _d.pop("_steal"):
            for l in new_locs:
                setattr(self, l, locs.pop(l))
        else:
            for l in new_locs:
                setattr(self, l, locs[l])

    def __str__(self):
        return super(LocalsCatcher, self).__str__() + \
            ":\n    " + \
            "\n    ".join(
                (n + " = " + "\n    ".join(str(v).split("\n"))
            ) for n, v in self.__dict__.items())


if __name__ == "__main__":
    lc = LocalsCatcher()

    a = 1

    with lc:
        b = a

        lc2 = LocalsCatcher()

        with lc2.steal:
            d = 4

        lc3 = LocalsCatcher()

        with lc3.nosteal:
            g = 8

        f = 6

    print(lc)
