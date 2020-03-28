from re import (
    compile
)


re_path_sep = compile(r"[/\\]")

def fs_path(string):
    return tuple(re_path_sep.split(string))
