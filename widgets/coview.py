__all__ = [
    "CoView"
]

from sys import version_info

if version_info[0] == 2:
    from ttk import Treeview
else:
    from tkinter.ttk import Treeview

from collections import deque

def coiid(co):
    return "co%u" % id(co)

socketRows = {"s2r", "s2w"}

def siid(sock):
    return "sock%u" % sock.fileno()

def cells(d, co):
    p = d.progress.get(co, None)

    if p is None:
        return ("?",)

    g = d.goal.get(co, None)

    if g is None:
        return (p,)

    aspect = p * 100 // g

    return ("%u/%u (%u%%)" % (p, g, aspect),)

class CoView(Treeview):
    def __init__(self, coDisp = None, **kw):
        kw["columns"] = [
            ":p" # progress
        ]

        Treeview.__init__(self, **kw)

        self.heading("#0", text = "Task")
        self.heading(":p", text = "Progress")

        self.insert("", "end",
            iid = "s2r",
            text = "Socket readers"
        )
        self.insert("", "end",
            iid = "s2w",
            text = "Socket writers"
        )

        self.d = coDisp

    def updateTree(self):
        d = self.d # dispatcher
        desc = d.desc # descriptions
        refs = d.references
        s2r = d.socketsToRead
        s2w = d.socketsToWrite

        allCo = deque(d.queue)
        allCo.extend(d.ready)
        allCo.extend(d.waiting)
        stack = [("", allCo)]

        toDel = set()

        for sockName in ["s2r", "s2w"]:
            sockDeps = locals()[sockName]

            children = set(self.get_children(sockName))

            for sock, co in sockDeps.items():
                iid = siid(sock)

                try:
                    children.remove(iid)
                except KeyError:
                    if self.exists(iid):
                        self.move(iid, sockName, "end")
                    else:
                        # no row for that socket yet
                        try:
                            peer = sock.getpeername()
                        except OSError:
                            text = "%s (%s)" % (
                                sock.getsockname(),
                                sock.fileno()
                            )
                        else:
                            text = "%s (%s) >=< %s" % (
                                sock.getsockname(),
                                sock.fileno(),
                                peer
                            )
                        # XXX: There is a negligible chance a socket was
                        # closed and a new one was opened with same number.
                        # Then text message should be updated

                        self.insert(sockName, "end",
                            iid = iid,
                            text = text
                        )

                        self.item(iid, open = True)
                finally:
                    self.item(iid, values = cells(d, co))

                stack.append((iid, (co,)))

            toDel |= children

        while stack:
            parent, allCo = stack.pop()
            children = set(self.get_children(parent))

            for co in allCo:
                iid = coiid(co)

                try:
                    children.remove(iid)
                except KeyError:
                    # no row for that task yet
                    try:
                        text = desc[co]
                    except KeyError:
                        text = co.__name__

                    # ensures that socket rows are always to the bottom
                    idx = "end" if parent else -2

                    if self.exists(iid):
                        # a row for that task is somewhere, use it
                        # print(parent, "<-", iid)
                        self.move(iid, parent, idx)
                        # print("ok")

                        if iid in toDel:
                            toDel.remove(iid)
                    else:
                        # print("ins", parent, "<-", iid)
                        self.insert(parent, idx, iid = iid, text = text)
                        self.item(iid, open = True)
                        # print("ok")
                finally:
                    self.item(iid, values = cells(d, co))

                if co in refs:
                    stack.append((iid, refs[co]))

            toDel |= children

        toDel -= socketRows

        # remove rows of forgotten tasks
        if toDel:
            self.delete(*list(toDel))
