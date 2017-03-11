#!/usr/bin/python

# imports below

TK_IMPORT = "Tk, TclError, Label, Frame"
TTK_IMPORT = "Treeview, Notebook"

from sys import \
    version_info

if version_info > (3,):
    # Python 3
    xrange = range
    long = int
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
    split, \
    join, \
    isfile, \
    isdir

from os import \
    O_NONBLOCK, \
    listdir

from enum import \
    Enum

from itertools import \
    combinations, \
    count

from argparse import \
    ArgumentParser

from hashlib import \
    sha1

from fcntl import \
    F_SETFL, \
    fcntl

# Actual program below
# ====================

# TODO: implement one for Windows
def openNoBlock(*args):
    f = open(*args)
    fd = f.fileno()
    fcntl(fd, F_SETFL, O_NONBLOCK)
    return f

# Coroutine API
# -------------

class Yield(Enum):
    WAIT = False
    READY = True
    LONG_WAIT = 2

# Simulatenous dispatching is not allowd. Hence, current dispatcher may declare
# itself globally.
coDisp = None

CO_LIMIT = 10
class CoDisp(object):
    def __init__(self):
        self.gotten = 0
        self.queue = []
        self.ready = []
        self.waiting = []
        self.longWaiting = []

    def enqueue(self, co):
        self.queue.append(co)

    def iterate(self):
        r = self.ready
        q = self.queue
        w = self.waiting
        g = self.gotten
        lw = self.longWaiting

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
                        try:
                            co = lw.pop(0)
                        except IndexError:
                            return False
                        else:
                            g += 1
                            self.gotten = g
                else:
                    g += 1
                    self.gotten = g
            else:
                co = w.pop(0)

        global coDisp
        coDisp = self

        try:
            ret = next(co)
        except StopIteration:
            g -= 1
            self.gotten = g

            coDisp = None
            return bool(r or q)
        else:
            coDisp = None

        if ret == True:
            r.append(co)
            return True

        if ret == Yield.LONG_WAIT:
            g -= 1
            self.gotten = g
            lw.append(co)
            return bool(r or q)

        w.append(co)
        return bool(r or q)

class EventContext(object):
    # TODO: turn events to coroutine-based signals
    # TODO: add listener removing method
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
    FILE_SIZE_GOT
    FILE_SIZE_ERROR
    FILE_BLOCKS_GOT
    FILE_BLOCKS_ERROR
    DIRECTORY_SCANNED
