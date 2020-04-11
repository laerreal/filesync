from os.path import (
    join,
    expanduser,
)
from .model import *


class Config(object):

    __slots__ = (
        "fs",
        "port",
        "name",
        "servers"
    )

    def __init__(self, **cfg):
        cfg.setdefault("servers", [])

        for k, v in cfg.items():
            setattr(self, k, v)


CFG_FILE_NAME = join(expanduser("~"), ".filesync", "cfg.py")

def load_config():
    with open(CFG_FILE_NAME, "r") as f:
        cfg_code = f.read()
    glob = dict(globals())
    exec(cfg_code, glob)
    cfg = glob["cfg"]
    return cfg
