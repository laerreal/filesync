#!/usr/bin/python

# imports below

TK_IMPORT = "Tk, TclError, Label"
TTK_IMPORT = "Treeview"

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
from importlib import \
    import_module

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

listeners = {}

def notify(event, *args, **kw):
    try:
        ls = listeners[event]
    except KeyError:
        return

    for l in ls:
        l(event, *args, **kw)

def listen(cb, *events):
    for e in events:
        try:
            ls = listeners[e]
        except KeyError:
            listeners[e] = ls = set()

        ls.add(cb)

FSEvent = Enum("Events", """
    DIRECTORY_FOUND
    FILE_TS_READED
    DIRECTORY_NODE_SKIPPED
    FILE_TS_READ_ERROR
    FILE_FOUND
""")


# Actual program below

class FileTSGettingError(Exception):
    pass

class FSNode(object):
    def __init__(self, directoryPath, directory = None):
        self.dp = directoryPath
        if directory:
            self.d = directory

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

class FileInfo(FSNode):
    def coGetFileTS(self):
        p = Popen(["stat", "-c", "%y", self.ep],
            stdout = PIPE,
            stderr = PIPE
        )

        while p.poll() is None:
            yield False

        if p.returncode != 0:
            notify(FSEvent.FILE_TS_READ_ERROR, self,
                returncode = p.returncode,
                popen = p
            )
        else:
            self.modify = p.communicate()[0].decode("utf-8").strip()
            notify(FSEvent.FILE_TS_READED, self)

# Directory Items Per Yield
DIPY = 100

class DirectoryInfo(FSNode):
    def coRead(self):
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
                notify(FSEvent.DIRECTORY_FOUND, n)
            elif isfile(ep):
                n = FileInfo(np, directory = self)
                files[np] = n
                notify(FSEvent.FILE_FOUND, n)
            else:
                notify(FSEvent.DIRECTORY_NODE_SKIPPED, self, path = np)
                continue

            n._ep = ep
            nodes[np] = n

        self.files, self.dirs, self.nodes = files, dirs, nodes

    def coRecursiveReading(self, coDisp):
        y = DIPY
        for f in self.files.values():
            if y <= 0:
                yield True
                y = DIPY
            else:
                y -= 1
            coDisp.enqueue(f.coGetFileTS())
        for d in self.dirs.values():
            if y <= 0:
                yield True
                y = DIPY
            else:
                y -= 4 # different price
                d.enqueueRecursiveReading(coDisp)

    def enqueueRecursiveReading(self, coDisp):
        dirPipe = CoPipe()
        dirPipe.append(self.coRead())
        dirPipe.append(self.coRecursiveReading(coDisp))
        coDisp.enqueue(dirPipe.coRun())

class CoPipe(object):
    queue = []

    def append(self, co):
        self.queue.append(co)

    def coRun(self):
        while True:
            try:
                current = self.queue.pop(0)
            except IndexError:
                break # StopIteration
            else:
                while True:
                    try:
                        res = next(current)
                    except StopIteration:
                        break
                    else:
                        yield res

CO_LIMIT = 10
class CoDisp(object):
    gotten = 0
    queue = []
    ready = []
    waiting = []

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

        if ret:
            r.append(co)
            return True

        w.append(co)
        return bool(r or q)

def iidGenerator():
    c = count(0)
    while True:
        yield str(next(c))

class FileTree(Treeview):
    iidGen = iidGenerator()

    def __init__(self, parent, rootDir, *args, **kw):
        kw["columns"] = ("info")
        Treeview.__init__(self, parent, *args, **kw)

        self.column("#0", width = 25)
        self.heading("#0", text = "Name")
        self.heading("info", text = "Information")

        listen(self.onFileFound, FSEvent.FILE_FOUND)
        listen(self.onDirectoryFound, FSEvent.DIRECTORY_FOUND)
        listen(self.onFileTSReaded, FSEvent.FILE_TS_READED)
        listen(self.onFileTSReadError, FSEvent.FILE_TS_READ_ERROR)
        listen(self.onDirectoryNodeSkipped, FSEvent.DIRECTORY_NODE_SKIPPED)

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

# Coroutine Iterations Per Main Loop Iteration
CIPMLI = 10

class MainWindow(Tk):
    coDisp = CoDisp()

    def __init__(self, effectiveRootDirectoryName):
        Tk.__init__(self)

        self.rootDir = rootDir = DirectoryInfo(effectiveRootDirectoryName)
        rootDir.enqueueRecursiveReading(self.coDisp)

        self.grid()
        self.rowconfigure(0, weight=1)
        self.columnconfigure(0, weight=1)

        FileTree(self, rootDir).grid(row = 0, column = 0, sticky="NESW")

        self.rowconfigure(1, weight=0)
        self.statusBar = l = Label(self)
        l.grid(
            row = 1,
            column = 0,
            columns = 1, # all
            sticky = "SW"
        )

        self.totalNodes = 1
        self.totalDirectories = 1
        self.totalTSReaded = 0
        self.totalFiles = 0
        self.totalReadErrors = 0

        listen(self.onFileFound, FSEvent.FILE_FOUND)
        listen(self.onDirectoryFound, FSEvent.DIRECTORY_FOUND)
        listen(self.onFileTSReaded, FSEvent.FILE_TS_READED)
        listen(self.onFileTSReadError, FSEvent.FILE_TS_READ_ERROR)
        listen(self.onDirectoryNodeSkipped, FSEvent.DIRECTORY_NODE_SKIPPED)

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

if __name__ == "__main__":
    print("Re@l file mirrorer")

    root = MainWindow("/media/data/Docs/Game saves/")
    root.geometry("1024x760")
    root.mainloop()

