#!/usr/bin/python

"""
Debug messages switching:

Find                    : (# )?(print[^#]+\) *#.*)
To turn on replace with : \2
To turn off replace with: # \2
"""

# imports below

TK_IMPORT = "Tk, TclError, Label, Frame"
TTK_IMPORT = "Treeview, Notebook"

from sys import version_info

if version_info > (3,):
    # Python 3
    xrange = range
    long = int
    exec("from tkinter import " + TK_IMPORT)
    exec("from tkinter.ttk import " + TTK_IMPORT)

    def decode_str(bytes):
        return bytes.decode("utf-8")

    from pickle import loads, dumps
else:
    # Python 2
    exec("from Tkinter import " + TK_IMPORT)
    exec("from ttk import " + TTK_IMPORT)

    def decode_str(bytes):
        return str(bytes)

    from cPickle import loads, dumps

# Any python
from types import GeneratorType
from subprocess import (
    Popen,
    PIPE
)
from os.path import (
    getsize,
    getctime,
    split,
    join,
    isfile,
    isdir
)
from os import (
    name as os_name,
    listdir
)

if os_name != "nt":
    from os import O_NONBLOCK

    from fcntl import (
        F_SETFL,
        fcntl
    )

from itertools import (
    combinations,
    count
)
from argparse import ArgumentParser
from hashlib import sha1
from socket import (
    ntohl,
    htonl,
    socket,
    AF_INET,
    SOCK_STREAM
)
from select import select
from time import sleep
from traceback import format_exc
from multiprocessing import (
    Process,
    Queue
)
from queue import Empty
from common import (
    Stateful,
    bytes2int, int2bytes
)

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
# Simulatenous dispatching is not allowd. Hence, current dispatcher may declare
# itself globally.
coDisp = None

CO_LIMIT = 40
class CoDisp(object):
    def __init__(self):
        self.gotten = 0
        self.queue = []
        self.ready = []
        self.waiting = []
        self.callers = set()
        self.references = {}
        self.socketsToRead = {}
        self.socketsToWrite = {}
        self.readySockets = []
        self.desc = {}

    def wake(self, co):
        self.waiting.remove(co)
        self.ready.append(co)

    def enqueue(self, co):
        self.queue.append(co)

    def select(self, timeout):
        s2r = self.socketsToRead
        s2w = self.socketsToWrite
        rs = self.readySockets

        if not (s2r or s2w):
            return False

        # Readt To Read(Write)
        r2r, r2w = select(s2r.keys(), s2w.keys(), [], timeout)[:2]

        for r in r2r:
            rs.append((s2r.pop(r), False))

        for w in r2w:
            rs.append((s2w.pop(w), False))

        if s2r:
            exceptions = select([], [], s2r.keys(), 0)[2]
            for r in exceptions:
                rs.append((s2r.pop(r), True))

        if s2w:
            exceptions = select([], [], s2w.keys(), 0)[2]
            for w in exceptions:
                rs.append((s2w.pop(w), True))

        return True

    """ An iteration contains
    - either 1 ready task
    - or 1 ready socket
    - or 1 new task from queue
    - or polling of all waiting tasks at the beginning of the iteration untill
      a waiting task becomes ready (execution of this ready task is part of the
      iteration too).
    """
    def iteration(self):
        r = self.ready
        try:
            yield r.pop(0), None
        except IndexError:
            rs = self.readySockets
            try:
                yield rs.pop(0)
            except IndexError:
                g = self.gotten
                if g < CO_LIMIT:
                    try:
                        res = self.queue.pop(0), None
                    except IndexError:
                        pass
                    else:
                        g += 1
                        self.gotten = g
                        yield res
                        return

                w = self.waiting
                for co in list(w):
                    w.remove(co)

                    yield co, None

                    # a task can be waked up
                    try:
                        yield r.pop(0), None
                    except IndexError:
                        continue

                    break

    def iterate(self):
        r = self.ready
        q = self.queue
        w = self.waiting
        c = self.callers
        refs = self.references
        s2r = self.socketsToRead
        s2w = self.socketsToWrite

        global coDisp

        for co, sockErr in self.iteration():
            coDisp = self
            try:
                ret = co.send(sockErr)
            except StopIteration:
                coDisp = None

                self.desc.pop(co, None)

                try:
                    coRefs = refs[co]
                except KeyError:
                    self.gotten -= 1
                    return True
                else:
                    del refs[co]

                g = self.gotten - 1
                for caller in coRefs:
                    c.remove(caller)
                    if g < CO_LIMIT:
                        g += 1
                        r.insert(0, caller)
                    else:
                        q.insert(0, caller)
                self.gotten = g

                return True
            else:
                coDisp = None

            if isinstance(ret, GeneratorType):
                c.add(co)

                try:
                    coRefs = refs[ret]
                except KeyError:
                    refs[ret] = [co]
                else:
                    coRefs.append(co)

                if ret in c:
                    self.gotten -= 1
                else:
                    r.append(ret)

                return True
            elif isinstance(ret, tuple):
                sock = ret[0]
                waitList = s2w if ret[1] else s2r

                waitList[sock] = co

                return True
            elif ret:
                r.append(co)
                return True

            w.append(co)

        return False

