#!/usr/bin/python

# imports below

TK_IMPORT = "Tk, TclError, Label, Frame"
TTK_IMPORT = "Treeview, Notebook"

try:
    xrange
except NameError:
    # Python 3
    xrange = range
    exec("from tkinter import " + TK_IMPORT)
    exec("from tkinter.ttk import " + TTK_IMPORT)
else:
    # Python 2
    exec("from Tkinter import " + TK_IMPORT)
    exec("from ttk import " + TTK_IMPORT)

# Any python

from subprocess import \
    Popen, \
    PIPE

from os.path import \
    join, \
    isfile, \
    isdir

from os import \
    listdir

from enum import \
    Enum

from itertools import \
    count

from argparse import \
    ArgumentParser

# Actual program below
# ====================

# Coroutine API
# -------------

class Yield(Enum):
    WAIT = False
    READY = True
    LONG_WAIT = 2

CO_LIMIT = 10
class CoDisp(object):
    def __init__(self):
        self.gotten = 0
        self.queue = []
        self.ready = []
        self.waiting = []

    def enqueue(self, co):
        self.queue.append(co)

    def iterate(self):
        r = self.ready
        q = self.queue
        w = self.waiting
        g = self.gotten

        try:
            co = r.pop(0)
        except IndexError:
            if g < CO_LIMIT:
                try:
                    co = q.pop(0)
                except IndexError:
                    try:
                        co = w.pop(0)
                    except IndexError:
                        return False
                else:
                    g += 1
                    self.gotten = g
            else:
                co = w.pop(0)

        try:
            ret = next(co)
        except StopIteration:
            g -= 1
            self.gotten = g
            return bool(r or q)

        if ret == True:
            r.append(co)
            return True

        if ret == Yield.LONG_WAIT:
            g -= 1
            self.gotten = g
            q.append(co)
            return bool(r or q) # This is not quite correct

        w.append(co)
        return bool(r or q)

class CoroutineContext(object):
    def __init__(self):
        self.listeners = {}

    def notify(self, event, *args, **kw):
        try:
            ls = self.listeners[event]
        except KeyError:
            return

        for l in ls:
            l(event, *args, **kw)

    def listen(self, cb, *events):
        allLs = self.listeners
        for e in events:
            try:
                ls = allLs[e]
            except KeyError:
                allLs[e] = ls = set()

            ls.add(cb)

# File system model
# -----------------

FSEvent = Enum("Events", """
    DIRECTORY_FOUND
    FILE_MODIFY_GOT
    DIRECTORY_NODE_SKIPPED
    FILE_MODIFY_ERROR
    FILE_FOUND
""")

class FS(object):
    def __init__(self, root):
        self.root = root
        self.coCtx = CoroutineContext()

class FileTSGettingError(Exception):
    pass

class FSNode(object):
    def __init__(self, directoryPath, directory = None):
        self.dp = directoryPath
        if directory:
            self.d = directory
            self.fs = directory.fs
        else:
            self.fs = FS(self)

        self.req = set()

    @property
    def ep(self):
        try:
            return self._ep
        except AttributeError:
            try:
                d = self.d
            except AttributeError:
                ep = self.dp
            else:
                ep = join(d.ep, self.dp)
            self._ep = ep
            return ep

    def requestAttribute(self, attr, coDisp):
        assert attr not in self.__dict__, \
            "Attempt to request available attribute " + attr

        req = self.req

        if attr in req:
            # already requested
            return

        coName = "coGet" + attr.title()
        coFn = getattr(self, coName)
        co = coFn()
        coDisp.enqueue(co)
        req.add(attr)

class FileInfo(FSNode):
    def coGetModify(self):
        p = Popen(["stat", "-c", "%y", self.ep],
            stdout = PIPE,
            stderr = PIPE
        )

        while p.poll() is None:
            yield False

        if p.returncode != 0:
            self.fs.coCtx.notify(FSEvent.FILE_MODIFY_ERROR, self,
                returncode = p.returncode,
                popen = p
            )
        else:
            self.modify = p.communicate()[0].decode("utf-8").strip()
            self.fs.coCtx.notify(FSEvent.FILE_MODIFY_GOT, self)