""")

class FS(object):
    def __init__(self, root):
        self.root = root
        self.eCtx = EventContext()

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

# File CheckSum Block Size
FCSBS = 4 << 10 # 4 KiB

class FileInfo(FSNode):
    def coGetModify(self):
        p = Popen(["stat", "-c", "%y", self.ep],
            stdout = PIPE,
            stderr = PIPE
        )

        while p.poll() is None:
            yield False

        if p.returncode != 0:
            self.fs.eCtx.notify(FSEvent.FILE_MODIFY_ERROR, self,
                returncode = p.returncode,
                popen = p
            )
        else:
            self.modify = p.communicate()[0].decode("utf-8").strip()
            self.fs.eCtx.notify(FSEvent.FILE_MODIFY_GOT, self)

    def coGetSize(self):
        p = Popen(["stat", "-c", "%s", self.ep],
            stdout = PIPE,
            stderr = PIPE
        )

        while p.poll() is None:
            yield False

        if p.returncode != 0:
            self.fs.eCtx.notify(FSEvent.FILE_SIZE_ERROR, self,
                returncode = p.returncode,
                popen = p
            )
        else:
            self.size = long(p.communicate()[0])
            self.fs.eCtx.notify(FSEvent.FILE_SIZE_GOT, self)

    def coGetBlocks(self):
        while True:
            try:
                restFile = self.size
            except AttributeError:
                self.requestAttribute("size", coDisp)
                yield Yield.LONG_WAIT
            else:
                break

        f = openNoBlock(self.ep, "rb", FCSBS << 2)
        yield True

        blocks = []

        while restFile:
            block = b''
            rest = min(FCSBS, restFile)

            while rest:
                readedBytes = f.read(rest)
                readedLen = len(readedBytes)
                block = block + readedBytes

                assert readedLen <= rest

                if readedLen < rest:
                    yield False

                rest -= readedLen

            restFile -= len(block)

            yield True

            sha = sha1()
            sha.update(block)
            digest = sha.digest()
            blocks.append(digest)

        yield True
        f.close()
        yield True

        self.blocks = tuple(blocks)

        self.fs.eCtx.notify(FSEvent.FILE_BLOCKS_GOT, self)

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
        skipped = 0

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
                self.fs.eCtx.notify(FSEvent.DIRECTORY_FOUND, n)
            elif isfile(ep):
                n = FileInfo(np, directory = self)
                files[np] = n
                self.fs.eCtx.notify(FSEvent.FILE_FOUND, n)
            else:
                self.fs.eCtx.notify(FSEvent.DIRECTORY_NODE_SKIPPED, self,
                    path = np
                )
                skipped += 1
                continue

            n._ep = ep
            nodes[np] = n

        self.files, self.dirs, self.nodes = files, dirs, nodes
        self.skipped = skipped
        self.fs.eCtx.notify(FSEvent.DIRECTORY_SCANNED, self)

    def coRecursiveReading(self):
        while True:
            try:
                dirs = self.dirs
            except AttributeError:
                self.requestAttribute("nodes", coDisp)
                yield Yield.LONG_WAIT
            else:
                break

        y = DIPY
        for d in dirs.values():
            if y <= 0:
                yield True
                y = DIPY
            else:
                y -= 1
            d.enqueueRecursiveReading(coDisp)

    def enqueueRecursiveReading(self, coDisp):
        coDisp.enqueue(self.coRecursiveReading())

# File system comparation API
# ---------------------------

class FSNoneNode(FSNode):
    """ FSNoneNode is used by comparation subsystem. """
    def __init__(self, directory):
        super(FSNoneNode, self).__init__(None,
            directory = directory
        )

# File System Comparation Event
FSCEvent = Enum("FSCEvent", """
    DIR_CMP_INFO
    FILE_CMP_INFO
    DIFF_DIR_SUBDIRS
    DIFF_DIR_FILES
    DIFF_FILES