class EventContext(object):
    # TODO: turn events to coroutine-based signals
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

    def forget(self, cb, *events):
        allLs = self.listeners

        for e in events:
            ls = allLs[e]
            ls.remove(cb)

# Networking
# ==========

MSG_MIN_LENGTH = 16
MSG_STR_LENGTH = 60

@Stateful("append", "str")
class Message(object):
    def __init__(self, data = None):
        if data is None:
            self.chunk = b""
            self.rest = MSG_MIN_LENGTH
            self.state = "RecvLen"
        else:
            fullLength = len(data) + 4
            extra = MSG_MIN_LENGTH - fullLength
            if extra > 0:
                data += b" " * extra
                fullLength = MSG_MIN_LENGTH

            self.chunk = int2bytes(htonl(fullLength), 4) + data

            self.rest = fullLength
            self.state = "Send"

    def __str__(self):
        return self.str()

    def strRecvLen(self):
        return "? >> %u [M ?]" % len(self.chunk)

    def strRecvData(self):
        chunkLength = len(self.chunk)
        rest = self.rest

        return "%u >> %u [M %u]" % (
            rest,
            chunkLength,
            chunkLength + rest
        )

    def strReceived(self):
        chunkLength = len(self.chunk)

        if chunkLength > MSG_STR_LENGTH:
            return "[M %u] %s..." % (
                chunkLength,
                str(self.chunk[4:MSG_STR_LENGTH])
            )
        else:
            return "[M %u] %s" % (
                chunkLength,
                str(self.chunk[4:])
            )

    def strSend(self):
        return "<< %u [M]" % len(self.chunk)

    def appendCommon(self, ch):
        self.rest -= len(ch)
        ch = self.chunk + ch
        self.chunk = ch

    def appendRecvLen(self, ch):
        self.appendCommon(ch)
        if len(ch) >= 4:
            fullLength = ntohl(bytes2int(ch[:4]))
            rest = self.rest + fullLength - MSG_MIN_LENGTH
            if rest > 0:
                self.state = "RecvData"
            else:
                self.state = "Received"
                self.finalize()
            self.rest = rest

    def appendRecvData(self, ch):
        self.appendCommon(ch)
        if self.rest == 0:
            self.state = "Received"
            self.finalize()

    def finalize(self):
        raw = self.chunk[4:]
        self._type, self.content = raw.split(b"(", 1)

    def appendSend(self, ch):
        raise RuntimeError("Cannot append chunk during sending.")

class AuthMessage(Message):
    def __init__(self):
        super(AuthMessage, self).__init__(b"auth(")

class FSMessage(Message):
    def __init__(self, rootDirectoryEffectiveName):
        msg = "FS(" + rootDirectoryEffectiveName
        super(FSMessage, self).__init__(msg.encode("utf-8"))

class GetAttrMessage(Message):
    def __init__(self, effectivePath, Attr):
        msg = "get(" + Attr + "(" + effectivePath
        super(GetAttrMessage, self).__init__(msg.encode("utf-8"))

class RetAttrMessage(Message):
    def __init__(self, effectivePath, Attr, value):
        msg = "ret(" + Attr + "(" + effectivePath
        super(RetAttrMessage, self).__init__(
            msg.encode("utf-8") + bytes(1) + value
        )

DEFAULT_PORT = 6655
CHUNK_SIZE = 4096

