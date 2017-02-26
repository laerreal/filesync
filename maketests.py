#!/usr/bin/python

from subprocess import \
    check_call as cmd

from os.path import \
    join, \
    dirname, \
    exists

from os import \
    sep, \
    chdir

from sys import \
    stdout

from copy import \
    deepcopy as dcp

scriptDir = dirname(__file__)
offgen = join(scriptDir, "offgen.exe")

cmd(["gcc", "-O3", "-o", offgen, join(scriptDir, "offgen.c")])

def offsetGenerator(fstf, offsetBytes = 4):
    cmd([offgen, fstf.name, str(fstf.size), str(offsetBytes)])

class FSTestNode(object):
    def __init__(self, *children):
        self.children = d = {}
        for c in children:
            d[c.name] = c

        self.parent = None
        for c in children:
            c.parent = self

    def addChild(self, child):
        assert child.parent is None

        self.children.add(child)
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
        cmd(["rm", self.name])

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
        self.clear()
        cmd(["rmdir", self.name])

    def generate(self):
        cmd(["mkdir", self.name])

    def __deepcopy__(self, *args):
        return FSTestDir(
            self.name,
            *[ dcp(c) for c in self.children.values() ]
        )

D = FSTestDir
F = FSTestFile

baseFS = D("root",
 D("emptyFiles",
  F("sameFile"),
  F("file with spaces"),
  F("файлСКириллицейВНазвании")
 ),
 D("emptyDirectory"),
 D("empty directory with spaces"),
 D("пустаяПапакаСКириллицейВНазвании"),
 D("soldFiles",
   F("bigUnalignedFile", (123 << 19) + 123),
   F("bigFile", 123 << 20),
   F("smallFile", 123)
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

    root = FSTestDir("test1", dcp(baseFS))
    updateFS(root, verbose = verbose)

    root = FSTestDir("test2", dcp(baseFS))
    updateFS(root, verbose = verbose)
