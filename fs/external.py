# https://github.com/ispras/qdt/commit/124258761359953e1b903cef604284107e4bbc9c
from six.moves.tkinter import (
    Scrollbar,
    HORIZONTAL, VERTICAL,
)
from six.moves.tkinter_ttk import (
    Sizegrip
)


def add_scrollbars_native(outer, inner, row = 0, column = 0, sizegrip = False):
    "Adds scroll bars to a widget which supports them natively."
    outer.rowconfigure(row + 1, weight = 0)
    outer.columnconfigure(column + 1, weight = 0)

    h_sb = Scrollbar(outer,
        orient = HORIZONTAL,
        command = inner.xview
    )
    h_sb.grid(row = row + 1, column = column, sticky = "NESW")

    v_sb = Scrollbar(outer,
        orient = VERTICAL,
        command = inner.yview
    )
    v_sb.grid(row = row, column = column + 1, sticky = "NESW")

    inner.configure(xscrollcommand = h_sb.set, yscrollcommand = v_sb.set)

    if sizegrip:
        sg = Sizegrip(outer)
        sg.grid(
            row = row + 1,
            column = column + 1,
            sticky = "NESW"
        )
    else:
        sg = None

    return h_sb, v_sb, sg