@Stateful(
    "handle_auth_",
    "handle_FS_",
    "handle_get_"
)
class ClientInfo(object):
    def __init__(self, server, sock):
        self.server = server
        self.sock = sock
        self.output = []
        self.outMsg = None
        self.state = "Auth"

    # TODO: exit sender and receiver
    def disconnected(self):
        pass

    def socketError(self):
        pass

    # node is list used to return value from coroutine
    def coLookUpNode(self, effectivePath, node):
        # look up node by effective path
        fs = self.fs
        root = fs.root
        sep = fs.sep
        rootDP, rp = effectivePath[:len(root.dp)], \
                     effectivePath[len(root.dp) + len(sep):]

        if rootDP != root.dp:
            raise RuntimeError("Client requested other root: %s" % rootDP)

        n = root
        if rp:
            for name in rp.split(sep):
                try:
                    nodes = n.nodes
                except AttributeError:
                    yield n.attributeGetter("nodes")
                    nodes = n.nodes

                try:
                    n = nodes[name]
                except KeyError:
                    raise RuntimeError("Client requested unexisting node '%s' \
in '%s'" % (name, n.ep)
                    )

        node.append(n)

    # Auth state
    def handle_auth_Auth(self, content):
        print("Authenticated") # net-0
        self.state = "FS"

    # FS state
    def handle_FS_FS(self, content):
        effectiveRootName = content.decode("utf-8")
        print("Preparing file system: " + effectiveRootName + " ... ", end="") # net-0
        self.fs = self.server.getFS(effectiveRootName)
        print("OK") # net-0
        self.state = "Work"

    # Work state function

    # ep -  Effective Path
    # TODO: use relative path
    def coGet(self, Attr, ep):
        node = []
        yield self.coLookUpNode(ep, node)
        n = node[0]

        # get requested attribute
        attr = Attr.lower()
        try:
            val = getattr(n, attr)
        except AttributeError:
            yield n.attributeGetter(attr)
            val = getattr(n, attr)

        val = dumps(val)

        self.output.append(RetAttrMessage(ep, Attr, val))

    def coGetNodes(self, ep):
        node = []
        yield self.coLookUpNode(ep, node)
        n = node[0]

        # get requested attribute
        try: (n.nodes)
        except AttributeError: yield n.attributeGetter("nodes")

        files = n.files
        dirs = n.dirs
        skipped = n.skipped

        total = skipped + len(files) + len(dirs)

        # print("Begin sending of nodes of '%s' to client" % n.ep) # net-1

        output = self.output

        output.extend([
            RetAttrMessage(ep, "Nodes", str(total).encode("utf-8")),
            RetAttrMessage(ep, "Skipped", str(skipped).encode("utf-8")),
        ])

        output.extend(RetAttrMessage(ep, "File", f.dp.encode("utf-8")) \
            for f in files.values()
        )

        output.extend(RetAttrMessage(ep, "Dir", d.dp.encode("utf-8")) \
            for d in dirs.values()
        )


    def handle_get_Work(self, content):
        attr, ep = content.split(b"(", 1)
        attr = decode_str(attr)
        ep = ep.decode("utf-8")

        # print("queue %s of %s" % (attr, ep)) # net-1
        if attr == "Nodes":
            self.server.coDisp.enqueue(self.coGetNodes(ep))
        else:
            self.server.coDisp.enqueue(self.coGet(attr, ep))

    def onMessage(self, inMsg):
        handler = decode_str(inMsg._type)
        getattr(self, "handle_" + handler + "_")(inMsg.content)

    def coReceiver(self):
        sock = self.sock
        inMsg = None

        while True:
            err = (yield (sock, False))

            if err:
                print("Client socket error raised during select.") # net-0
                try:
                    sock.close()
                except:
                    pass
                self.socketError()
                break

            if not inMsg:
                inMsg = Message()

            chunk = sock.recv(min(CHUNK_SIZE, inMsg.rest))
            if chunk == b"":
                print("Disconnected.") # net-0
                self.disconnected()
                break

            inMsg.append(chunk)

            # print(inMsg) # net-1

            if not inMsg.rest:
                self.onMessage(inMsg)
                inMsg = None

    def coSender(self):
        sock = self.sock
        outMsg = None
        outMsgs = self.output

        while True:
            if not outMsg:
                while not outMsgs:
                    yield False
                outMsg = outMsgs.pop(0)

            err = (yield (sock, True))

            if err:
                print("Client socket error raised during select.") # net-0
                try:
                    sock.close()
                except:
                    pass
                self.socketError()
                break

            rest = outMsg.rest
            toSend = min(CHUNK_SIZE, rest)
            chunk = outMsg.chunk
            sent = sock.send(chunk[:toSend])

            if sent == 0:
                print("Send returned 0.") # net-0
            elif sent == outMsg.rest:
                outMsg = None
            else:
                outMsg.chunk = chunk[sent:]
                outMsg.rest = rest - sent

class FSServer(object):
    def __init__(self, port = DEFAULT_PORT):
        self.port = port
        # File System Registry
        self.fsr = {}
        self.coDisp = CoDisp()

    def getFS(self, rootDirectoryEffectiveName):
        fsr = self.fsr
        try:
            return fsr[rootDirectoryEffectiveName]
        except KeyError:
            fs = newFS(rootDirectoryEffectiveName)
            fsr[rootDirectoryEffectiveName] = fs
            return fs

    def start(self):
        s = socket(AF_INET, SOCK_STREAM)
        s.setblocking(0)
        bindTo = ("127.0.0.1", self.port)

        print("Binding to %s:%u..." % bindTo, end = "") # net-0

        s.bind(bindTo)

        print(" OK\nListening starting... ", end = "") # net-0

        s.listen(5)

        print(" OK") # net-0

        # Listening Socket
        self.ls = s
        self.coDisp.enqueue(self.coAccept())

    def coAccept(self):
        ls = self.ls
        while True:
            err = yield ls, False

            if err:
                print("Listening socket error raised during select.") # net-0
                del self.ls
                try:
                    ls.close()
                except:
                    pass
                break

            (clientSocket, addr) = ls.accept()

            print("Incomming connection from %s:%u" % addr) # net-0

            clientSocket.setblocking(0)
            cl = ClientInfo(self, clientSocket)
            coDisp.enqueue(cl.coReceiver())
            coDisp.enqueue(cl.coSender())

