from os import (
    listdir
)
from os.path import (
    isfile,
    isdir,
    join,
    sep
)


def proc_build_root_tree(q, root_path):
    queue = [(sep.join(root_path), 0)]

    dir_count = 1

    while queue:
        _path, _dir = queue.pop()

        q.put((0, (_path, _dir)))

        nodes = listdir(_path)

        q.put((1, nodes))

        folders = []

        for node_name in nodes:
            full_path = join(_path, node_name)
            if isdir(full_path):
                q.put((2, (node_name,)))

                folders.append((full_path, dir_count))
                dir_count += 1
            elif isfile(full_path):
                q.put((3, (node_name,)))
            else:
                print("Node of unknown kind: %s" % full_path)

        # TODO: first analyze folders which do exists in much of trees
        queue[:0] = folders

        q.put((4, None))

    q.put((None, None))

