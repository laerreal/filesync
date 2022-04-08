from common.modules import (
    iter_modules_recursive,
)

from doctest import (
    DocTestSuite,
)
from os.path import (
    dirname,
)
from unittest import (
    main,
)


ROOT_DIR = dirname(dirname(__file__))

def load_tests(loader, tests, ignore):
    tests.addTests(
        map(
            DocTestSuite,
            map(
                ".".join,
                iter_modules_recursive(ROOT_DIR),
            )
        )
    )
    return tests


if __name__ == '__main__':
    main()