# File system model
# -----------------

def newFS(rootDirectoryEffectiveName):
    pieces = rootDirectoryEffectiveName.split("::")
    if len(pieces) <= 1:
        if os_name == "nt":
            return WindowsFS(rootDirectoryEffectiveName)
        else:
            return LinuxFS(rootDirectoryEffectiveName)
    else:
        remote = pieces.pop(0)
        try:
            (remoteAddress, remotePort) = remote.split(":")
        except ValueError:
            remoteAddress = remote
            remotePort = DEFAULT_PORT
        else:
            remotePort = int(remotePort, 0)
        return RemoteFS(remoteAddress, remotePort, "::".join(pieces))

class FSEvent:
    class DIRECTORY_FOUND: pass
    class FILE_MODIFY_GOT: pass
    class DIRECTORY_NODE_SKIPPED: pass
    class FILE_MODIFY_ERROR: pass
    class FILE_FOUND: pass
    class FILE_SIZE_GOT: pass
    class FILE_SIZE_ERROR: pass
    class FILE_CHECKSUMS_GOT: pass
    class FILE_CHECKSUMS_ERROR: pass
    class DIRECTORY_SCANNED: pass

class FS(object):
    def __init__(self):
        self.eCtx = EventContext()

class RFSEvent:
    class INCOMMING_MESSAGE: pass

class RemoteNodesReceiver():
    def __init__(self, directory, fs, disp):
        self.node = directory
        self.fs = fs
        self.disp = disp
        self.finished = False
        self.total = None
        self.skipped = None
        self.files = {}
        self.dirs = {}
        self.nodes = {}

    def onIncommingMessage(self, event, msg):
        if msg._type != b"ret":
            return

        Attr, ep_data = msg.content.split(b"(", 1)
        ep, data = ep_data.split(b"\0", 1)

        node = self.node

        ep = ep.decode("utf-8")
        if ep != node.ep:
            return

        Attr = decode_str(Attr)
        getattr(self, "handle_" + Attr)(data)

        total = self.total
        if total is None:
            return

        skipped = self.skipped
        if skipped is None:
            return

        nodes = self.nodes

        if total != skipped + len(nodes):
            return

        node.files, node.dirs, node.nodes, node.skipped = \
            self.files, self.dirs, nodes, skipped

        self.finished = True
        self.disp.wake(self.co)

        self.fs.eCtx.notify(FSEvent.DIRECTORY_SCANNED, node)

    def handle_Nodes(self, data):
        self.total = int(data)

        # print("Total nodes count %d gotten" % self.total) # net-1

    def handle_Skipped(self, data):
        self.skipped = int(data)

        # print("Skipped %d gotten" % self.skipped) # net-1

    def handle_File(self, data):
        f = FileInfo(data.decode("utf-8"), directory = self.node)
        self.files[f.dp] = f
        self.nodes[f.dp] = f
        self.fs.eCtx.notify(FSEvent.FILE_FOUND, f)

        # print("File %s gotten" % f.dp) # net-1

    def handle_Dir(self, data):
        d = DirectoryInfo(data.decode("utf-8"), directory = self.node)
        self.dirs[d.dp] = d
        self.nodes[d.dp] = d
        self.fs.eCtx.notify(FSEvent.DIRECTORY_FOUND, d)

        # print("Directory %s gotten" % d.dp) # net-1

class RemoteAttrReceiver():
    def __init__(self, node, fs, disp):
        self.node = node
        self.fs = fs
        self.disp = disp
        self.finished = False

    def onIncommingMessage(self, event, msg):
        if msg._type != b"ret":
            return

        Attr, ep_data = msg.content.split(b"(", 1)
        ep, data = ep_data.split(b"\0", 1)

        node = self.node

        ep = ep.decode("utf-8")
        if ep != node.ep:
            return

        data = loads(data)

        Attr = decode_str(Attr)
        attr = Attr.lower()
        ATTR = Attr.upper()

        setattr(node, attr, data)

        self.finished = True
        self.disp.wake(self.co)

        self.fs.eCtx.notify(
            FSEvent["FILE_" + ATTR + "_GOT"], node
        )