# Directory Items Per Yield
DIPY = 100

class DirectoryInfo(FSNode):
    def coGetNodes(self):
        # node pathes
        nps = listdir(self.ep)

        yield True

        files = {}
        dirs = {}
        nodes = {}

        y = DIPY
        for np in nps:
            if y <= 0:
                yield True
                y = DIPY
            else:
                y -= 1

            ep = join(self.ep, np)
            if isdir(ep):
                n = DirectoryInfo(np, directory = self)
                dirs[np] = n
                self.fs.coCtx.notify(FSEvent.DIRECTORY_FOUND, n)
            elif isfile(ep):
                n = FileInfo(np, directory = self)
                files[np] = n
                self.fs.coCtx.notify(FSEvent.FILE_FOUND, n)
            else:
                self.fs.coCtx.notify(FSEvent.DIRECTORY_NODE_SKIPPED, self,
                    path = np
                )
                continue

            n._ep = ep
            nodes[np] = n

        self.files, self.dirs, self.nodes = files, dirs, nodes

    def coRecursiveReading(self, coDisp):
        while True:
            try:
                dirs = self.dirs
            except AttributeError:
                self.requestAttribute("nodes", coDisp)
                yield Yield.LONG_WAIT
            else:
                break

        y = DIPY
        for f in self.files.values():
            if y <= 0:
                yield True
                y = DIPY
            else:
                y -= 1
            f.requestAttribute("modify", coDisp)
        for d in dirs.values():
            if y <= 0:
                yield True
                y = DIPY
            else:
                y -= 1
            d.enqueueRecursiveReading(coDisp)

    def enqueueRecursiveReading(self, coDisp):
        coDisp.enqueue(self.coRecursiveReading(coDisp))

# Widgets
# -------

def iidGenerator():
    c = count(0)
    while True:
        yield str(next(c))

class FileTree(Treeview):
    def __init__(self, parent, rootDir, *args, **kw):
        kw["columns"] = ("info")
        Treeview.__init__(self, parent, *args, **kw)

        self.column("#0", width = 25)
        self.heading("#0", text = "Name")
        self.heading("info", text = "Information")

        self.iidGen = iidGenerator()

        coCtx = rootDir.fs.coCtx
        coCtx.listen(self.onFileFound, FSEvent.FILE_FOUND)
        coCtx.listen(self.onDirectoryFound, FSEvent.DIRECTORY_FOUND)
        coCtx.listen(self.onFileTSReaded, FSEvent.FILE_MODIFY_GOT)
        coCtx.listen(self.onFileTSReadError, FSEvent.FILE_MODIFY_ERROR)
        coCtx.listen(self.onDirectoryNodeSkipped,
            FSEvent.DIRECTORY_NODE_SKIPPED
        )

        # File system node to iid
        self.fsn2iid = {
            rootDir : ""
        }
        self.onDirectoryFound(FSEvent.DIRECTORY_FOUND, rootDir)

    def genIID(self, fsn):
        iid = next(self.iidGen)
        self.fsn2iid[fsn] = iid
        return iid

    def onFileFound(self, e, fi):
        parent = self.fsn2iid[fi.d]
        iid = self.genIID(fi)

        self.insert(parent, "end",
            iid = iid,
            text = fi.dp,
            values = ("?")
        )

    def onDirectoryNodeSkipped(self, e, di, path):
        parent = self.fsn2iid[di]
        iid = self.genIID(path)

        self.insert(parent, "end",
            iid = iid,
            text = path,
            values = ("unknown")
        )

    def onFileTSReaded(self, e, fi):
        self.item(self.fsn2iid[fi], values = (fi.modify,))

    def onFileTSReadError(self, e, fi, returncode, popen):
        self.item(self.fsn2iid[fi], values = ("!: %d" % returncode))

    def onDirectoryFound(self, e, di):
        try:
            parent = self.fsn2iid[di.d]
        except AttributeError:
            parent = ""
        iid = self.genIID(di)

        self.insert(parent, "end",
            iid = iid,
            text = di.dp,
            values = ("...")
        )