""")

class FSNodeComparationInfo(object):
    def __init__(self, directoryPath, parent = None):
        if parent:
            self.p = parent

        self.dp = directoryPath

    # relative apth
    @property
    def rp(self):
        try:
            return self._rp
        except AttributeError:
            try:
                p = self.p
            except AttributeError:
                rp = self.dp
            else:
                rp = join(p.rp, self.dp)

            self._rp = rp
            return rp

    def __hash__(self):
        return hash(self.rp)

class DirectoryComparationInfo(FSNodeComparationInfo):
    def __init__(self, dirs, parent = None):
        # dirs order is sugnificant
        if parent is None:
            directoryPath = "root:"
        else:
            for d in dirs:
                if not isinstance(d, FSNoneNode):
                    directoryPath = d.dp
                    break

        super(DirectoryComparationInfo, self).__init__(directoryPath,
            parent = parent
        )

        self.dirs = dirs

        self.childFCI = 0
        self.childFCIDiff = 0
        self.childDCI = 0

        self.totalFCI = 0
        self.totalFCIDiff = 0
        self.totalDCI = 0

    def accountFCI(self, fci):
        if fci.p is self:
            self.childFCI += 1

        self.totalFCI += 1
        try:
            p = self.p
        except AttributeError:
            pass
        else:
            p.accountFCI(fci)

    def accountFCIDiff(self, fci):
        if fci.p is self:
            self.childFCIDiff += 1

        self.totalFCIDiff += 1
        try:
            p = self.p
        except AttributeError:
            pass
        else:
            p.accountFCIDiff(fci)

    def accountDCI(self, dci):
        if dci.p is self:
            self.childDCI += 1

        self.totalDCI += 1
        try:
            p = self.p
        except AttributeError:
            pass
        else:
            p.accountDCI(dci)

class FileComparationInfo(FSNodeComparationInfo):
    attrs = (
        "modify",
        "size",
        "blocks"
    )

    def __init__(self, files, parent):
        # files order is sugnificant
        for f in files:
            if not isinstance(f, FSNoneNode):
                directoryPath = f.dp
                break

        super(FileComparationInfo, self).__init__(directoryPath,
            parent = parent
        )

        self.files = files
        pairs = self.pairs = tuple(combinations(files, 2))

        m = self.mesh = {}
        for f in files:
            m[f] = {f: {}}

        for f1, f2 in pairs:
            m[f2][f1] = m[f1][f2] = {}

    def coCompare(self, ctx):
        eCtx = ctx.eCtx
        pairs = self.pairs
        m = self.mesh

        attrs = FileComparationInfo.attrs

        for f1, f2 in pairs:
            if isinstance(f1, FSNoneNode) or isinstance(f2, FSNoneNode):
                continue

            for attr in attrs:
                yield True

                while True:
                    try:
                        a1 = getattr(f1, attr)
                    except AttributeError:
                        f1.requestAttribute(attr, coDisp)
                        yield Yield.LONG_WAIT
                    else:
                        break

                while True:
                    try:
                        a2 = getattr(f2, attr)
                    except AttributeError:
                        f2.requestAttribute(attr, coDisp)
                        yield Yield.LONG_WAIT
                    else:
                        break

                m[f1][f2][attr] = (a1 == a2)

        for f1, f2 in pairs:
            yield True

            for attr in attrs:
                if not m[f1][f2][attr]:
                    break
            else:
                continue
            break
        else:
            raise StopIteration()

        self.p.accountFCIDiff(self)
        eCtx.notify(FSCEvent.DIFF_FILES, self)

class RootComparationContext(object):
    def __init__(self, roots, eCtx):
        self.roots = set(roots)
        self.eCtx = eCtx

    def coCompare(self):
        attrs = FileComparationInfo.attrs

        queue = []

        roots = list(self.roots)
        self.rootDci = dci = self.emitDirectoryComparationInfo(roots)

        queue.append(dci)

        while queue:
            curDci = queue.pop(0)
            cur = curDci.dirs

            # queue subdirectories
            dirSummary = set()

            # d = Directory
            for d in cur:
                if not isinstance(d, FSNoneNode):
                    while True:
                        try:
                            dirs = d.dirs
                        except AttributeError:
                            d.requestAttribute("nodes", coDisp)
                            yield Yield.LONG_WAIT
                        else:
                            break

                    dirSummary.update(dirs.keys())

            yield True

            if dirSummary:
                for dn in dirSummary:
                    sameDirs = []

                    for d in cur:
                        if isinstance(d, FSNoneNode):
                            subDir = FSNoneNode(d)
                        else:
                            try:
                                subDir = d.dirs[dn]
                            except KeyError:
                                subDir = FSNoneNode(d)

                        sameDirs.append(subDir)

                    newDci = self.emitDirectoryComparationInfo(sameDirs,
                        curDci
                    )
                    queue.append(newDci)

                    yield True

            # queue files
            fileSummary = set()

            for d in cur:
                if not isinstance(d, FSNoneNode):
                    fileSummary.update(d.files.keys())

            yield True

            if fileSummary:
                for fn in fileSummary:
                    sameFiles = []
                    entries = 0

                    for d in cur:
                        if isinstance(d, FSNoneNode):
                            file = FSNoneNode(d)
                        else:
                            try:
                                file = d.files[fn]
                            except KeyError:
                                file = FSNoneNode(d)
                            else:
                                entries += 1

                        sameFiles.append(file)

                    fci = self.emitFileComparationInfo(sameFiles, curDci)

                    if entries == 1:
                        # Only request attributes of alone file entry
                        for oneFile in sameFiles:
                            if not isinstance(oneFile, FSNoneNode):
                                break

                        for attr in attrs:
                            if not attr in oneFile.__dict__:
                                oneFile.requestAttribute(attr, coDisp)
                    else:
                        coDisp.enqueue(fci.coCompare(self))

                    yield True

    def emitDirectoryComparationInfo(self, dirs, parent = None):
        dci = DirectoryComparationInfo(dirs, parent)
        if parent:
            parent.accountDCI(dci)
        self.eCtx.notify(FSCEvent.DIR_CMP_INFO, dci)
        return dci

    def emitFileComparationInfo(self, files, parent):
        fci = FileComparationInfo(files, parent)
        parent.accountFCI(fci)
        self.eCtx.notify(FSCEvent.FILE_CMP_INFO, fci)
        return fci

# Widgets
# -------

FILE_PENDING = "..."
DIRECTORY_PENDING = "[...]"
UNKNOWN_ENTRY = "?"

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

        eCtx = rootDir.fs.eCtx
        eCtx.listen(self.onFileFound, FSEvent.FILE_FOUND)
        eCtx.listen(self.onDirectoryFound, FSEvent.DIRECTORY_FOUND)
        eCtx.listen(self.onFileTSReaded, FSEvent.FILE_MODIFY_GOT)
        eCtx.listen(self.onFileTSReadError, FSEvent.FILE_MODIFY_ERROR)
        eCtx.listen(self.onDirectoryNodeSkipped,
            FSEvent.DIRECTORY_NODE_SKIPPED
        )
        eCtx.listen(self.onDirectoryScanned, FSEvent.DIRECTORY_SCANNED)

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
            values = [ FILE_PENDING ]
        )

    def onDirectoryNodeSkipped(self, e, di, path):
        parent = self.fsn2iid[di]
        iid = self.genIID(path)

        self.insert(parent, "end",
            iid = iid,
            text = path,
            values = [ UNKNOWN_ENTRY ]
        )

    def onFileTSReaded(self, e, fi):
        self.item(self.fsn2iid[fi], values = [fi.modify])

    def onFileTSReadError(self, e, fi, returncode, popen):
        self.item(self.fsn2iid[fi], values = ["!: %d" % returncode])

    def onDirectoryFound(self, e, di):
        _open = False
        try:
            parent = self.fsn2iid[di.d]
        except AttributeError:
            parent = ""
            _open = True
        iid = self.genIID(di)

        self.insert(parent, "end",
            iid = iid,
            text = di.dp,
            values = [ DIRECTORY_PENDING ],
            open = _open
        )

    def onDirectoryScanned(self, event, di):
        skipped = di.skipped
        text = "F: %u D: %u%s" % (
            len(di.files), len(di.dirs), (" ?: %u" % skipped if skipped else "")
        )
        self.item(self.fsn2iid[di], values = [text])

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

        eCtx = rootDir.fs.eCtx
        eCtx.listen(self.onFileFound, FSEvent.FILE_FOUND)
        eCtx.listen(self.onDirectoryFound, FSEvent.DIRECTORY_FOUND)
        eCtx.listen(self.onFileTSReaded, FSEvent.FILE_MODIFY_GOT)
        eCtx.listen(self.onFileTSReadError, FSEvent.FILE_MODIFY_ERROR)
        eCtx.listen(self.onDirectoryNodeSkipped,
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

        self.rowconfigure(1, weight = 0)
        self.statusBar = l = Label(self)
        l.grid(row = 1, column = 0,
            columns = 1, # all
            sticky = "SW"
        )

    def iterateCoroutines(self):
        coDisp = self.coDisp

        i = CIPMLI
        while i > 0 and coDisp.iterate():
            i -= 1

        l = self.statusBar
        l.config(text = "Tasks: %u + %u(W) = %u | %u + %u(LW)" % (
            len(coDisp.ready),
            len(coDisp.waiting),
            coDisp.gotten,
            len(coDisp.queue),
            len(coDisp.longWaiting)
        ))

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