class RemoteFS(FS):
    def __init__(self, remoteAddress, remotePort, rootDirectoryEffectiveName):
        super(RemoteFS, self).__init__()

        self.root = DirectoryInfo(rootDirectoryEffectiveName,
            fileSystem = self
        )

        s = socket(AF_INET, SOCK_STREAM)
        s.setblocking(0)
        s.connect_ex((remoteAddress, remotePort))

        self.clientSocket = s

        self.outMsgs = [AuthMessage(), FSMessage(rootDirectoryEffectiveName)]

        self.started = False

    def coSender(self):
        clientSocket = self.clientSocket
        outMsgs = self.outMsgs
        outMsg = None

        while True:
            if not outMsg:
                while not outMsgs:
                    yield False

                outMsg = outMsgs.pop(0)

            err = (yield (clientSocket, True))

            if err:
                print("Client socked error. Sender out.") # net-0
                try:
                    clientSocket.close()
                except:
                    pass
                break

            # print(outMsg) # net-1

            rest = outMsg.rest
            toSend = min(CHUNK_SIZE, rest)
            chunk = outMsg.chunk
            sent = clientSocket.send(chunk[:toSend])

            if sent == 0:
                print("Send returned 0. Sender out.") # net-0
                break
            elif sent == outMsg.rest:
                outMsg = None
            else:
                outMsg.chunk = chunk[sent:]
                outMsg.rest = rest - sent

    def coReceiver(self):
        clientSocket = self.clientSocket
        inMsg = None
        eCtx = self.eCtx

        while True:
            err = (yield (clientSocket, False))

            if err:
                print("Client socked error.") # net-0
                try:
                    clientSocket.close()
                except:
                    pass
                break

            if not inMsg:
                inMsg = Message()

            try:
                chunk = clientSocket.recv(min(CHUNK_SIZE, inMsg.rest))
            except ConnectionRefusedError:
                print("Connection refused.") # net-0
                try:
                    clientSocket.close()
                except:
                    pass
                break

            if chunk == b"":
                print("Server disconnected.") # net-0
                try:
                    clientSocket.close()
                except:
                    pass
                break
            else:
                inMsg.append(chunk)

                # print(inMsg) # net-1

                if not inMsg.rest:
                    eCtx.notify(RFSEvent.INCOMMING_MESSAGE, inMsg)
                    inMsg = None

    def coGetAttr(self, node, Attr):
        if not self.started:
            coDisp.enqueue(self.coSender())
            coDisp.enqueue(self.coReceiver())
            self.started = True

        ep = node.ep
        reqMsg = GetAttrMessage(ep, Attr)
        self.outMsgs.append(reqMsg)

        eCtx = self.eCtx

        if Attr == "Nodes":
            receiver = RemoteNodesReceiver(node, self, coDisp)
        else:
            receiver = RemoteAttrReceiver(node, self, coDisp)

        eCtx.listen(receiver.onIncommingMessage,
            RFSEvent.INCOMMING_MESSAGE
        )

        def co(receiver = receiver):
            while not receiver.finished:
                yield False

        receiver.co = co = co()
        yield co

        eCtx.forget(receiver.onIncommingMessage, RFSEvent.INCOMMING_MESSAGE)

    def __getattr__(self, name):
        try:
            (nope, Attr) = name.split("coGet")
        except ValueError:
            return super(RemoteFS, self).__getattr__(name)
        else:
            def co(node, Attr = Attr):
                yield self.coGetAttr(node, Attr)

            return co

# Directory Items Per Yield
DIPY = 100
# File CheckSum Block Size
FCSBS = 4 << 10 # 4 KiB

class LocalFS(FS): pass

class LinuxFS(LocalFS):
    def __init__(self, effectiveRootPath):
        super(LinuxFS, self).__init__()

        while effectiveRootPath[-1] == "/":
            effectiveRootPath = effectiveRootPath[:-1]

        self.root = DirectoryInfo(effectiveRootPath, fileSystem = self)
        self.sep = "/"

    def coGetModify(self, file):
        p = Popen(["stat", "-c", "%y", file.ep],
            stdout = PIPE,
            stderr = PIPE
        )

        while p.poll() is None:
            yield False

        if p.returncode != 0:
            self.eCtx.notify(FSEvent.FILE_MODIFY_ERROR, file,
                returncode = p.returncode,
                popen = p
            )
        else:
            file.modify = p.communicate()[0].decode("utf-8").strip()
            self.eCtx.notify(FSEvent.FILE_MODIFY_GOT, file)

    def coGetSize(self, file):
        p = Popen(["stat", "-c", "%s", file.ep],
            stdout = PIPE,
            stderr = PIPE
        )

        while p.poll() is None:
            yield False

        if p.returncode != 0:
            self.eCtx.notify(FSEvent.FILE_SIZE_ERROR, file,
                returncode = p.returncode,
                popen = p
            )
        else:
            file.size = long(p.communicate()[0])
            self.eCtx.notify(FSEvent.FILE_SIZE_GOT, file)

    def coGetChecksums(self, file):
        while True:
            try:
                restFile = file.size
            except AttributeError:
                yield file.attributeGetter("size")
            else:
                break

        f = openNoBlock(file.ep, "rb", FCSBS << 2)
        yield True

        checksums = []

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
            checksums.append(digest)

        yield True
        f.close()
        yield True

        file.checksums = tuple(checksums)

        self.eCtx.notify(FSEvent.FILE_CHECKSUMS_GOT, file)

    def coGetNodes(self, directory):
        # node pathes
        nps = listdir(directory.ep)

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

            ep = join(directory.ep, np)
            if isdir(ep):
                n = DirectoryInfo(np, directory = directory)
                dirs[np] = n
                self.eCtx.notify(FSEvent.DIRECTORY_FOUND, n)
            elif isfile(ep):
                n = FileInfo(np, directory = directory)
                files[np] = n
                self.eCtx.notify(FSEvent.FILE_FOUND, n)
            else:
                self.eCtx.notify(FSEvent.DIRECTORY_NODE_SKIPPED, directory,
                    path = np
                )
                skipped += 1
                continue

            n._ep = ep
            nodes[np] = n

        directory.files, directory.dirs, directory.nodes = files, dirs, nodes
        directory.skipped = skipped
        self.eCtx.notify(FSEvent.DIRECTORY_SCANNED, directory)

