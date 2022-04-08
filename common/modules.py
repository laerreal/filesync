__all__ = [
    "SPECIAL_FILE_NAMES",
    "PYTHON_MOD_EXTS",
    "iter_module_files",
    "iter_modules",
    "iter_modules_recursive",
]


from os import (
    listdir,
)
from os.path import (
    isdir,
    join,
    splitext,
)


SPECIAL_FILE_NAMES = set([
    "__init__",
    "__main__",
    # ?
])

PYTHON_MOD_EXTS = set([
    "py", # source
    "pyd", # compilled library
    # ?
])


def iter_module_files(cur_dir):
    for item in listdir(cur_dir):
        name, ext = splitext(item)
        if ext[1:] in PYTHON_MOD_EXTS:
            yield name


def iter_modules(cur_dir):
    for item in listdir(cur_dir):
        name, ext = splitext(item)

        # filter out non-modules
        if ext[1:] in PYTHON_MOD_EXTS:
            if name in SPECIAL_FILE_NAMES:
                continue
        else:
            full_path = join(cur_dir, item)
            if isdir(full_path):
                # name = item, see below (a directory can have an "extension")
                for iname in iter_module_files(full_path):
                    if iname == "__init__":
                        name = item
                        break
                else:
                    # a directory without __init__
                    continue
            else:
                # a file with non-python extension
                continue

        yield name


def iter_modules_recursive(cur_dir):
    for name in iter_modules(cur_dir):
        mod = (name,)
        yield mod

        full_path = join(cur_dir, name)
        if isdir(full_path):
            for iname in iter_modules_recursive(full_path):
                yield mod + iname
