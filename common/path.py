__all__ = [
    "fs_path",
    "re_path_sep",
]

from re import (
    compile,
)
from six import (
    binary_type,
)


re_path_sep = compile("\\r\\n|\\n|\\r")
re_split = re_path_sep.split

def fs_path(string):
    """
>>> fs_path("windows\\r\\nmultiline")
('windows', 'multiline')
>>> fs_path("linux\\nmultiline")
('linux', 'multiline')
>>> fs_path("mac\\nmultiline")
('mac', 'multiline')
>>> fs_path("mixed\\rmulti\\nOS\\r\\nmultiline")
('mixed', 'multi', 'OS', 'multiline')
    """

    if isinstance(string, tuple):
        ret = tuple()
        for e in string:
            ret += fs_path(e)
    else:
        if isinstance(string, binary_type):
            string = string.decode("utf-8")
        ret = tuple(re_split(string))
    return ret