def pGetChecksums(ep, fsize,  q):
    f = open(ep, "rb", FCSBS << 2)

    restFile = fsize

    while restFile:
        toRead = min(FCSBS, restFile)

        readedBytes = f.read(toRead)
        readedLen = len(readedBytes)

        assert readedLen == toRead

        sha = sha1()
        sha.update(readedBytes)

        digest = sha.digest()
        q.put(digest)

        restFile -= readedLen

    q.put(None)

    f.close()

class WindowsFS(LocalFS):
    def __init__(self, effectiveRootPath):
        super(WindowsFS, self).__init__()

        while effectiveRootPath[-1] == "\\":
            effectiveRootPath = effectiveRootPath[:-1]

        self.root = DirectoryInfo(effectiveRootPath, fileSystem = self)
        self.sep = "\\"

    def coGetModify(self, file):
        try:
            ct = getctime(file.ep)
        except BaseException as e:
            msg = format_exc()
            self.eCtx.notify(FSEvent.FILE_MODIFY_ERROR, file,
                exception = e,
                trace = msg
            )
        else:
            file.modify = ct
            self.eCtx.notify(FSEvent.FILE_MODIFY_GOT, file)

    def coGetSize(self, file):
        try:
            s = getsize(file.ep)
        except BaseException as e:
            msg = format_exc()
            self.eCtx.notify(FSEvent.FILE_SIZE_ERROR, file,
                exception = e,
                trace = msg
            )
        else:
            file.size = s
            self.eCtx.notify(FSEvent.FILE_SIZE_GOT, file)

    def coGetChecksums(self, file):
        try:
            fsize = file.size
        except AttributeError:
            yield file.attributeGetter("size")
            fsize = file.size

        q = Queue()
        p = Process(target = pGetChecksums, args = (file.ep, fsize, q))
        p.run()

        yield True

        checksums = []

        while True:
            yield True

            while True:
                try:
                    block = q.get_nowait()
                except Empty:
                    if p.is_alive():
                        yield False
                    else:
                        raise RuntimeError(
                            "Process terminated before checksum is obtained"
                        )
                else:
                    break

            if block is None:
                break

            checksums.append(block)

        yield True

        file.checksums = tuple(checksums)

        self.eCtx.notify(FSEvent.FILE_CHECKSUMS_GOT, file)

    coGetNodes = LinuxFS.coGetNodes

class FSNode(object):
    def __init__(self, directoryPath, directory = None, fileSystem = None):
        assert (directory is None) != (fileSystem is None)

        self.dp = directoryPath
        if directory is None:
            self.fs = fileSystem
        else:
            self.d = directory
            self.fs = directory.fs

        self.req = {}

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

    def attributeGetter(self, attr):
        assert attr not in self.__dict__, \
            "Attempt to request available attribute " + attr

        req = self.req

        try:
            co = req[attr]
        except KeyError:
            coName = "coGet" + attr.title()
            coFn = getattr(self.fs, coName)
            co = coFn(self)
            req[attr] = co

        coDisp.desc[co] = "Getting " + attr + " of " + self.dp

        return co

    def requestAttribute(self, attr, coDisp):
        co = self.attributeGetter(attr)
        # TODO: Multiple queuing possible, but it is acceptable.
        coDisp.enqueue(co)

class FileInfo(FSNode):
    pass

class DirectoryInfo(FSNode):
    def coRecursiveReading(self):
        while True:
            try:
                dirs = self.dirs
            except AttributeError:
                yield self.attributeGetter("nodes")
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
class FSCEvent:
    class DIR_CMP_INFO: pass
    class FILE_CMP_INFO: pass
    class DIFF_DIR_SUBDIRS: pass
    class DIFF_DIR_FILES: pass
    class DIFF_FILES: pass

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
        "checksums"
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

                try:
                    a1 = getattr(f1, attr)
                except AttributeError:
                    yield f1.attributeGetter(attr)
                    a1 = getattr(f1, attr)

                try:
                    a2 = getattr(f2, attr)
                except AttributeError:
                    yield f2.attributeGetter(attr)
                    a2 = getattr(f2, attr)

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
                            yield d.attributeGetter("nodes")
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

    def onFileTSReadError(self, e, fi, returncode = 0, **kw):
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

