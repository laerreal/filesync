from .model import *

from os.path import (
    join,
    expanduser,
)


class Config(object):

    __slots__ = (
        "fs",
        "port",
        "name",
        "servers",
        "passphrase",
    )

    def __init__(self, **cfg):
        cfg.setdefault("servers", [])
        cfg.setdefault("passphrase", None)

        for k, v in cfg.items():
            setattr(self, k, v)


CFG_DIRECTORY = join(expanduser("~"), ".filesync")
CFG_FILE_NAME = join(CFG_DIRECTORY, "cfg.py")

def load_config():
    with open(CFG_FILE_NAME, "r") as f:
        cfg_code = f.read()
    glob = dict(globals())
    exec(cfg_code, glob)
    cfg = glob["cfg"]
    return cfg
