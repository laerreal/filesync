from os.path import (
    isdir,
    isfile,
    sep,
    exists,
)
from os import (
    listdir
)



class LocalFolder(object):

    def __new__(cls, *a, **kw):
        if cls is LocalFolder:
            raise TypeError("Can only instantiate a folder implementation")
        return object.__new__(cls)

    def __init__(self, local_path, rules):
        self.local_path = local_path
        self.rules = rules

    def __str__(self):
        return sep.join(self.local_path)

    def __call__(self, name):
        effective_rule = None
        new_effective_rule = None

        sub_rules = []
        for r in self.rules:
            r_path = r.relative_path
            if len(r_path) == 0:
                effective_rule = r
            elif r_path[0] == name:
                sub_r_path = r_path[1:]
                if len(sub_r_path) == 0:
                    if new_effective_rule is None:
                        new_effective_rule = type(r)(sub_r_path)
                    else:
                        raise RuntimeError("Several rules with same path")
                else:
                    sub_rules.append(type(r)(sub_r_path))

        if new_effective_rule is None:
            new_effective_rule = effective_rule

        assert new_effective_rule is not None

        sub_rules.insert(0, new_effective_rule)
        return self.__get_sub_folder__(name, sub_rules)

    def __get_sub_folder__(self, name, rules):
        return folder(self.local_path + (name,), rules)

    def __iter__(self):
        raise NotImplemented("%s: nodes enumeration is not implemented" % (
            type(self).__name__
        ))


class Directory(LocalFolder):

    def __iter__(self):
        for f in listdir(sep.join(self.local_path)):
            yield f


class NameNotExists(ValueError):
    pass


def folder(local_path, rules):
    if isdir(sep.join(local_path)):
        return Directory(local_path, rules)
    elif isfile(sep.join(local_path)):
        raise NotImplementedError("Archives are not supported")
    elif exists(sep.join(local_path)):
        raise ValueError("Unknown folder kind %s" % sep.join(local_path))
    else:
        raise NameNotExists(sep.join(local_path))