def defaultFileCellValue(f = None):
    return "-" if isinstance(f, FSNoneNode) else ""

class CmpResTree(Treeview):
    def __init__(self, parent, rootDirs, coDisp, *args, **kw):
        fs2col = self.fs2col = {}

        columns = [ ":summary" ]
        for idx, rd in enumerate(rootDirs):
            col = rd.dp
            columns.append(col)
            fs2col[rd.fs] = (idx, col)

        kw["columns"] = columns
        Treeview.__init__(self, parent, *args, **kw)

        self.column("#0")

        self.heading(":summary", text = "Summary")

        # Evaluate headings
        allDP = [ rd.dp for rd in rootDirs]
        cSfx = ""

        while len(allDP) > 1:
            nextDP = []

            prefix, curSfx = split(allDP[0])
            if not curSfx:
                break
            if prefix:
                nextDP.append(prefix)

            for dp in allDP[1:]:
                prefix, suffix = split(dp)
                if curSfx != suffix:
                    break
                if prefix:
                    nextDP.append(prefix)
            else:
                allDP = nextDP
                cSfx = join(curSfx, cSfx)
                continue

            break

        cSfxStrip = len(cSfx)

        self.heading("#0", text = cSfx)
        for rd in rootDirs:
            self.heading(rd.dp,
                text = rd.dp[:-cSfxStrip] if cSfxStrip > 0 else rd.dp
            )

        eCtx = EventContext()
        cmpCtx = RootComparationContext(rootDirs, eCtx)
        coDisp.enqueue(cmpCtx.coCompare())

        self.iidGen = iidGenerator()
        # File system node comparation info to iid
        self.fsnci2iid = {None: ""}
        self.iid2fsnci = {}

        # Maintaning the tree
        eCtx.listen(self.onDirCmpInfo, FSCEvent.DIR_CMP_INFO)
        eCtx.listen(self.onFileCmpInfo, FSCEvent.FILE_CMP_INFO)

        # handling differences
        eCtx.listen(self.onFileDiffs, FSCEvent.DIFF_FILES)

        self.coDisp = coDisp

        self.refreshQueued = False

        self.bind("<<TreeviewOpen>>", self.onOpen, "+")

    # Miscellaneous
    # =============

    def genIID(self, fscin):
        iid = next(self.iidGen)
        self.fsnci2iid[fscin] = iid
        self.iid2fsnci[iid] = fscin
        return iid

    def sortFSNodes(self, nodes):
        fs2col = self.fs2col

        return sorted(nodes,
            key = lambda n : fs2col[n.fs][0]
        )

    # TODO: spread refresh mechanizm to other widgets
    def queueRefresh(self):
        if self.refreshQueued:
            return

        self.refreshQueued = True
        self.coDisp.enqueue(self.coRefresh())

    def coRefresh(self):
        attrs = FileComparationInfo.attrs

        self.refreshQueued = False

        if not self.selection():
            # select something
            iid = self.get_children("")[0]
            self.selection_set(iid)
            # http://stackoverflow.com/questions/11273612/how-to-set-focus-for-tkinter-widget
            self.focus(iid)

        queue = [""]

        while queue:
            iid = queue.pop(0)
            for ciid in self.get_children(iid):
                if self.item(ciid, "open"):
                    queue.append(ciid)

                yield True

                # another refreshing was queueed
                if self.refreshQueued:
                    raise StopIteration()

                fscin = self.iid2fsnci[ciid]
                summary = ""

                if isinstance(fscin, DirectoryComparationInfo):

                    childFCI = fscin.childFCI
                    childFCIDiff = fscin.childFCIDiff
                    childDCI = fscin.childDCI
                    extraFCI = fscin.totalFCI - childFCI
                    extraFCIDiff = fscin.totalFCIDiff - childFCIDiff
                    extralDCI = fscin.totalDCI - childDCI

                    if childFCI:
                        summary += " %u" % childFCI
                    if childFCIDiff:
                        summary += " (%u)" % childFCIDiff
                    if childDCI:
                        summary += " [%u]" % childDCI

                    extra = ""
                    if extraFCIDiff or extraFCI:
                        extra += " %u" % extraFCI
                    if extraFCIDiff:
                        extra += " (%u)" % extraFCIDiff
                    if extralDCI:
                        extra += " [%u]" % extralDCI

                    if extra:
                        summary += " +" + extra

                    if summary:
                        summary = summary[1:]

                elif isinstance(fscin, FileComparationInfo):
                    m = fscin.mesh

                    lost = False
                    inProgress = False
                    diffs = []
                    for attr in attrs:
                        for f1, f2 in fscin.pairs:
                            if isinstance(f1, FSNoneNode):
                                lost = True
                                continue
                            if isinstance(f2, FSNoneNode):
                                lost = True
                                continue

                            res = m[f1][f2]
                            try:
                                if not res [attr]:
                                    break
                            except KeyError:
                                inProgress = True
                        else:
                            continue
                        diffs.append(attr)

                    if inProgress:
                        diffs.insert(0, FILE_PENDING)

                    if lost:
                        diffs.append("lost")

                    if diffs:
                        summary = ", ".join(diffs)

                values = self.item(ciid, "values")
                self.item(ciid, values = [summary] + list(values[1:]))

    # Event handlers
    # ==============

    def onFileCmpInfo(self, event, fci):
        parent = self.fsnci2iid[fci.p]
        iid = self.genIID(fci)

        values = [
            ("-" if isinstance(fi, FSNoneNode) else FILE_PENDING) \
                for fi in self.sortFSNodes(fci.files)
        ]

        self.insert(parent, "end",
            iid = iid,
            text = fci.dp,
            values = [""] + values
        )

        self.queueRefresh()

    def onDirCmpInfo(self, event, dci):
        _open = False
        try:
            p = dci.p
        except AttributeError:
            parent = ""
            _open = True
        else:
            parent = self.fsnci2iid[p]
        iid = self.genIID(dci)

        values = [
            ("-" if isinstance(di, FSNoneNode) else DIRECTORY_PENDING) \
                for di in self.sortFSNodes(dci.dirs)
        ]

        self.insert(parent, "end",
            iid = iid,
            text = dci.dp,
            open = _open,
            values = [""] + values
        )

        self.queueRefresh()

    def onFileDiffs(self, event, fci):
        self.queueRefresh()

    def onOpen(self, *args):
        self.queueRefresh()

