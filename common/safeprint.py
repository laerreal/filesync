from sys import (
    stdout,
)

exec("""
escape = lambda s : \
    s.encode("{ENC}", errors = "backslashreplace").decode("{ENC}")
""".format(
    ENC = stdout.encoding.lower()
)
)

def safeprint(*args):
    print(u" ".join(map(escape, args)))