class RootInfo(Frame):
    def __init__(self, parent, rootDir, coDisp):
        Frame.__init__(self, parent)

        self.grid()
        self.rowconfigure(0, weight=1)
        self.columnconfigure(0, weight=1)

        rootDir.enqueueRecursiveReading(coDisp)

        ft = FileTree(self, rootDir)
        ft.grid(row = 0, column = 0, sticky="NESW")

        self.rowconfigure(1, weight=0)
        self.statusBar = l = Label(self)
        l.grid(
            row = 1,
            column = 0,
            columns = 1, # all
            sticky = "SW"
        )

        coCtx = rootDir.fs.coCtx
        coCtx.listen(self.onFileFound, FSEvent.FILE_FOUND)
        coCtx.listen(self.onDirectoryFound, FSEvent.DIRECTORY_FOUND)
        coCtx.listen(self.onFileTSReaded, FSEvent.FILE_MODIFY_GOT)
        coCtx.listen(self.onFileTSReadError, FSEvent.FILE_MODIFY_ERROR)
        coCtx.listen(self.onDirectoryNodeSkipped,
            FSEvent.DIRECTORY_NODE_SKIPPED
        )

        self.totalNodes = 1
        self.totalDirectories = 1
        self.totalTSReaded = 0
        self.totalFiles = 0
        self.totalReadErrors = 0

    def onFileFound(self, *a, **kw):
        self.totalFiles += 1
        self.totalNodes += 1
        self.updateStatusBar()

    def onDirectoryFound(self, *a, **kw):
        self.totalDirectories += 1
        self.totalNodes += 1
        self.updateStatusBar()

    def onDirectoryNodeSkipped(self, *a, **kw):
        self.totalNodes += 1
        self.updateStatusBar()

    def onFileTSReaded(self, *a, **kw):
        self.totalTSReaded += 1
        self.updateStatusBar()

    def onFileTSReadError(self, *a, **kw):
        self.totalReadErrors += 1
        self.updateStatusBar()

    def updateStatusBar(self):
        self.statusBar.config(
            text = "N: %u, D: %u, F: %u/%u (e: %u)" % (
                self.totalNodes,
                self.totalDirectories,
                self.totalTSReaded,
                self.totalFiles,
                self.totalReadErrors
            )
        )

# Coroutine Iterations Per Main Loop Iteration
CIPMLI = 10

class MainWindow(Tk):
    def __init__(self, rootDirectoryEffectiveNames):
        Tk.__init__(self)

        coDisp = self.coDisp = CoDisp()

        self.grid()
        self.rowconfigure(0, weight=1)
        self.columnconfigure(0, weight=1)

        nbRoots = Notebook(self)
        nbRoots.grid(row = 0, column = 0, sticky = "NESW")

        for rden in rootDirectoryEffectiveNames:
            rootDir = DirectoryInfo(rden)
            ri = RootInfo(self, rootDir, coDisp)
            nbRoots.add(ri, text = rden)

    def iterateCoroutines(self):
        i = CIPMLI
        while i > 0 and self.coDisp.iterate():
            i -= 1

    def mainloop(self):
        try:
            while True:
                self.update_idletasks()
                self.update()
                self.iterateCoroutines()
        except TclError:
            pass

# Main program
# ------------

if __name__ == "__main__":
    ap = ArgumentParser(description = "Re@l file syncronization tool.")
    ap.add_argument('roots',
        metavar = "D",
        type = str,
        nargs = "*",
        help = "A root directory to syncronize",
        default = "."
    )

    args = ap.parse_args()

    root = MainWindow(args.roots)
    root.title(ap.description)
    root.geometry("1024x760")
    root.mainloop()

