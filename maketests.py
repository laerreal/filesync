#!/usr/bin/python

from subprocess import \
    check_call as cmd

from os.path import \
    join, \
    dirname, \
    exists

from os import \
    rmdir, \
    mkdir, \
    remove, \
    sep, \
    chdir

from sys import \
    stdout

from copy import \
    deepcopy as dcp

from traceback import \
    print_exc

scriptDir = dirname(__file__)

for gen in ["offgen", "linegen"]:
    genexe = join(scriptDir, gen + ".exe")
    cmd(["gcc", "-O3", "-o", genexe, join(scriptDir, gen + ".c")])


def offsetGenerator(fstf, offsetBytes = 4):
    cmd([
        join(scriptDir, "offgen.exe"),
        fstf.name,
        str(fstf.size),
        str(offsetBytes)
    ])


def lineGenerator(fstf):
    cmd([join(scriptDir, "linegen.exe"), fstf.name, str(fstf.size)])


class FSTestNode(object):
    def __init__(self, *children):
        self.children = d = {}
        for c in children:
            d[c.name] = c

        self.parent = None
        for c in children:
            c.parent = self

    def iter_path_reversed(self):
        c = self
        while c is not None:
            yield c
            c = c.parent

    @property
    def path(self):
        return sep.join(reversed(list(
            c.name for c in self.iter_path_reversed()
        )))

    def iter_children(self):
        return iter(self.children.values())

    def addChild(self, child):
        assert child.parent is None

        self.children[child.name] = child
        child.parent = self

    def __hash__(self):
        raise TypeError("Cannot hash abstract class.")

    def __deepcopy__(self, *args):
        raise TypeError("Abstract class cannot be deeply copied.")

    def isDir(self):
        return isinstance(self, FSTestDir)

    def isFile(self):
        return isinstance(self, FSTestFile)

    def exists(self):
        return exists(self.name)

    def __str__(self):
        return type(self).__name__ + "(%r)" % self.name

class FSTestFile(FSTestNode):
    def __init__(self, name,
        size = 0,
        generator = offsetGenerator
    ):
        super(FSTestFile, self).__init__()
        self.name = name
        self.size = size
        self.generator = generator

    def generate(self):
        if self.size:
            self.generator(self)
        else:
            open(self.name, "w").close()

    def remove(self):
        remove(self.name)

    def __hash__(self):
        return hash(self.name)

    def __deepcopy__(self, *args):
        return FSTestFile(
            self.name,
            size = self.size,
            generator = self.generator
        )

class FSTestDir(FSTestNode):
    def __init__(self, name, *children):
        super(FSTestDir, self).__init__(*children)
        self.name = name

    def __hash__(self):
        return hash(self.name)

    def enter(self):
        chdir(self.name)

    def clear(self):
        self.enter()
        for c in self.children.values():
            if c.exists():
                c.remove()
        chdir("..")

    def remove(self):
        if not exists(self.name):
            return
        self.clear()
        try:
            rmdir(self.name)
        except:
            print_exc()

    def generate(self):
        mkdir(self.name)

    def __deepcopy__(self, *args):
        return FSTestDir(
            self.name,
            *[ dcp(c) for c in self.children.values() ]
        )

    def __getitem__(self, path):
        cur = self
        for name in path.split(sep):
            if not name or name == ".":
                continue
            if name == "..":
                cur = cur.parent
            else:
                try:
                    cur = cur.children[name]
                except KeyError:
                    raise IOError('"%s" have no "%s"' % (cur.name, name))
        return cur

D = FSTestDir
F = FSTestFile

baseFS = D("root",
 D("emptyFiles",
  D("emptyFolder"),
  F("someFile"),
  F("file with spaces"),
  F("файлСКириллицейВНазвании")
 ),
 D("emptyDirectory"),
 D("empty directory with spaces"),
 D("dir",
   D("dir")
 ),
 D("пустаяПапакаСКириллицейВНазвании"),
 D("soldFiles",
   F("bigUnalignedFile", (123 << 19) + 123),
   F("bigFile", 123 << 20),
   F("smallFile", 123, generator = lineGenerator)
 )
)

def updateFS(root, verbose = False, indent = "  "):
    if verbose:
        curIndent = ""
        indentTrunc = -len(indent)

    stack = [root]
    while stack:
        n = stack.pop()

        if n is None:
            chdir("..")
            if verbose:
                curIndent = curIndent[:indentTrunc]
            continue

        isDir = n.isDir()

        if verbose:
            if not n.exists():
                if isDir:
                    n.generate()
                    print(curIndent + n.name + sep + " [gen]")
                else:
                    print(curIndent + n.name + " ...", end = "")
                    n.generate()
                    print(" [gen]")
            else:
                print(curIndent + n.name + (sep if isDir else "") + " [exists]")
        elif not n.exists():
            n.generate()

        if isDir:
            if verbose:
                curIndent = curIndent + indent
            n.enter()
            stack.append(None)
            for c in n.children.values():
                stack.append(c)

if __name__ == "__main__":
    verbose = True

    if verbose:
        def writeFlush(args, w=stdout.write):
            w(args)
            stdout.flush()

        stdout.write = writeFlush

    root1 = FSTestDir("test1", dcp(baseFS))
    root1["root"].addChild(D("folderInTest1Only"))

    root2 = FSTestDir("test2", dcp(baseFS))
    root2["root"]["пустаяПапакаСКириллицейВНазвании"].addChild(
        F("fileInTest2Only.txt", size = 22)
    )

    # Do several modifications
    root2[join("root", "soldFiles", "smallFile")].size += 13
    root2["root"]["dir"]["dir"].addChild(F("file"))

    root3 = FSTestDir("test3", dcp(root2["root"]))

    root3.remove()
    updateFS(root3, verbose = verbose)

    root1.remove()
    updateFS(root1, verbose = verbose)

    root2.remove()
    updateFS(root2, verbose = verbose)