class CmpInfo(Frame):
    def __init__(self, parent, rootDirs, coDisp, *args, **kw):
        Frame.__init__(self, parent)

        self.grid()
        self.columnconfigure(0, weight = 1)

        self.rowconfigure(0, weight = 1)
        self.crt = crt = CmpResTree(self, rootDirs, coDisp)
        crt.grid(row = 0, column = 0, sticky = "NESW")
        crt.bind("<<TreeviewSelect>>", self.onSelect, "+")

        self.rowconfigure(1, weight = 0)
        self.infoFrame = infoFrame = Frame(self)
        infoFrame.grid(row = 1, column = 0, sticky = "NESW")

        infoFrame.grid()
        infoFrame.columnconfigure(0, weight = 1)

        infoFrame.rowconfigure(0, weight = 1)
        self.nameLabel = l = Label(infoFrame)
        l.grid(row = 0, column = 0, sticky = "NWS")

        crt.focus_set()

        self.updateInfo()

    def updateInfo(self):
        crt = self.crt
        nameLabel = self.nameLabel
        sel = crt.selection()

        if not sel:
            nameLabel.config(text = "Select something.")
        elif len(sel) == 1:
            iid = sel[0]
            fsnci = crt.iid2fsnci[iid]

            if isinstance(fsnci, FileComparationInfo):
                text = "File: "
            elif isinstance(fsnci, DirectoryComparationInfo):
                text = "Directory: "
            else:
                text = "?: "

            text += fsnci.dp

            nameLabel.config(text = text)
        else:
            nameLabel.config(text = "Multiple selection.")

    def onSelect(self, event):
        self.updateInfo()

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

        rootDirs = [
            newFS(rden).root for rden in rootDirectoryEffectiveNames
        ]
        ci = CmpInfo(self, rootDirs, coDisp)
        nbRoots.add(ci, text = "Overwiew")

        for rd in rootDirs:
            ri = RootInfo(self, rd, coDisp)
            nbRoots.add(ri, text = rd.dp)

        self.rowconfigure(1, weight = 0)
        self.statusBar = l = Label(self, font = ("Monospace", 8))
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
        r = coDisp.ready
        try:
            desc = coDisp.desc[r[0]]
        except (KeyError, IndexError):
            desc = ""
        else:
            desc = " // " + desc

        l.config(text = "Tasks: %2u + %2u (W)%s = %2u | %5u" % (
            len(r),
            len(coDisp.waiting),
            " + %2u (S2R) + %2u (S2W)" % (
                len(coDisp.socketsToRead),
                len(coDisp.socketsToWrite)
            ),
            coDisp.gotten,
            len(coDisp.queue)
        ) + " + %5u (C)" % len(coDisp.callers) + desc
        )

        if i > 0:
            if not coDisp.select(0.01):
                # print("sleep") # disp-1
                sleep(0.01)

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
        help = "A root directory to syncronize"
    )

    args = ap.parse_args()

    roots = args.roots
    if roots:
        root = MainWindow(args.roots)
        root.title(ap.description)
        root.geometry("1024x760")
        root.mainloop()
    else:
        srv = FSServer()
        srv.start()
        disp = srv.coDisp
        while True:
            if not disp.iterate():
                if not disp.select(0.01):
                    # print("sleep") # disp-1
                    sleep(0.01)
